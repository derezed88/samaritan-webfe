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

import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path

import httpx
import websockets as ws_lib
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import asyncio
import uvicorn

load_dotenv()

logger = logging.getLogger("uvicorn.error")

# ── Config ────────────────────────────────────────────────────────────────────
STT_DEBUG        = os.getenv("STT_DEBUG", "").lower() in ("1", "true", "yes")
LLMEM_GW_URL     = os.getenv("LLMEM_GW_URL", "http://localhost:8767")
SAMARITAN_API_KEY = os.getenv("SAMARITAN_API_KEY", "")   # gate for this app
LLMEM_GW_API_KEY = os.getenv("LLMEM_GW_API_KEY", "")   # forwarded to llmem-gw

app = FastAPI(title="Samaritan Interface")

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


@app.post("/api/submit")
async def submit(request: Request):
    """Submit a message to llmem-gw."""
    if not _check_auth(request):
        return _auth_error()

    body = await request.json()
    text = body.get("text", "")
    client_id = body.get("client_id", "samaritan-ui")

    payload = {"client_id": client_id, "text": text, "wait": False}

    async with httpx.AsyncClient(headers=_agent_headers(), timeout=10) as http:
        resp = await http.post(f"{LLMEM_GW_URL}/api/v1/submit", json=payload)
        resp.raise_for_status()

    return {"status": "submitted", "client_id": client_id}


@app.get("/api/stream/{client_id}")
async def stream_proxy(client_id: str, request: Request):
    """Proxy the SSE stream from llmem-gw to the browser."""
    if not _check_auth(request):
        return _auth_error()

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

                            elif event_type == "done":
                                full_response = "".join(response_tokens)
                                logger.info("RESP (%d chars): %s", len(full_response), full_response[:200])
                                # Fetch xAI voice token server-side and piggyback it
                                # on the SSE stream so the browser never needs a
                                # separate HTTP request (avoids Safari post-WS drop).
                                xai_key = os.getenv("XAI_API_KEY", "")
                                if xai_key:
                                    try:
                                        async with httpx.AsyncClient(timeout=8) as hx:
                                            tr = await hx.post(
                                                "https://api.x.ai/v1/realtime/client_secrets",
                                                headers={"Authorization": f"Bearer {xai_key}",
                                                         "Content-Type": "application/json"},
                                                json={"expires_in": 120},
                                            )
                                            if tr.is_success:
                                                yield f"data: {json.dumps({'type': 'vtok', 'token': tr.json()})}\n\n"
                                    except Exception:
                                        pass  # browser will fall back to direct fetch
                                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                                return

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
    Accepts: { "text": "...", "voice_id": "Evelyn", "model_id": "inworld-tts-1.5-max" }
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
    model_id      = body.get("model_id", "inworld-tts-1.5-max")
    speaking_rate = body.get("speaking_rate", 1.0)
    temperature   = body.get("temperature", 0.8)

    logger.info("TTS text (%d chars): %r", len(text), text[:120])

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

    logger.info("DG-TTS (%d chars, %s): %r", len(text), model, text[:120])

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

    logger.info("DG connect: %s", dg_url)
    try:
        async with ws_lib.connect(
            dg_url,
            additional_headers={"Authorization": f"Token {dg_key}"},
        ) as dg_ws:
            logger.info("DG handshake OK")

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
                                    transcript = (
                                        dg_msg.get("channel", {})
                                        .get("alternatives", [{}])[0]
                                        .get("transcript", "")
                                    )
                                    if transcript:
                                        logger.info("STT: %s", transcript)
                                elif msg_type not in ("Metadata",):
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


if __name__ == "__main__":
    import threading

    cert = Path(__file__).parent / "certs" / "cert.pem"
    key  = Path(__file__).parent / "certs" / "key.pem"
    use_tls = cert.exists() and key.exists()

    # Plain HTTP on 8801 — for pinggy tunnel (pinggy terminates TLS itself)
    def run_http():
        uvicorn.run("samaritan:app", host="0.0.0.0", port=8801, reload=False)

    t = threading.Thread(target=run_http, daemon=True)
    t.start()

    # HTTPS on 8800 — for local network access (mic requires HTTPS)
    uvicorn.run(
        "samaritan:app",
        host="0.0.0.0",
        port=8800,
        reload=False,
        ssl_certfile=str(cert) if use_tls else None,
        ssl_keyfile=str(key)   if use_tls else None,
    )
