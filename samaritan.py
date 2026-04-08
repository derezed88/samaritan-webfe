"""
Samaritan AI Web Client
A Person of Interest-themed web interface for the llmem-gw service.
Streams responses word-by-word in the Samaritan UI style.

Auth: Set SAMARITAN_API_KEY in .env (or environment).
      GET / redirects to /login if not authenticated.
      POST /login validates the password and sets an HttpOnly session cookie.
      Cookies persist in iOS PWA (WKWebView) across launches.
      API routes accept: Bearer token header, ?token= query param, or session cookie.
      The same key is forwarded to llmem-gw if LLMEM_GW_API_KEY is also set.
"""

import base64
import hashlib
import hmac
import json
import logging
from contextlib import asynccontextmanager
import os
import time
from pathlib import Path

import httpx
import websockets as ws_lib
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import asyncio
import uvicorn

load_dotenv()

logger = logging.getLogger("uvicorn.error")

# ── Config ────────────────────────────────────────────────────────────────────
STT_DEBUG        = os.getenv("STT_DEBUG", "").lower() in ("1", "true", "yes")
LOG_LEVEL        = os.getenv("LOG_LEVEL", "info").lower()   # set LOG_LEVEL=debug in .env to enable debug logs
LLMEM_GW_URL     = os.getenv("LLMEM_GW_URL", "http://localhost:8767")
MCP_DIRECT_URL   = os.getenv("MCP_DIRECT_URL", "http://localhost:8769")  # Claude Code MCP Direct
SAMARITAN_API_KEY = os.getenv("SAMARITAN_API_KEY", "")   # gate for this app
LLMEM_GW_API_KEY = os.getenv("LLMEM_GW_API_KEY", "")   # forwarded to llmem-gw
SIMLI_API_KEY    = os.getenv("SIMLI_API_KEY", "")       # Simli avatar API key
SIMLI_FACE_ID    = os.getenv("SIMLI_FACE_ID", "")       # Simli avatar face ID

# ── Cost event logging ────────────────────────────────────────────────────────

async def _log_cost(provider: str, service: str, cost_usd: float,
                    unit: str = None, unit_count: float = None, notes: str = None):
    """Fire-and-forget cost logger → samaritan_cost_events table."""
    try:
        import aiomysql
        conn = await aiomysql.connect(
            host="localhost",
            user=os.getenv("MYSQL_USER", "markj"),
            password=os.getenv("MYSQL_PASS", ""),
            db="mymcp", charset="utf8mb4",
        )
        async with conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO samaritan_cost_events
                   (provider, service, cost_usd, unit, unit_count, notes)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (provider, service, round(cost_usd, 6), unit, unit_count, notes),
            )
        await conn.commit()
        conn.close()
    except Exception as e:
        logger.debug("_log_cost failed: %s", e)

async def _auto_embed_sources_loop():
    """Every 5 min: embed any samaritan_sources rows missing from Qdrant samaritan_sources collection."""
    import pymysql
    import pymysql.cursors
    _EMBED_URL   = os.getenv("EMBED_URL",   "http://192.168.10.101:8000/v1/embeddings")
    _EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
    _QDRANT_HOST = os.getenv("QDRANT_HOST", "192.168.10.101")
    _QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
    _COLL        = "samaritan_sources"
    _INTERVAL    = 300  # seconds

    await asyncio.sleep(15)  # let server fully start before first check

    while True:
        try:
            def _check_and_embed():
                from qdrant_client import QdrantClient
                from qdrant_client.models import PointStruct
                import httpx as _httpx

                qc = QdrantClient(host=_QDRANT_HOST, port=_QDRANT_PORT, timeout=10)
                # collect existing Qdrant IDs
                existing, offset = set(), None
                while True:
                    pts, next_off = qc.scroll(_COLL, limit=1000, offset=offset,
                                              with_payload=False, with_vectors=False)
                    for p in pts:
                        existing.add(p.id)
                    if next_off is None:
                        break
                    offset = next_off

                conn = pymysql.connect(
                    host=os.getenv("MYSQL_HOST", "localhost"),
                    user=os.getenv("MYSQL_USER", "markj"),
                    password=os.getenv("MYSQL_PASS", ""),
                    database="mymcp", charset="utf8mb4",
                    cursorclass=pymysql.cursors.DictCursor,
                )
                with conn.cursor() as cur:
                    cur.execute("SELECT id, title, canonical_url, summary, domain_tags FROM samaritan_sources WHERE status='active'")
                    rows = cur.fetchall()
                conn.close()

                missing = [r for r in rows if r["id"] not in existing]
                if not missing:
                    return 0

                points = []
                for row in missing:
                    tags_raw = row["domain_tags"] or ""
                    try:
                        tags_list = json.loads(tags_raw) if tags_raw.strip().startswith("[") else tags_raw.split(",")
                        tags_str  = " ".join(t.strip() for t in tags_list if t.strip())
                    except Exception:
                        tags_str = tags_raw
                    text = ". ".join(p for p in [
                        row["title"] or row["canonical_url"] or "",
                        (row["summary"] or "")[:400],
                        tags_str,
                    ] if p).strip()[:1000]
                    try:
                        resp = _httpx.post(_EMBED_URL,
                                           json={"input": f"search_document: {text}", "model": _EMBED_MODEL},
                                           timeout=30)
                        resp.raise_for_status()
                        vector = resp.json()["data"][0]["embedding"]
                    except Exception as e:
                        logging.getLogger("uvicorn.error").warning("auto-embed source %s: %s", row["id"], e)
                        continue
                    points.append(PointStruct(
                        id=row["id"], vector=vector,
                        payload={"title": row["title"] or "", "type": "source",
                                 "domain_tags": tags_str, "summary": (row["summary"] or "")[:300]},
                    ))

                if points:
                    qc.upsert(collection_name=_COLL, points=points)
                return len(points)

            n = await asyncio.get_event_loop().run_in_executor(None, _check_and_embed)
            if n:
                logging.getLogger("uvicorn.error").info("auto-embed-sources: upserted %d new source(s)", n)
        except Exception as exc:
            logging.getLogger("uvicorn.error").warning("auto-embed-sources loop error: %s", exc)

        await asyncio.sleep(_INTERVAL)


@asynccontextmanager
async def _lifespan(app):
    asyncio.create_task(_auto_embed_sources_loop())
    yield


app = FastAPI(title="Samaritan Interface", lifespan=_lifespan)

# CORS — needed for Pinggy tunnel (Safari sends preflight OPTIONS for POST+JSON)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r".*",  # echo any origin (allow_origins=["*"] + credentials is invalid per spec)
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Suppress high-frequency polling endpoints from INFO logs → DEBUG only
_POLL_PATHS = ("/api/claude/poll",)

class _PollFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if any(p in msg for p in _POLL_PATHS):
            record.levelno = logging.DEBUG
            record.levelname = "DEBUG"
        return True

logging.getLogger("uvicorn.access").addFilter(_PollFilter())

# Per-client SSE stream cancellation: when a new stream opens for a client_id,
# the old one is signalled to exit so they don't compete on the same llmem-gw queue.
_stream_cancel: dict[str, asyncio.Event] = {}

# Serve static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── Auth helpers ──────────────────────────────────────────────────────────────
_COOKIE_NAME = "sam_session"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _make_cookie_value() -> str:
    """Sign a timestamp with HMAC-SHA256 so we can verify it later."""
    ts = str(int(time.time()))
    sig = hmac.new(SAMARITAN_API_KEY.encode(), ts.encode(), hashlib.sha256).hexdigest()
    return f"{ts}.{sig}"


def _verify_cookie(value: str) -> bool:
    ts, _, sig = value.partition(".")
    if not ts or not sig:
        return False
    expected = hmac.new(SAMARITAN_API_KEY.encode(), ts.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _check_auth(request: Request) -> bool:
    """Return True if auth passes (or SAMARITAN_API_KEY not set).
    Accepts: Bearer token header, ?token= query param, or session cookie.
    """
    if not SAMARITAN_API_KEY:
        return True
    auth = request.headers.get("Authorization", "")
    # Bearer token header
    if auth == f"Bearer {SAMARITAN_API_KEY}":
        return True
    # ?token= query param (for EventSource which can't set headers)
    if request.query_params.get("token") == SAMARITAN_API_KEY:
        return True
    # Session cookie
    cookie = request.cookies.get(_COOKIE_NAME, "")
    if cookie:
        if _verify_cookie(cookie):
            return True
        logger.warning("Cookie present but invalid")
    return False


def _auth_error():
    """Return 401 JSON for API routes that can't redirect."""
    return JSONResponse({"error": "Unauthorized"}, status_code=401)


def _agent_headers() -> dict:
    """Headers to forward to llmem-gw, including its bearer token if set."""
    h = {}
    if LLMEM_GW_API_KEY:
        h["Authorization"] = f"Bearer {LLMEM_GW_API_KEY}"
    return h


# ── Routes ────────────────────────────────────────────────────────────────────

_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SAMARITAN — Access Required</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #fff;
    color: #c00;
    font-family: 'Courier New', Courier, monospace;
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh;
  }
  .box {
    border: 2px solid #c00;
    padding: 2rem 2.5rem;
    width: min(340px, 90vw);
    text-align: center;
  }
  h1 { font-size: 1.1rem; letter-spacing: 0.2em; margin-bottom: 1.5rem; }
  input[type=password] {
    width: 100%; padding: 0.6rem 0.8rem;
    border: 1px solid #c00; background: #fff; color: #c00;
    font-family: inherit; font-size: 1rem;
    outline: none; margin-bottom: 1rem;
  }
  input[type=password]::placeholder { color: #f99; }
  button {
    width: 100%; padding: 0.6rem;
    background: #c00; color: #fff; border: none;
    font-family: inherit; font-size: 1rem; letter-spacing: 0.1em;
    cursor: pointer;
  }
  button:active { background: #900; }
  .err { color: #900; font-size: 0.85rem; margin-top: 0.8rem; }
</style>
</head>
<body>
<div class="box">
  <h1>SAMARITAN<br>ACCESS REQUIRED</h1>
  <form method="post" action="/login">
    <input type="password" name="password" placeholder="access key" autofocus autocomplete="current-password">
    <button type="submit">AUTHENTICATE</button>
    {error}
  </form>
</div>
</body>
</html>"""


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return HTMLResponse(_LOGIN_HTML.replace("{error}", ""))


@app.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    password = form.get("password", "")
    if not SAMARITAN_API_KEY or password == SAMARITAN_API_KEY:
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            _COOKIE_NAME,
            _make_cookie_value(),
            max_age=_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
        return response
    return HTMLResponse(
        _LOGIN_HTML.replace("{error}", '<p class="err">ACCESS DENIED</p>'),
        status_code=401,
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the UI — requires auth so the page is never shown to strangers."""
    if not _check_auth(request):
        return RedirectResponse(url="/login", status_code=302)
    html_path = Path(__file__).parent / "static" / "index.html"
    content = html_path.read_text().replace("%%SAMARITAN_API_KEY%%", SAMARITAN_API_KEY)
    return HTMLResponse(content=content, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    })


@app.get("/chat", response_class=HTMLResponse)
async def chat(request: Request):
    """Serve the Claude-like chat UI."""
    if not _check_auth(request):
        return RedirectResponse(url="/login", status_code=302)
    html_path = Path(__file__).parent / "static" / "chat.html"
    content = html_path.read_text().replace("%%SAMARITAN_API_KEY%%", SAMARITAN_API_KEY)
    return HTMLResponse(content=content, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    })


@app.get("/chat-ged", response_class=HTMLResponse)
async def chat_ged(request: Request):
    """Serve the GED study chat UI for Lee."""
    if not _check_auth(request):
        return RedirectResponse(url="/login", status_code=302)
    html_path = Path(__file__).parent / "static" / "chat-ged.html"
    content = html_path.read_text().replace("%%SAMARITAN_API_KEY%%", SAMARITAN_API_KEY)
    return HTMLResponse(content=content, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    })


@app.post("/api/submit")
async def submit(request: Request):
    """Submit a message to llmem-gw."""
    if not _check_auth(request):
        return _auth_error()

    body = await request.json()
    text = body.get("text", "")
    client_id = body.get("client_id", "samaritan-ui")
    logger.info("SUBMIT (%d chars): %r", len(text), text[:200])

    wait = body.get("wait", False)
    payload = {"client_id": client_id, "text": text}
    if body.get("location"):
        payload["location"] = body["location"]
    if wait:
        payload["wait"] = True

    timeout = httpx.Timeout(connect=10, read=120, write=10, pool=10) if wait else 10
    async with httpx.AsyncClient(headers=_agent_headers(), timeout=timeout) as http:
        resp = await http.post(f"{LLMEM_GW_URL}/api/v1/submit", json=payload)
        resp.raise_for_status()

    if wait:
        data = resp.json()
        return {"text": data.get("text", ""), "status": data.get("status", "complete")}
    return {"status": "submitted", "client_id": client_id}


@app.post("/api/pre-enrich")
async def pre_enrich_proxy(request: Request):
    """Pre-warm enrichment cache from partial speech transcript (fire-and-forget)."""
    if not _check_auth(request):
        return _auth_error()
    body = await request.json()
    try:
        async with httpx.AsyncClient(headers=_agent_headers(),
                                     timeout=httpx.Timeout(connect=5, read=10, write=5, pool=5)) as http:
            await http.post(f"{LLMEM_GW_URL}/api/v1/pre-enrich", json=body)
    except Exception:
        pass  # best-effort; never block the caller
    return JSONResponse({"status": "queued"})


@app.post("/api/analyze-photo")
async def analyze_photo_proxy(request: Request):
    """Proxy photo analysis to llmem-gw's analyze_photo endpoint."""
    if not _check_auth(request):
        return _auth_error()
    body = await request.json()
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=60, write=10, pool=10)) as http:
        resp = await http.post(f"{MCP_DIRECT_URL}/analyze_photo", json=body)
        return JSONResponse(resp.json(), status_code=resp.status_code)


@app.post("/api/drive-upload-photo")
async def drive_upload_photo_proxy(request: Request):
    """Proxy photo upload to Google Drive via llmem-gw."""
    if not _check_auth(request):
        return _auth_error()
    body = await request.json()
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=30, write=30, pool=10)) as http:
        resp = await http.post(f"{MCP_DIRECT_URL}/drive_upload_photo", json=body)
        return JSONResponse(resp.json(), status_code=resp.status_code)


@app.post("/api/eidetic-save")
async def eidetic_save_proxy(request: Request):
    """Proxy eidetic memory save to llmem-gw."""
    if not _check_auth(request):
        return _auth_error()
    body = await request.json()
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=30, write=10, pool=10)) as http:
        resp = await http.post(f"{MCP_DIRECT_URL}/eidetic_save", json=body)
        return JSONResponse(resp.json(), status_code=resp.status_code)


@app.get("/api/stream/{client_id}")
async def stream_proxy(client_id: str, request: Request):
    """Proxy the SSE stream from llmem-gw to the browser."""
    if not _check_auth(request):
        return _auth_error()

    # Cancel any previous generator for this client so it stops reading the shared queue
    old = _stream_cancel.pop(client_id, None)
    if old:
        old.set()
    cancel_ev = asyncio.Event()
    _stream_cancel[client_id] = cancel_ev

    async def event_generator():
        stream_url = f"{LLMEM_GW_URL}/api/v1/stream/{client_id}"
        try:
            async with httpx.AsyncClient(
                headers={**_agent_headers(), "Accept": "text/event-stream"},
                timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10),
            ) as http:
                async with http.stream("GET", stream_url) as resp:
                    event_type = "message"
                    data_lines = []
                    response_tokens = []

                    async for line in resp.aiter_lines():
                        if cancel_ev.is_set():
                            return
                        line = line.rstrip("\r")

                        if line.startswith("event:"):
                            event_type = line[6:].strip()
                        elif line.startswith("data:"):
                            data_lines.append(line[5:].strip())
                        elif line == "":
                            raw_data = "\n".join(data_lines)
                            data_lines = []

                            if event_type in ("", "message", "tok"):
                                try:
                                    token = json.loads(raw_data).get("text", "")
                                except (json.JSONDecodeError, ValueError):
                                    token = raw_data
                                if token:
                                    response_tokens.append(token)
                                    yield f"data: {json.dumps({'type': 'tok', 'text': token})}\n\n"

                            elif event_type == "flush":
                                # Intermediate checkpoint — more tokens coming after tool call.
                                # Forward text tokens for display but signal no-TTS-yet.
                                try:
                                    token = json.loads(raw_data).get("text", "")
                                except (json.JSONDecodeError, ValueError):
                                    token = raw_data
                                if token:
                                    response_tokens.append(token)
                                    yield f"data: {json.dumps({'type': 'flush', 'text': token})}\n\n"

                            elif event_type == "progress":
                                try:
                                    msg = json.loads(raw_data).get("text", raw_data)
                                except (json.JSONDecodeError, ValueError):
                                    msg = raw_data
                                logger.debug("PROGRESS: %s", msg)
                                yield f"data: {json.dumps({'type': 'progress', 'text': msg})}\n\n"

                            elif event_type == "done":
                                full_response = "".join(response_tokens)
                                logger.info("RESP (%d chars): %s", len(full_response), full_response[:200])
                                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                                return

                            elif event_type == "notif":
                                try:
                                    msg = json.loads(raw_data).get("text", raw_data)
                                except (json.JSONDecodeError, ValueError):
                                    msg = raw_data
                                logger.debug("NOTIF: %s", msg[:120])
                                yield f"data: {json.dumps({'type': 'notif', 'text': msg})}\n\n"

                            elif event_type == "error":
                                try:
                                    msg = json.loads(raw_data).get("message", raw_data)
                                except (json.JSONDecodeError, ValueError):
                                    msg = raw_data
                                yield f"data: {json.dumps({'type': 'error', 'message': msg})}\n\n"
                                return

                            event_type = "message"

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
        finally:
            # Remove our cancel event so the dict doesn't grow unbounded
            if _stream_cancel.get(client_id) is cancel_ev:
                _stream_cancel.pop(client_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/voice-token")
async def voice_token(request: Request):
    """Fetch a short-lived xAI ephemeral token for the realtime WebSocket API.
    The browser never sees the raw XAI_API_KEY; it only gets a single-use token.
    """
    if not _check_auth(request):
        return _auth_error()

    xai_key = os.getenv("XAI_API_KEY", "")
    if not xai_key:
        return JSONResponse({"error": "XAI_API_KEY not configured"}, status_code=503)

    body = await request.json()
    expires_in = body.get("expires_in", 60)  # seconds; browser can request shorter

    async with httpx.AsyncClient(timeout=10) as http:
        resp = await http.post(
            "https://api.x.ai/v1/realtime/client_secrets",
            headers={"Authorization": f"Bearer {xai_key}", "Content-Type": "application/json"},
            json={"expires_in": expires_in},
        )
        resp.raise_for_status()

    return resp.json()


@app.post("/api/tts/inworld")
async def tts_inworld(request: Request):
    """Proxy Inworld TTS streaming endpoint — keeps INWORLD_API_KEY server-side.
    Accepts: { "text": "...", "voice_id": "Evelyn", "model_id": "inworld-tts-1.5-mini" }
    Returns: newline-delimited JSON stream, each line is a chunk with base64 audioContent.
    Browser decodes each chunk independently via decodeAudioData and plays gaplessly.
    """
    if not _check_auth(request):
        return _auth_error()

    inworld_key = os.getenv("INWORLD_API_KEY", "")
    if not inworld_key:
        return JSONResponse({"error": "INWORLD_API_KEY not configured"}, status_code=503)

    body = await request.json()
    text          = body.get("text", "")
    voice_id      = body.get("voice_id", "Evelyn")
    model_id      = body.get("model_id", "inworld-tts-1.5-mini")
    speaking_rate = body.get("speaking_rate", 1.0)
    temperature   = body.get("temperature", 0.8)

    logger.debug("TTS text (%d chars): %r", len(text), text[:120])
    char_count = len(text)
    price_per_m = 10.00 if "max" in model_id else 5.00
    asyncio.ensure_future(_log_cost(
        provider="inworld", service=model_id,
        cost_usd=char_count * price_per_m / 1_000_000,
        unit="characters", unit_count=char_count,
        notes=f"voice={voice_id}",
    ))

    async def stream_chunks():
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=120, write=10, pool=5)) as http:
            async with http.stream(
                "POST",
                "https://api.inworld.ai/tts/v1/voice:stream",
                headers={"Authorization": f"Basic {inworld_key}", "Content-Type": "application/json"},
                json={
                    "text": text,
                    "voiceId": voice_id,
                    "modelId": model_id,
                    "temperature": temperature,
                    "audioConfig": {
                        "audioEncoding": "LINEAR16",
                        "sampleRateHertz": 24000,
                        "speakingRate": speaking_rate,
                    },
                },
            ) as resp:
                if not resp.is_success:
                    err = await resp.aread()
                    yield json.dumps({"error": err.decode()[:200]}) + "\n"
                    return
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if line:
                        yield line + "\n"

    return StreamingResponse(
        stream_chunks(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/tts/xai")
async def tts_xai(request: Request):
    """Proxy xAI TTS endpoint — keeps XAI_API_KEY server-side.
    Accepts: { "text": "...", "voice_id": "eve", "language": "en" }
    Returns: raw PCM audio bytes (24kHz 16-bit LE) streamed to browser.
    """
    if not _check_auth(request):
        return _auth_error()

    xai_key = os.getenv("XAI_API_KEY", "")
    if not xai_key:
        return JSONResponse({"error": "XAI_API_KEY not configured"}, status_code=503)

    body = await request.json()
    text     = body.get("text", "")
    voice_id = body.get("voice_id", "eve")
    language = body.get("language", "en")

    logger.debug("xAI TTS text (%d chars): %r", len(text), text[:120])
    char_count = len(text)
    asyncio.ensure_future(_log_cost(
        provider="xai", service="tts",
        cost_usd=char_count * 4.20 / 1_000_000,
        unit="characters", unit_count=char_count,
        notes=f"voice={voice_id}",
    ))

    async def stream_audio():
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=120, write=10, pool=5)) as http:
            async with http.stream(
                "POST",
                "https://api.x.ai/v1/tts",
                headers={"Authorization": f"Bearer {xai_key}", "Content-Type": "application/json"},
                json={
                    "text": text,
                    "voice_id": voice_id,
                    "language": language,
                    "output_format": {
                        "codec": "pcm",
                        "sample_rate": 24000,
                    },
                },
            ) as resp:
                if not resp.is_success:
                    err = await resp.aread()
                    logger.warning("xAI TTS error %d: %s", resp.status_code, err.decode()[:200])
                    yield b""
                    return
                async for chunk in resp.aiter_bytes(4096):
                    yield chunk

    return StreamingResponse(
        stream_audio(),
        media_type="audio/pcm",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/tts/deepgram")
async def tts_deepgram(request: Request):
    """Proxy Deepgram Aura TTS — keeps DEEPGRAM_API_KEY server-side.
    Accepts: { "text": "...", "model": "aura-2-thalia-en" }
    Returns: streaming PCM16-LE at 24kHz (raw bytes, no header).
    Browser feeds each chunk directly to pcmBytesToAudioBuf for gapless playback.
    """
    if not _check_auth(request):
        return _auth_error()

    dg_key = os.getenv("DEEPGRAM_API_KEY", "")
    if not dg_key:
        return JSONResponse({"error": "DEEPGRAM_API_KEY not configured"}, status_code=503)

    body = await request.json()
    text  = body.get("text", "")
    model = body.get("model", "aura-2-thalia-en")

    if not text:
        return JSONResponse({"error": "empty text"}, status_code=400)

    logger.debug("DG-TTS (%d chars, %s): %r", len(text), model, text[:120])

    async def stream_audio():
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10, read=120, write=10, pool=5)
        ) as http:
            async with http.stream(
                "POST",
                f"https://api.deepgram.com/v1/speak?model={model}&encoding=linear16&sample_rate=24000&container=none",
                headers={
                    "Authorization": f"Token {dg_key}",
                    "Content-Type": "application/json",
                },
                json={"text": text},
            ) as resp:
                if not resp.is_success:
                    err = await resp.aread()
                    logger.warning("DG-TTS error %s: %s", resp.status_code, err.decode()[:200])
                    yield b""
                    return
                async for chunk in resp.aiter_bytes():
                    yield chunk

    return StreamingResponse(
        stream_audio(),
        media_type="application/octet-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/simli/session")
async def simli_session(request: Request):
    """Create a Simli avatar session — returns session_token + ICE servers.
    API key stays server-side; browser only receives the ephemeral token.
    """
    if not _check_auth(request):
        return _auth_error()
    if not SIMLI_API_KEY:
        return JSONResponse({"error": "SIMLI_API_KEY not configured"}, status_code=503)
    if not SIMLI_FACE_ID:
        return JSONResponse({"error": "SIMLI_FACE_ID not configured"}, status_code=503)

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=30, write=10, pool=5)) as http:
        # Fetch ICE/TURN servers
        ice_resp = await http.get(
            "https://api.simli.ai/compose/ice",
            headers={"x-simli-api-key": SIMLI_API_KEY},
        )
        ice_servers = ice_resp.json() if ice_resp.is_success else []

        # Create session token
        tok_resp = await http.post(
            "https://api.simli.ai/compose/token",
            headers={"x-simli-api-key": SIMLI_API_KEY, "Content-Type": "application/json"},
            json={
                "faceId": SIMLI_FACE_ID,
                "apiVersion": "v2",
                "handleSilence": True,
                "maxSessionLength": 3600,
                "maxIdleTime": 300,
            },
        )
        token_data = tok_resp.json()

    if token_data.get("session_token") == "FAIL TOKEN":
        logger.warning("Simli session creation failed: %s", token_data.get("detail"))
        return JSONResponse({"error": token_data.get("detail", "Simli session failed")}, status_code=502)

    return JSONResponse({
        "session_token": token_data.get("session_token"),
        "iceServers": ice_servers,
    })


@app.get("/api/stt-token")
async def stt_token(request: Request):
    """Return the Deepgram API key for browser-direct WebSocket STT.
    The browser uses this as a Bearer token on wss://api.deepgram.com/v1/listen.
    """
    if not _check_auth(request):
        return _auth_error()
    dg_key = os.getenv("DEEPGRAM_API_KEY", "")
    if not dg_key:
        return JSONResponse({"error": "DEEPGRAM_API_KEY not configured"}, status_code=503)
    return JSONResponse({"key": dg_key})


@app.websocket("/api/stt-proxy")
async def stt_proxy(websocket: WebSocket, token: str = ""):
    """Proxy browser WebSocket → Deepgram, injecting Authorization header.
    Browser can't set custom headers on WebSocket, so we bridge it here.
    Query param: ?token=<SAMARITAN_API_KEY>  (same as other protected routes)
    Remaining query params (model, encoding, etc.) are forwarded to Deepgram.
    """
    # Authenticate caller
    if SAMARITAN_API_KEY and token != SAMARITAN_API_KEY:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    dg_key = os.getenv("DEEPGRAM_API_KEY", "")
    if not dg_key:
        await websocket.close(code=4002, reason="DEEPGRAM_API_KEY not configured")
        return

    # Build Deepgram URL — forward all query params except our 'token'
    params = dict(websocket.query_params)
    params.pop("token", None)
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    dg_version = "v2" if params.get("model", "").startswith("flux") else "v1"
    dg_url = f"wss://api.deepgram.com/{dg_version}/listen?{qs}"

    await websocket.accept()

    logger.debug("DG connect: %s", dg_url)
    try:
        async with ws_lib.connect(
            dg_url,
            additional_headers={"Authorization": f"Token {dg_key}"},
        ) as dg_ws:
            logger.debug("DG handshake OK")

            async def browser_to_dg():
                try:
                    while True:
                        msg = await websocket.receive()
                        if "bytes" in msg and msg["bytes"]:
                            await dg_ws.send(msg["bytes"])
                        elif "text" in msg and msg["text"]:
                            await dg_ws.send(msg["text"])
                        else:
                            break  # disconnect
                except (WebSocketDisconnect, Exception):
                    pass
                finally:
                    await dg_ws.close()

            async def dg_to_browser():
                try:
                    async for message in dg_ws:
                        if isinstance(message, bytes):
                            await websocket.send_bytes(message)
                        else:
                            await websocket.send_text(message)
                            try:
                                dg_msg = json.loads(message)
                                msg_type = dg_msg.get("type", "")
                                if msg_type == "TurnInfo":
                                    transcript = (dg_msg.get("transcript") or "").strip()
                                    event = dg_msg.get("event", "")
                                    if event == "Update":
                                        if STT_DEBUG and transcript:
                                            logger.info("STT [Update]: %s", transcript)
                                    else:
                                        logger.info("STT [%s]: %s", event, transcript)
                                elif dg_msg.get("is_final"):
                                    alt = (
                                        dg_msg.get("channel", {})
                                        .get("alternatives", [{}])[0]
                                    )
                                    transcript = alt.get("transcript", "")
                                    words = alt.get("words", [])
                                    diarized = any("speaker" in w for w in words)
                                    if transcript:
                                        if diarized:
                                            logger.info("STT [is_final/diarized]: %s", transcript)
                                        else:
                                            logger.info("STT: %s", transcript)
                                elif msg_type == "UtteranceEnd":
                                    logger.debug("STT [UtteranceEnd]")
                                elif msg_type not in ("Metadata", "Results"):
                                    logger.info("DG msg: %s", message[:200])
                            except Exception:
                                pass
                except Exception as e:
                    logger.info("DG stream closed: %s", e)
                finally:
                    try:
                        await websocket.close()
                    except Exception:
                        pass

            await asyncio.gather(browser_to_dg(), dg_to_browser())

    except Exception as e:
        logger.info("DG connect error: %s", e)
        try:
            await websocket.close(code=1011, reason=str(e)[:100])
        except Exception:
            pass


@app.websocket("/api/stt-inworld-proxy")
async def stt_inworld_proxy(websocket: WebSocket, token: str = ""):
    """Proxy browser WebSocket → Inworld STT, injecting Authorization header.
    Browser sends raw PCM Int16 binary; proxy base64-encodes and wraps in JSON.
    Inworld voice profile data (emotion, pitch, vocal_style) forwarded to browser.
    Query param: ?token=<SAMARITAN_API_KEY>&sample_rate=48000
    """
    if SAMARITAN_API_KEY and token != SAMARITAN_API_KEY:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    inworld_key = os.getenv("INWORLD_API_KEY", "")
    if not inworld_key:
        await websocket.close(code=4002, reason="INWORLD_API_KEY not configured")
        return

    params = dict(websocket.query_params)
    params.pop("token", None)
    sample_rate    = int(params.get("sample_rate", 16000))
    vp_threshold   = float(params.get("vp_threshold", 0.3))
    vad_threshold  = float(params.get("vad_threshold", 0.7))
    eot_silence_ms = int(params.get("eot_silence_ms", 600))

    await websocket.accept()
    _stt_start = time.time()

    inworld_url = "wss://api.inworld.ai/stt/v1/transcribe:streamBidirectional"
    logger.debug("Inworld STT connect: rate=%d vp_thresh=%.1f vad=%.1f eot=%dms",
                sample_rate, vp_threshold, vad_threshold, eot_silence_ms)

    try:
        async with ws_lib.connect(
            inworld_url,
            additional_headers={"Authorization": f"Basic {inworld_key}"},
        ) as iw_ws:
            logger.debug("Inworld STT handshake OK")

            # Send config message
            config_msg = json.dumps({
                "transcribeConfig": {
                    "modelId": "inworld/inworld-stt-1",
                    "audioEncoding": "LINEAR16",
                    "sampleRateHertz": sample_rate,
                    "language": "en-US",
                    "voiceProfileConfig": {
                        "enableVoiceProfile": True,
                        "topN": 3,
                    },
                    "inworldConfig": {
                        "voiceProfileThreshold": vp_threshold,
                        "inworldSttV1Config": {
                            "vadThreshold": vad_threshold,
                            "minEndOfTurnSilenceWhenConfident": eot_silence_ms,
                        },
                    },
                }
            })
            await iw_ws.send(config_msg)

            async def browser_to_inworld():
                try:
                    while True:
                        msg = await websocket.receive()
                        if "bytes" in msg and msg["bytes"]:
                            # Raw PCM binary → base64 → JSON audioChunk
                            b64_audio = base64.b64encode(msg["bytes"]).decode("ascii")
                            await iw_ws.send(json.dumps({
                                "audioChunk": {"content": b64_audio}
                            }))
                        elif "text" in msg and msg["text"]:
                            # Pass through text messages (endTurn, closeStream)
                            await iw_ws.send(msg["text"])
                        else:
                            break
                except (WebSocketDisconnect, Exception):
                    pass
                finally:
                    await iw_ws.close()

            async def inworld_to_browser():
                try:
                    async for message in iw_ws:
                        if isinstance(message, str):
                            await websocket.send_text(message)
                            try:
                                iw_msg = json.loads(message)
                                result = iw_msg.get("result", {})
                                tx = result.get("transcription", {})
                                transcript = (tx.get("transcript") or "").strip()
                                is_final = tx.get("isFinal", False)
                                if transcript:
                                    tag = "final" if is_final else "partial"
                                    logger.info("Inworld STT [%s]: %s", tag, transcript)
                                    if is_final:
                                        logger.debug("Inworld raw: %s", json.dumps(iw_msg, separators=(',', ':')))
                                vp = tx.get("voiceProfile")
                                if vp:
                                    emo_arr = vp.get("emotion") or []
                                    emo = emo_arr[0] if isinstance(emo_arr, list) and emo_arr else {}
                                    pit_arr = vp.get("pitch") or []
                                    pit = pit_arr[0] if isinstance(pit_arr, list) and pit_arr else {}
                                    vs_arr = vp.get("vocalStyle") or []
                                    vs = vs_arr[0] if isinstance(vs_arr, list) and vs_arr else {}
                                    if emo.get("label"):
                                        logger.info("Inworld VP: emotion=%s(%.2f) pitch=%s vocal=%s",
                                            emo.get("label"), emo.get("confidence", 0),
                                            pit.get("label", "?"), vs.get("label", "?"))
                            except Exception:
                                pass
                except Exception as e:
                    logger.info("Inworld STT stream closed: %s", e)
                finally:
                    try:
                        await websocket.close()
                    except Exception:
                        pass

            await asyncio.gather(browser_to_inworld(), inworld_to_browser())

    except Exception as e:
        logger.info("Inworld STT connect error: %s", e)
        try:
            await websocket.close(code=1011, reason=str(e)[:100])
        except Exception:
            pass
    finally:
        duration_s = time.time() - _stt_start
        asyncio.ensure_future(_log_cost(
            provider="inworld", service="inworld-stt-1",
            cost_usd=duration_s * 77.78 / 1_000_000,
            unit="seconds", unit_count=round(duration_s, 2),
        ))



@app.get("/knowledge-graph", response_class=HTMLResponse)
async def knowledge_graph(request: Request):
    """Serve the 3D knowledge graph UI."""
    if not _check_auth(request):
        return RedirectResponse(url="/login", status_code=302)
    html_path = Path(__file__).parent / "static" / "knowledge-graph.html"
    content = html_path.read_text().replace("%%SAMARITAN_API_KEY%%", SAMARITAN_API_KEY)
    return HTMLResponse(content=content, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    })


@app.post("/api/knowledge-graph")
async def knowledge_graph_api(request: Request):
    """Return nodes and edges for the knowledge graph.

    Request: { query: str, node_types: [belief|source|drive|memory], limit: int }
    Response: { nodes: [...], links: [...] }
    """
    if not _check_auth(request):
        return _auth_error()

    import aiomysql
    body   = await request.json()
    query  = body.get("query", "").strip().lower()
    types  = set(body.get("node_types", ["belief", "source", "drive", "memory"]))
    limit  = min(int(body.get("limit", 150)), 300)

    mysql_user = os.getenv("MYSQL_USER", "markj")
    mysql_pass = os.getenv("MYSQL_PASS", "")

    nodes, links = [], []
    node_ids = set()

    # Split multi-word queries into individual words for any-word matching.
    # "lee monthly cycle" → matches topic containing "lee" OR "monthly" OR "cycle"
    stop_words = {"the", "and", "for", "with", "a", "an", "in", "of", "to", "is", "are", "was"}
    words = [w for w in query.split() if w and w not in stop_words] if query else []
    # For belief/memory topic matching, drop tokens < 3 chars — short tokens like "ap"
    # produce false substring hits (e.g. "ap" matches "april" in unrelated belief topics).
    topic_words = [w for w in words if len(w) >= 3]

    def word_filter(col: str, params: list) -> str:
        """Return SQL fragment matching any query word in col, appending params."""
        if not words:
            return ""
        clauses = []
        for w in words:
            clauses.append(f"LOWER({col}) LIKE %s")
            params.append(f"%{w}%")
        return " AND (" + " OR ".join(clauses) + ")"

    try:
        conn = await aiomysql.connect(
            host="localhost", user=mysql_user, password=mysql_pass,
            db="mymcp", charset="utf8mb4", autocommit=True,
        )
        async with conn.cursor(aiomysql.DictCursor) as cur:

            # ── beliefs ──────────────────────────────────────────────
            if "belief" in types:
                params: list = []
                topic_filter = word_filter("topic", params)
                content_filter = word_filter("content", params)
                if words:
                    # Topic: OR any topic_word (>=3 chars — prevents "ap" matching "april")
                    # Content: AND all words (prevents single off-topic word pulling in unrelated beliefs)
                    tw = topic_words or words  # fallback if all words are short
                    tclauses = [f"LOWER(topic) LIKE %s" for _ in tw]
                    cclauses = [f"LOWER(content) LIKE %s" for _ in words]
                    t_params  = [f"%{w}%" for w in tw]
                    c_params  = [f"%{w}%" for w in words]
                    params = t_params + c_params
                    where = " AND ((" + " OR ".join(tclauses) + ") OR (" + " AND ".join(cclauses) + "))"
                else:
                    where, params = "", []
                sql = f"SELECT id, topic, content, confidence FROM samaritan_beliefs WHERE status='active'{where} ORDER BY confidence DESC, updated_at DESC LIMIT {limit}"
                await cur.execute(sql, params)
                for r in await cur.fetchall():
                    nid = f"b{r['id']}"
                    nodes.append({"id": nid, "label": r["topic"], "type": "belief",
                                  "content": r["content"] or "", "score": r["confidence"] / 10.0})
                    node_ids.add(nid)

            # ── sources ───────────────────────────────────────────────
            # Sources use threshold-based matching:
            #   1–2 words → all words must match (prevent "lee" matching Aruba docs)
            #   3+ words  → all-but-one words must match (allow "aruba cluster configuration"
            #               to match even if "configuration" isn't in domain_tags)
            if "source" in types:
                if words:
                    n_words = len(words)
                    threshold = n_words if n_words <= 2 else n_words - 1
                    case_parts = []
                    params = []
                    for w in words:
                        case_parts.append(
                            f"(CASE WHEN (LOWER(title) LIKE %s OR LOWER(domain_tags) LIKE %s) THEN 1 ELSE 0 END)"
                        )
                        params += [f"%{w}%", f"%{w}%"]
                    score_expr = " + ".join(case_parts)
                    sql = (
                        f"SELECT id, title, canonical_url, domain_tags, truth_score, summary,"
                        f" ({score_expr}) AS _ms"
                        f" FROM samaritan_sources WHERE status='active' AND truth_score >= 0.5"
                        f" HAVING _ms >= {threshold}"
                        f" ORDER BY _ms DESC, truth_score DESC LIMIT {limit // 2}"
                    )
                else:
                    sql = f"SELECT id, title, canonical_url, domain_tags, truth_score, summary FROM samaritan_sources WHERE status='active' AND truth_score >= 0.5 ORDER BY truth_score DESC LIMIT {limit // 2}"
                    params = []
                await cur.execute(sql, params)
                for r in await cur.fetchall():
                    nid = f"s{r['id']}"
                    nodes.append({"id": nid, "label": r["title"] or r["canonical_url"] or f"source-{r['id']}",
                                  "type": "source", "content": (r["summary"] or "")[:1500],
                                  "score": min(float(r["truth_score"] or 0) / 10.0, 1.0) if float(r["truth_score"] or 0) > 1.0 else float(r["truth_score"] or 0), "url": r["canonical_url"] or ""})
                    node_ids.add(nid)

            # ── drives ────────────────────────────────────────────────
            # When query is empty: show all drives. When queried: filter by name/description.
            if "drive" in types:
                if words:
                    nclauses = [f"LOWER(name) LIKE %s" for _ in words]
                    dclauses = [f"LOWER(description) LIKE %s" for _ in words]
                    params = [f"%{w}%" for w in words] + [f"%{w}%" for w in words]
                    where = " WHERE (" + " OR ".join(nclauses + dclauses) + ")"
                else:
                    where, params = "", []
                sql = f"SELECT id, name, description, value FROM samaritan_drives{where} ORDER BY value DESC"
                await cur.execute(sql, params)
                for r in await cur.fetchall():
                    nid = f"d{r['id']}"
                    nodes.append({"id": nid, "label": r["name"], "type": "drive",
                                  "content": (r["description"] or "")[:300], "score": float(r["value"] or 0) / 100.0})
                    node_ids.add(nid)

            # ── memories ──────────────────────────────────────────────
            # Threshold: importance >= 3 for filtered queries.
            # No-query overview: show top-N by importance (no hard threshold —
            # conv_log saves turns at importance 3-4, never reaching 6).
            if "memory" in types:
                min_imp = 3
                if words:
                    tclauses = [f"LOWER(topic) LIKE %s" for _ in words]
                    cclauses = [f"LOWER(content) LIKE %s" for _ in words]
                    params = [f"%{w}%" for w in words] + [f"%{w}%" for w in words]
                    where = " AND (" + " OR ".join(tclauses + cclauses) + ")"
                else:
                    where, params = "", []
                sql = f"SELECT id, topic, content, importance FROM samaritan_memory_shortterm WHERE importance >= {min_imp}{where} ORDER BY importance DESC, created_at DESC LIMIT {limit // 2}"
                await cur.execute(sql, params)
                for r in await cur.fetchall():
                    nid = f"m{r['id']}"
                    nodes.append({"id": nid, "label": r["topic"], "type": "memory",
                                  "content": (r["content"] or "")[:800], "score": float(r["importance"] or 0) / 10.0})
                    node_ids.add(nid)

            # ── edges: source_references (explicit) ──────────────────
            if node_ids:
                await cur.execute(
                    "SELECT DISTINCT source_id, context_topic FROM samaritan_source_references "
                    "WHERE context_topic IS NOT NULL ORDER BY used_at DESC LIMIT 500"
                )
                for r in await cur.fetchall():
                    src_nid = f"s{r['source_id']}"
                    if src_nid not in node_ids:
                        continue
                    ctx = (r["context_topic"] or "").lower()
                    # match context_topic against belief topics
                    for n in nodes:
                        if n["type"] == "belief" and ctx in n["label"].lower():
                            if len(links) < 300:
                                links.append({"source": src_nid, "target": n["id"],
                                              "weight": 1.0, "reason": "source_reference"})

            # ── edges: keyword overlap (topic keywords shared) ────────
            # Require 1 shared word that is >= 5 chars (filters trivial single-domain
            # tokens like "aruba" or "lee" that would over-connect all beliefs).
            belief_nodes = [n for n in nodes if n["type"] == "belief"]
            stop = {"the", "and", "for", "with", "are", "this", "that", "from", "not", "but",
                    "was", "has", "have", "aruba", "wifi", "network", "system", "using"}
            for i, a in enumerate(belief_nodes):
                a_words = {w for w in a["label"].replace("-", " ").split() if len(w) >= 5} - stop
                for b in belief_nodes[i+1:]:
                    if len(links) >= 300:
                        break
                    b_words = {w for w in b["label"].replace("-", " ").split() if len(w) >= 5} - stop
                    shared = a_words & b_words
                    if shared:
                        links.append({"source": a["id"], "target": b["id"],
                                      "weight": min(len(shared) / 3.0, 1.0), "reason": "keyword_overlap"})

            # ── edges: domain tag → belief topic overlap ──────────────
            source_nodes = [n for n in nodes if n["type"] == "source"]
            if source_nodes:
                await cur.execute(
                    "SELECT id, domain_tags FROM samaritan_sources WHERE status='active' AND truth_score >= 0.5 AND domain_tags IS NOT NULL"
                )
                def _parse_tags(raw):
                    if not raw:
                        return []
                    try:
                        parsed = json.loads(raw)
                        return [t.lower().strip() for t in parsed if t]
                    except Exception:
                        return [t.lower().strip() for t in raw.split(",") if t.strip()]
                src_tags = {r["id"]: _parse_tags(r["domain_tags"]) for r in await cur.fetchall()}
                for sn in source_nodes:
                    sid = int(sn["id"][1:])
                    tags = [t.strip() for t in src_tags.get(sid, [])]
                    for bn in belief_nodes:
                        if len(links) >= 300:
                            break
                        label_lower = bn["label"].lower()
                        if any(tag and tag in label_lower for tag in tags):
                            links.append({"source": sn["id"], "target": bn["id"],
                                          "weight": 0.6, "reason": "domain_tag"})

        conn.close()
    except Exception as exc:
        logger.exception("knowledge-graph DB error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)

    # ── Qdrant semantic edges ─────────────────────────────────────────────────
    # For each node type that has a Qdrant collection, fetch embeddings and
    # find nearest neighbors. Adds semantic edges (cosine > 0.75) and returns
    # suggested_links (cosine > 0.80) for nodes with no existing structural edge.
    suggested_links: list = []
    _QDRANT_COLL = {"b": "samaritan_beliefs", "s": "samaritan_sources", "m": "samaritan_memory"}
    _SEMANTIC_THRESHOLD   = 0.75
    _SUGGESTED_THRESHOLD  = 0.80
    try:
        from qdrant_client import QdrantClient
        qdrant_host = os.getenv("QDRANT_HOST", "192.168.10.101")
        qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))

        # Build existing-edge set for dedup
        edge_pairs: set = set()
        for lnk in links:
            s, t = lnk["source"], lnk["target"]
            edge_pairs.add((s, t)); edge_pairs.add((t, s))

        # Group node IDs by type prefix
        by_type: dict = {"b": [], "s": [], "m": []}
        for nid in node_ids:
            prefix = nid[0]
            if prefix in by_type:
                by_type[prefix].append(int(nid[1:]))

        def _build_semantic_edges():
            qc = QdrantClient(host=qdrant_host, port=qdrant_port, timeout=10)
            existing_colls = {c.name for c in qc.get_collections().collections}
            new_links, new_suggested = [], []
            local_edge_pairs = set(edge_pairs)
            for prefix, ids in by_type.items():
                if not ids:
                    continue
                coll = _QDRANT_COLL[prefix]
                if coll not in existing_colls:
                    continue
                pts = qc.retrieve(coll, ids=ids, with_vectors=True)
                for pt in pts:
                    if not pt.vector:
                        continue
                    self_nid = f"{prefix}{pt.id}"
                    result_batch = qc.query_points(
                        coll, query=pt.vector,
                        limit=6, score_threshold=_SEMANTIC_THRESHOLD,
                    )
                    for r in result_batch.points:
                        other_nid = f"{prefix}{r.id}"
                        if other_nid == self_nid or other_nid not in node_ids:
                            continue
                        pair = (min(self_nid, other_nid), max(self_nid, other_nid))
                        if pair in local_edge_pairs:
                            continue
                        local_edge_pairs.add(pair)
                        lnk = {"source": self_nid, "target": other_nid,
                               "weight": round(r.score, 3), "reason": "semantic"}
                        new_links.append(lnk)
                        if r.score >= _SUGGESTED_THRESHOLD and len(new_suggested) < 50:
                            new_suggested.append(lnk)
            return new_links, new_suggested

        sem_links, sem_suggested = await asyncio.get_event_loop().run_in_executor(None, _build_semantic_edges)
        links.extend(sem_links)
        suggested_links.extend(sem_suggested)
    except Exception as exc:
        logger.warning("knowledge-graph Qdrant error (non-fatal): %s", exc)

    return JSONResponse({"nodes": nodes, "links": links[:300], "suggested_links": suggested_links})


@app.post("/api/knowledge-graph/verify-source")
async def kg_verify_source(request: Request):
    """Verify a source node's stored summary against its actual URL and xai_search.

    Request:  { source_id: int, url: str, summary: str, title: str }
    Response: { verdict: "supported"|"partial"|"unsupported", confidence: 0-1,
                notes: str, unsupported_claims: [...], new_score: float }
    """
    if not _check_auth(request):
        return _auth_error()
    body = await request.json()
    source_id = body.get("source_id")
    url       = body.get("url", "").strip()
    summary   = body.get("summary", "").strip()
    title     = body.get("title", "").strip()

    if not url or not summary:
        return JSONResponse({"error": "url and summary required"}, status_code=400)

    def _is_substantial(text: str, min_chars: int = 300) -> bool:
        """True if text looks like real extracted content, not an error/empty response."""
        if not text or len(text) < min_chars:
            return False
        low = text.lower()
        error_phrases = (
            "extraction failed", "could not extract", "no content", "access denied",
            "not found", "error retrieving", "failed to fetch", "requires authentication",
            # search engine "nothing found" signals
            "zero results", "no results", "no relevant", "no information found",
            "no information was found", "could not find", "nothing found",
            "no specific information", "no data found",
        )
        return not any(p in low for p in error_phrases)

    # ── Step 1: fetch all four sources in parallel ────────────────────────────
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=60, write=10, pool=10)) as http:
        url_task    = http.post(f"{MCP_DIRECT_URL}/url_extract_tavily",
                                json={"url": url, "query": title})
        xai_task    = http.post(f"{MCP_DIRECT_URL}/xai_search",
                                json={"query": f"{title} {' '.join(summary.split()[:6])}"})
        sonar_task  = http.post(f"{MCP_DIRECT_URL}/sonar_answer",
                                json={"query": f"What does '{title}' cover? Verify: {summary[:300]}"})
        google_task = http.post(f"{MCP_DIRECT_URL}/google_search",
                                json={"query": f"{title} {' '.join(summary.split()[:8])}"})
        url_resp, xai_resp, sonar_resp, google_resp = await asyncio.gather(
            url_task, xai_task, sonar_task, google_task, return_exceptions=True)

    url_content = ""
    xai_content = ""
    sonar_content  = ""
    google_content = ""

    if not isinstance(url_resp, Exception) and url_resp.is_success:
        url_content = str(url_resp.json().get("result", ""))[:3000]
    elif isinstance(url_resp, Exception):
        logger.warning("verify-source url_extract failed: %s", url_resp)

    if not isinstance(xai_resp, Exception) and xai_resp.is_success:
        xai_content = str(xai_resp.json().get("result", ""))[:2000]
    elif isinstance(xai_resp, Exception):
        logger.warning("verify-source xai_search failed: %s", xai_resp)

    if not isinstance(sonar_resp, Exception) and sonar_resp.is_success:
        sonar_content = str(sonar_resp.json().get("result", ""))[:2000]
    elif isinstance(sonar_resp, Exception):
        logger.warning("verify-source sonar failed: %s", sonar_resp)

    if not isinstance(google_resp, Exception) and google_resp.is_success:
        google_content = str(google_resp.json().get("result", ""))[:2000]
    elif isinstance(google_resp, Exception):
        logger.warning("verify-source google failed: %s", google_resp)

    url_substantial    = _is_substantial(url_content)
    xai_substantial    = _is_substantial(xai_content, min_chars=100)
    sonar_substantial  = _is_substantial(sonar_content, min_chars=100)
    google_substantial = _is_substantial(google_content, min_chars=100)
    has_substantial_evidence = url_substantial or xai_substantial or sonar_substantial or google_substantial

    if not any([url_content, xai_content, sonar_content, google_content]):
        return JSONResponse({"error": "Could not retrieve any source content for verification"}, status_code=502)

    # ── Step 2: LLM assessment ────────────────────────────────────────────────
    prompt = f"""You are verifying whether a stored source summary is supported by the actual source content.

SOURCE URL CONTENT (extracted from {url}):
{url_content if url_substantial else "(extraction failed — URL may require auth or be a private document)"}

XAI/GROK SEARCH RESULTS for "{title}":
{xai_content if xai_substantial else "(no relevant results found)"}

SONAR/PERPLEXITY RESULTS for "{title}":
{sonar_content if sonar_substantial else "(not consulted or no results)"}

GOOGLE SEARCH RESULTS for "{title}":
{google_content if google_substantial else "(not consulted or no results)"}

STORED SUMMARY TO VERIFY:
{summary}

IMPORTANT: "Unverifiable" is NOT the same as "unsupported".
- If none of the above sources contain relevant content, return "partial" with confidence <= 0.3 — do NOT mark as unsupported.
- Only return "unsupported" if you found CONTRADICTING evidence — not merely absent evidence.
- Only return "supported" if you found CONFIRMING evidence in the content above.

Task: Determine if the specific claims in the stored summary are supported by the source content above.
Focus on factual claims (partnerships, product names, technical specs, company strategies).
Ignore stylistic differences.

Respond with ONLY valid JSON (no markdown):
{{
  "verdict": "supported" | "partial" | "unsupported",
  "confidence": 0.0-1.0,
  "unsupported_claims": ["claim 1", "claim 2"],
  "notes": "one sentence explanation"
}}"""

    assessment = {"verdict": "partial", "confidence": 0.5,
                  "unsupported_claims": [], "notes": "LLM assessment unavailable"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=45, write=10, pool=10)) as http:
            llm_resp = await http.post(f"{MCP_DIRECT_URL}/llm_call",
                                       json={"model": "reason-gemini", "prompt": prompt, "mode": "text"})
        if llm_resp.is_success:
            raw = llm_resp.json().get("result", "")
            # strip markdown fences if present
            raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            assessment = json.loads(raw)
    except Exception as exc:
        logger.warning("verify-source llm_call failed: %s", exc)

    # ── Step 3: update truth_score in DB based on verdict ────────────────────
    verdict    = assessment.get("verdict", "partial")
    confidence = float(assessment.get("confidence", 0.5))
    # Map verdict → new truth_score (on 1-10 scale to match existing data)
    score_map  = {"supported": 8, "partial": 4, "unsupported": 1}
    new_raw_score = score_map.get(verdict, 4)

    # Only update score when we have substantial evidence.
    # Never downgrade based on "couldn't find" — only on actual contradicting evidence.
    can_downgrade = has_substantial_evidence and confidence >= 0.6
    can_upgrade   = verdict == "supported" and confidence >= 0.6
    should_update_score = can_upgrade or (can_downgrade and verdict != "supported")

    if source_id and should_update_score:
        try:
            import aiomysql
            mysql_user = os.getenv("MYSQL_USER", "markj")
            mysql_pass = os.getenv("MYSQL_PASS", "")
            conn = await aiomysql.connect(
                host="localhost", user=mysql_user, password=mysql_pass,
                db="mymcp", charset="utf8mb4", autocommit=True,
            )
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE samaritan_sources SET truth_score=%s WHERE id=%s",
                    (new_raw_score, source_id)
                )
            conn.close()
        except Exception as exc:
            logger.warning("verify-source DB update failed: %s", exc)

    return JSONResponse({
        "verdict":            verdict,
        "confidence":         confidence,
        "unsupported_claims": assessment.get("unsupported_claims", []),
        "notes":              assessment.get("notes", ""),
        "new_score":          round(new_raw_score / 10.0, 1),
        "score_updated":      bool(source_id and should_update_score),
        "url_extracted":      bool(url_content),
        "xai_searched":       bool(xai_content),
        "sonar_consulted":    bool(sonar_content),
        "google_consulted":   bool(google_content),
    })


@app.get("/api/knowledge-graph/saved-views")
async def kg_saved_views_list(request: Request):
    """List saved graph views from MySQL directly."""
    if not _check_auth(request):
        return _auth_error()
    import aiomysql
    try:
        conn = await aiomysql.connect(
            host=os.getenv("MYSQL_HOST", "localhost"),
            user=os.getenv("MYSQL_USER", "markj"),
            password=os.getenv("MYSQL_PASS", ""),
            db="mymcp", charset="utf8mb4",
        )
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT topic, content FROM samaritan_kg_views ORDER BY created_at DESC LIMIT 100"
            )
            rows = await cur.fetchall()
        conn.close()
        views = [{"name": r["topic"], "query": r["content"]} for r in rows]
        return JSONResponse(views)
    except Exception as exc:
        logger.exception("kg_saved_views_list error: %s", exc)
        return JSONResponse([], status_code=200)


@app.post("/api/knowledge-graph/saved-views")
async def kg_saved_views_save(request: Request):
    """Persist a graph view query to MySQL. Only the query string is stored — views re-run on load."""
    if not _check_auth(request):
        return _auth_error()
    import aiomysql
    body = await request.json()
    name = body.get("name", "unnamed")
    payload = body.get("payload", {})
    query = payload.get("query", "") if isinstance(payload, dict) else ""
    try:
        conn = await aiomysql.connect(
            host=os.getenv("MYSQL_HOST", "localhost"),
            user=os.getenv("MYSQL_USER", "markj"),
            password=os.getenv("MYSQL_PASS", ""),
            db="mymcp", charset="utf8mb4",
        )
        async with conn.cursor() as cur:
            await cur.execute(
                "CREATE TABLE IF NOT EXISTS samaritan_kg_views "
                "(id INT AUTO_INCREMENT PRIMARY KEY, topic VARCHAR(500) NOT NULL UNIQUE, "
                "content TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
                "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)"
            )
            await cur.execute(
                "INSERT INTO samaritan_kg_views (topic, content) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE content=%s, updated_at=NOW()",
                (name, query, query)
            )
        await conn.commit()
        conn.close()
        return JSONResponse({"ok": True})
    except Exception as exc:
        logger.exception("kg_saved_views_save error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.delete("/api/knowledge-graph/saved-views")
async def kg_saved_views_delete(request: Request):
    """Delete a saved graph view by name."""
    if not _check_auth(request):
        return _auth_error()
    import aiomysql
    body = await request.json()
    name = body.get("name", "")
    if not name:
        return JSONResponse({"error": "name required"}, status_code=400)
    try:
        conn = await aiomysql.connect(
            host=os.getenv("MYSQL_HOST", "localhost"),
            user=os.getenv("MYSQL_USER", "markj"),
            password=os.getenv("MYSQL_PASS", ""),
            db="mymcp", charset="utf8mb4",
        )
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM samaritan_kg_views WHERE topic=%s", (name,))
        await conn.commit()
        conn.close()
        return JSONResponse({"ok": True})
    except Exception as exc:
        logger.exception("kg_saved_views_delete error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/cogn-costs")
async def cogn_costs(request: Request):
    """Return cognition loop costs from samaritan_cost_events, grouped by loop and period."""
    if not _check_auth(request):
        return _auth_error()
    try:
        import aiomysql
        mysql_user = os.getenv("MYSQL_USER", "markj")
        mysql_pass = os.getenv("MYSQL_PASS", "")
        conn = await aiomysql.connect(
            host="localhost", user=mysql_user, password=mysql_pass,
            db="mymcp", charset="utf8mb4",
            cursorclass=aiomysql.DictCursor,
        )
        try:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT
                        client_id AS `loop`,
                        DATE(ts) AS day,
                        COUNT(*) AS calls,
                        COALESCE(SUM(tokens_in), 0) AS tokens_in,
                        COALESCE(SUM(tokens_out), 0) AS tokens_out,
                        ROUND(COALESCE(SUM(cost_usd), 0), 6) AS cost_usd
                    FROM samaritan_cost_events
                    WHERE client_id LIKE 'cogn-%%'
                      AND ts >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                    GROUP BY client_id, DATE(ts)
                    ORDER BY DATE(ts) DESC, client_id
                """)
                rows = await cur.fetchall()
                # Convert date objects to strings for JSON serialization
                for r in rows:
                    if r.get("day"):
                        r["day"] = str(r["day"])
                return JSONResponse(rows)
        finally:
            conn.close()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/health")
async def health(request: Request):
    """Check llmem-gw health — also validates the caller's token."""
    if not _check_auth(request):
        return _auth_error()
    try:
        async with httpx.AsyncClient(headers=_agent_headers(), timeout=5) as http:
            resp = await http.get(f"{LLMEM_GW_URL}/api/v1/health")
            return resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Claude Code voice relay proxy ─────────────────────────────────────────
# Proxies voice frontend requests to the MCP Direct plugin's voice relay
# endpoints on llmem-gw port 8769.

@app.post("/api/claude-relay/submit")
async def claude_relay_submit(request: Request):
    """Proxy voice message to Claude Code via MCP Direct voice relay."""
    if not _check_auth(request):
        return _auth_error()
    body = await request.json()
    async with httpx.AsyncClient(timeout=10) as http:
        resp = await http.post(f"{MCP_DIRECT_URL}/voice_relay/submit", json=body)
        return JSONResponse(resp.json(), status_code=resp.status_code)


@app.get("/api/claude-relay/poll")
async def claude_relay_poll(request: Request):
    """Proxy long-poll for Claude Code's response."""
    if not _check_auth(request):
        return _auth_error()
    # Pass all query params through (wait, channel)
    params = dict(request.query_params)
    async with httpx.AsyncClient(timeout=35) as http:
        resp = await http.get(f"{MCP_DIRECT_URL}/voice_relay/poll", params=params)
        return JSONResponse(resp.json(), status_code=resp.status_code)


@app.get("/api/claude-relay/status")
async def claude_relay_status(request: Request):
    """Check if Claude Code voice relay is enabled."""
    if not _check_auth(request):
        return _auth_error()
    try:
        params = dict(request.query_params)
        async with httpx.AsyncClient(timeout=5) as http:
            resp = await http.get(f"{MCP_DIRECT_URL}/voice_relay/status", params=params)
            return JSONResponse(resp.json())
    except Exception:
        return JSONResponse({"enabled": False, "error": "MCP Direct unreachable"})


# ── RC-style tmux dispatch (replaces voice relay for Claude mode) ─────────

@app.post("/api/claude/submit")
async def claude_dispatch_submit(request: Request):
    """Submit message to Claude Code via tmux dispatch."""
    if not _check_auth(request):
        return _auth_error()
    body = await request.json()
    async with httpx.AsyncClient(timeout=10) as http:
        resp = await http.post(f"{MCP_DIRECT_URL}/claude/submit", json=body)
        return JSONResponse(resp.json(), status_code=resp.status_code)


@app.get("/api/claude/poll")
async def claude_dispatch_poll(request: Request):
    """Poll for Claude Code response from tmux dispatch."""
    if not _check_auth(request):
        return _auth_error()
    params = dict(request.query_params)
    async with httpx.AsyncClient(timeout=35) as http:
        resp = await http.get(f"{MCP_DIRECT_URL}/claude/poll", params=params)
        return JSONResponse(resp.json(), status_code=resp.status_code)


@app.get("/api/claude/status")
async def claude_dispatch_status(request: Request):
    """Check Claude Code tmux session health."""
    if not _check_auth(request):
        return _auth_error()
    try:
        params = dict(request.query_params)
        async with httpx.AsyncClient(timeout=5) as http:
            resp = await http.get(f"{MCP_DIRECT_URL}/claude/status", params=params)
            return JSONResponse(resp.json())
    except Exception:
        return JSONResponse({"enabled": False, "error": "MCP Direct unreachable"})


@app.post("/api/ged/start")
async def ged_start(request: Request):
    """Launch a GED Claude Code workspace on demand."""
    if not _check_auth(request):
        return _auth_error()
    body = await request.json()
    async with httpx.AsyncClient(timeout=75) as http:
        resp = await http.post(f"{MCP_DIRECT_URL}/ged/start", json=body)
        return JSONResponse(resp.json(), status_code=resp.status_code)


# ── Chat session management ───────────────────────────────────

@app.post("/api/chat/start")
async def chat_start(request: Request):
    """Start a Claude Code chat session on demand."""
    if not _check_auth(request):
        return _auth_error()
    body = await request.json()
    async with httpx.AsyncClient(timeout=75) as http:
        resp = await http.post(f"{MCP_DIRECT_URL}/chat/start", json=body)
        return JSONResponse(resp.json(), status_code=resp.status_code)


@app.get("/api/chat/sessions")
async def chat_sessions(request: Request):
    """List active chat sessions."""
    if not _check_auth(request):
        return _auth_error()
    try:
        async with httpx.AsyncClient(timeout=5) as http:
            resp = await http.get(f"{MCP_DIRECT_URL}/chat/sessions")
            return JSONResponse(resp.json())
    except Exception:
        return JSONResponse({"sessions": [], "error": "MCP Direct unreachable"})


@app.post("/api/chat/delete")
async def chat_delete(request: Request):
    """Kill a chat session."""
    if not _check_auth(request):
        return _auth_error()
    body = await request.json()
    async with httpx.AsyncClient(timeout=10) as http:
        resp = await http.post(f"{MCP_DIRECT_URL}/chat/delete", json=body)
        return JSONResponse(resp.json(), status_code=resp.status_code)


if __name__ == "__main__":
    import threading

    cert = Path(__file__).parent / "certs" / "cert.pem"
    key  = Path(__file__).parent / "certs" / "key.pem"
    use_tls = cert.exists() and key.exists()

    # Plain HTTP on 8801 — for pinggy tunnel (pinggy terminates TLS itself)
    def run_http():
        uvicorn.run("samaritan:app", host="0.0.0.0", port=8801, reload=False, log_level=LOG_LEVEL)

    t = threading.Thread(target=run_http, daemon=True)
    t.start()

    # HTTPS on 8800 — for local network access (mic requires HTTPS)
    uvicorn.run(
        "samaritan:app",
        host="0.0.0.0",
        port=8800,
        reload=False,
        log_level=LOG_LEVEL,
        ssl_certfile=str(cert) if use_tls else None,
        ssl_keyfile=str(key)   if use_tls else None,
    )
