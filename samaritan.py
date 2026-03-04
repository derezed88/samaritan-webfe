"""
Samaritan AI Web Client
A Person of Interest-themed web interface for the agent-mcp service.
Streams responses word-by-word in the Samaritan UI style.

Auth: Set SAMARITAN_API_KEY in .env (or environment).
      ALL routes (including /) require HTTP Basic Auth when this is set.
      Password = SAMARITAN_API_KEY, username is ignored.
      The browser caches the credential so the prompt only appears once.
      The same key is forwarded to agent-mcp if AGENT_MCP_API_KEY is also set.
"""

import base64
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
AGENT_MCP_URL     = os.getenv("AGENT_MCP_URL", "http://localhost:8767")
SAMARITAN_API_KEY = os.getenv("SAMARITAN_API_KEY", "")   # gate for this app
AGENT_MCP_API_KEY = os.getenv("AGENT_MCP_API_KEY", "")   # forwarded to agent-mcp

app = FastAPI(title="Samaritan Interface")

# Serve static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── Auth helpers ──────────────────────────────────────────────────────────────
def _check_auth(request: Request) -> bool:
    """Return True if auth passes (or SAMARITAN_API_KEY not set).
    Accepts: Bearer token header, Basic Auth header, or ?token= query param.
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
    # HTTP Basic Auth
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode()
            _, _, password = decoded.partition(":")
            if password == SAMARITAN_API_KEY:
                return True
        except Exception:
            pass
    return False


def _auth_error():
    """Return 401 with WWW-Authenticate to trigger browser credential dialog."""
    return JSONResponse(
        {"error": "Unauthorized"},
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Samaritan"'},
    )


def _agent_headers() -> dict:
    """Headers to forward to agent-mcp, including its bearer token if set."""
    h = {}
    if AGENT_MCP_API_KEY:
        h["Authorization"] = f"Bearer {AGENT_MCP_API_KEY}"
    return h


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the UI — requires auth so the page is never shown to strangers."""
    if not _check_auth(request):
        return _auth_error()
    html_path = Path(__file__).parent / "static" / "index.html"
    content = html_path.read_text().replace("%%SAMARITAN_API_KEY%%", SAMARITAN_API_KEY)
    return HTMLResponse(content=content, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    })


@app.post("/api/submit")
async def submit(request: Request):
    """Submit a message to agent-mcp."""
    if not _check_auth(request):
        return _auth_error()

    body = await request.json()
    text = body.get("text", "")
    client_id = body.get("client_id", "samaritan-ui")

    payload = {"client_id": client_id, "text": text, "wait": False}

    async with httpx.AsyncClient(headers=_agent_headers(), timeout=10) as http:
        resp = await http.post(f"{AGENT_MCP_URL}/api/v1/submit", json=payload)
        resp.raise_for_status()

    return {"status": "submitted", "client_id": client_id}


@app.get("/api/stream/{client_id}")
async def stream_proxy(client_id: str, request: Request):
    """Proxy the SSE stream from agent-mcp to the browser."""
    if not _check_auth(request):
        return _auth_error()

    async def event_generator():
        stream_url = f"{AGENT_MCP_URL}/api/v1/stream/{client_id}"
        try:
            async with httpx.AsyncClient(
                headers={**_agent_headers(), "Accept": "text/event-stream"},
                timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10),
            ) as http:
                async with http.stream("GET", stream_url) as resp:
                    event_type = "message"
                    data_lines = []

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
                                    yield f"data: {json.dumps({'type': 'tok', 'text': token})}\n\n"

                            elif event_type == "done":
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
    """Proxy Inworld TTS batch endpoint — keeps INWORLD_API_KEY server-side.
    Accepts: { "text": "...", "voice_id": "Evelyn", "model_id": "inworld-tts-1.5-max" }
    Returns: audio/mpeg (MP3) — decoded by browser via decodeAudioData.
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

    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(
            "https://api.inworld.ai/tts/v1/voice",
            headers={"Authorization": f"Basic {inworld_key}", "Content-Type": "application/json"},
            json={
                "text": text,
                "voiceId": voice_id,
                "modelId": model_id,
                "temperature": temperature,
                "audioConfig": {"speakingRate": speaking_rate},
            },
        )
        if not resp.is_success:
            return JSONResponse({"error": resp.text[:200]}, status_code=resp.status_code)
        data = resp.json()

    audio_b64 = data.get("audioContent", "")
    if not audio_b64:
        return JSONResponse({"error": "no audioContent in response"}, status_code=502)

    audio_bytes = base64.b64decode(audio_b64)
    return StreamingResponse(
        iter([audio_bytes]),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/api/health")
async def health(request: Request):
    """Check agent-mcp health — also validates the caller's token."""
    if not _check_auth(request):
        return _auth_error()
    try:
        async with httpx.AsyncClient(headers=_agent_headers(), timeout=5) as http:
            resp = await http.get(f"{AGENT_MCP_URL}/api/v1/health")
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
