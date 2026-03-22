<!-- Improved compatibility of back to top link: See: https://github.com/othneildrew/Best-README-Template/pull/73 -->
<a id="readme-top"></a>

<!-- PROJECT SHIELDS -->
[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![License][license-shield]][license-url]
[![LinkedIn][linkedin-shield]][linkedin-url]



<!-- PROJECT LOGO -->
<br />
<div align="center">

<h3 align="center">samaritan-webfe</h3>

  <p align="center">
    A <em>Person of Interest</em>-themed web front-end for the llmem-gw AI service.
    Streams LLM responses word-by-word in the Samaritan UI style with full voice I/O — speak to Samaritan and hear it speak back.
    <br />
    <a href="https://github.com/derezed88/samaritan-webfe"><strong>Explore the docs &raquo;</strong></a>
    <br />
    <br />
    <a href="https://github.com/derezed88/samaritan-webfe/issues/new?labels=bug&template=bug-report---.md">Report Bug</a>
    &middot;
    <a href="https://github.com/derezed88/samaritan-webfe/issues/new?labels=enhancement&template=feature-request---.md">Request Feature</a>
  </p>
</div>



<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li><a href="#screenshots">Screenshots</a></li>
    <li><a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#three-frontends-one-portfolio">Three Frontends, One Portfolio</a></li>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li><a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#mode-default---samaritan-voice-ui">Mode: Default</a>
      <ul>
        <li><a href="#voice-input-live-mode">Voice Input</a></li>
        <li><a href="#full-voice-hands-free-mode">Full-Voice Hands-Free</a></li>
        <li><a href="#keyboard-mode">Keyboard Mode</a></li>
        <li><a href="#idle-behaviour">Idle Behaviour</a></li>
      </ul>
    </li>
    <li><a href="#mode-cognitive---live-monitoring-dashboard">Mode: Cognitive</a></li>
    <li><a href="#voice-io">Voice I/O</a>
      <ul>
        <li><a href="#tts-providers-text-to-speech">TTS Providers</a></li>
        <li><a href="#stt-providers-speech-to-text">STT Providers</a></li>
        <li><a href="#mic-modes">Mic Modes</a></li>
      </ul>
    </li>
    <li><a href="#commands">Commands</a></li>
    <li><a href="#configuration">Configuration</a></li>
    <li><a href="#other-frontends">Other Frontends</a></li>
    <li><a href="#remote-access-via-pinggy">Remote Access via Pinggy</a></li>
    <li><a href="#security">Security</a></li>
    <li><a href="#developer-notes-adapting-this-frontend">Developer Notes</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>



<!-- SCREENSHOTS -->
## Screenshots

### `#mode default` — Samaritan Voice UI

<div align="center">
  <img src="docs/IMG_7650.PNG" alt="Samaritan UI — word flash animation" width="30%" />
  &nbsp;
  <img src="docs/IMG_7651.PNG" alt="Samaritan UI — terminal response panel" width="30%" />
  &nbsp;
  <img src="docs/IMG_7653.PNG" alt="Samaritan UI — voice mode" width="30%" />
</div>

### `#mode cognitive` — Live Monitoring Dashboard

<!-- TODO: Add screenshot here -->

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- ABOUT THE PROJECT -->
## About The Project

`samaritan-webfe` is a Python web service that provides a browser-based AI chat client styled
after the **Samaritan** interface from the CBS television series *Person of Interest* (2011-2016).
It acts as a front-end proxy to the [llmem-gw](https://github.com/derezed88/llmem-gw)
AI agent service, streaming responses token-by-token.

The Samaritan UI (`index.html`) operates in two modes:

- **`#mode default`** — The main voice/text chat with Samaritan's word-flash animation, terminal panel display, full-voice hands-free loop, and pluggable TTS/STT providers
- **`#mode cognitive`** — A real-time monitoring dashboard that polls llmem-gw's cognitive engine at 10-second resolution, displaying goals, beliefs, plans, tools, and live timer countdowns

### Three Frontends, One Portfolio

This repo contains three independent frontend UIs served by the same `samaritan.py` FastAPI server. They share the same llmem-gw backend and auth cookie, but each is a self-contained single-file HTML/CSS/JS application with no shared code between them:

| Frontend | Route | Description | Docs |
|----------|-------|-------------|------|
| **Samaritan Voice UI** | `/` | Person of Interest-themed voice interface (this README) | — |
| **Chat** | `/chat` | Claude-style scrolling chat with markdown, LaTeX, memory display | [docs/CHAT.md](docs/CHAT.md) |
| **Chat-GED** | `/chat-ged` | GED exam prep tutor with subject isolation, score tracking, Mermaid charts | [docs/CHAT-GED.md](docs/CHAT-GED.md) |

If you want to use any of these separately, you would need to pull them apart — each HTML file is standalone but relies on the `samaritan.py` proxy for auth, API key management, and SSE/WebSocket proxying. I keep them together as a **frontend portfolio** demonstrating different approaches to the same backend.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



### Built With

* [![Python][Python-badge]][Python-url]
* [![FastAPI][FastAPI-badge]][FastAPI-url]
* [![uvicorn][uvicorn-badge]][uvicorn-url]
* [![httpx][httpx-badge]][httpx-url]

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- GETTING STARTED -->
## Getting Started

### Prerequisites

- Python 3.10+
- [llmem-gw](https://github.com/derezed88/llmem-gw) running on the same host (default port 8767)
- `openssl` (for self-signed cert generation — usually pre-installed on Linux/macOS)
- At least one voice provider API key (required for FULL VOICE mode — see [Configuration](#configuration))

### Installation

1. Clone the repo
   ```sh
   git clone https://github.com/derezed88/samaritan-webfe.git
   cd samaritan-webfe
   ```

2. Copy and edit the environment file
   ```sh
   cp .env.example .env
   # Edit .env and set SAMARITAN_API_KEY plus at least one voice provider key — see Configuration below
   ```

3. Run the start script (creates venv, installs deps, generates TLS cert, starts server)
   ```sh
   chmod +x start.sh
   ./start.sh
   ```

4. Open in your browser
   - **Local network:** `https://<your-host-ip>:8800`
   - **Pinggy tunnel:** `https://<assigned-pinggy-url>` (see [Remote Access](#remote-access-via-pinggy))

<p align="right">(<a href="#readme-top">back to top</a>)</p>



## `#mode default` — Samaritan Voice UI

The default mode is the Person of Interest-styled interface. Short responses (< 10 words) animate center-screen in the show's word-flash style — one word at a time. Longer responses use a typewriter terminal panel at the top of the screen.

**Key features:**

- Samaritan visual style — white radial-gradient background, ALL-CAPS monospace font, red accent triangle, scanline overlay
- Word-by-word token animation; longer responses use a typewriter terminal panel
- Full-voice hands-free loop — speak, hear the response, mic reopens automatically
- Pluggable TTS providers (Deepgram Aura, Inworld, xAI, xAI Persistent) switchable at runtime
- Deepgram STT with multiple mic modes (barge-in, speaker-safe, diarization)
- Dark/light theme via `#screen_mode dark|light` with a 3-second crossfade
- Keyword-triggered Samaritan-style cards (INITIATIVE, ASSET, TASK, THREAT)

### Voice Input (LIVE mode)

1. Tap the **MIC** button — the label changes to **LIVE** and the interface listens
2. Speak your query — it auto-submits when you finish speaking
3. The response streams word-by-word on screen
4. When the response finishes, the mic restarts automatically for the next turn

### Full-Voice Hands-Free Mode

1. Tap **D / I / X** (TTS provider button) to cycle through Deepgram Aura, Inworld, xAI, or xAI Persistent
2. Tap **FULL VOICE** to enable spoken responses, then tap **MIC** to start listening
3. Speak your query — Samaritan responds in text *and* speaks the response aloud via AI voice
4. After the audio finishes, the mic reopens automatically — the loop continues hands-free indefinitely
5. Works over remote access (Pinggy tunnel) from any device with a browser and microphone

> **Note:** Voice responses require at least one TTS provider API key in `.env` (see [Configuration](#configuration)).
> Tap the provider button in the control bar to cycle providers at any time without reloading.

### Keyboard Mode

1. Tap the **keyboard** button to open the text input
2. Type your query and press **Enter** or tap **SEND**
3. The input panel closes while the response streams, then reopens ready for the next message
4. If FULL VOICE is active, typed prompts also receive a spoken response

### Idle Behaviour

After `IDLE_TIMEOUT_SEC` seconds (default 300 / 5 minutes), the screen clears and returns to the blinking `CONNECTION ESTABLISHED.` state.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



## `#mode cognitive` — Live Monitoring Dashboard

Type `#mode cognitive` to switch to the real-time monitoring dashboard. This mode polls llmem-gw's cognitive engine and displays the internal state of the AI agent.

**Layout — 4-column display:**

| Column | Width | Content |
|--------|-------|---------|
| Left data stack | 220px | Goals, beliefs, prospective memory, plans (auto-scrolling cards) |
| Center top | flex | Dashboard with live timer table |
| Center bottom | flex | Chat log with input field |
| Right | 352px | Samaritan-style countdown timer cards |

**Live data cards** (refreshed every 30 seconds):

- `!cogn goals` — Current LLM goals
- `!cogn flags` — Belief flags
- `!plan` — Current plan breakdown
- `!cogn` — Full cognition state (prospective memory)
- `!toolstats` — Tool usage and availability
- `!memstats` — Memory pool statistics

**Timer cards** (right column, refreshed every second):

- Parsed from the `!timers` command
- Each card shows timer name, live countdown, status, last/next run, duration, run count
- Multiple timers auto-cycle through groups of 3

**Chat input:**

The center-bottom panel has a live input field for interacting with the agent while monitoring. Type `#mode default` to return to the main Samaritan UI.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



## Voice I/O

### TTS Providers (Text-to-Speech)

Samaritan uses a pluggable TTS provider architecture. Switch at runtime via the **VOICE** button in the control bar, or set the default via `TTS_PROVIDER` in the JS config block of `index.html`.

| Provider | Button | API Key | Audio Format | Notes |
|----------|--------|---------|--------------|-------|
| **Deepgram Aura** | `D` | `DEEPGRAM_API_KEY` | HTTP streaming PCM16-LE @ 24kHz | Server proxy at `/api/tts/deepgram`. Model: `aura-asteria-en` (configurable). |
| **Inworld AI** | `I` | `INWORLD_API_KEY` | Streaming NDJSON, base64 WAV chunks | Server proxy at `/api/tts/inworld`. Voice: `Evelyn`. Model: `inworld-tts-1.5-mini`. 44-byte RIFF header stripped per chunk. |
| **xAI Realtime** | `X` | `XAI_API_KEY` | Per-turn WebSocket | Ephemeral token minted server-side per response. Voices: Eve, Ara, Rex, Sal, Leo. Sentence-level streaming. |
| **xAI Persistent** | `XP` (amber) | `XAI_API_KEY` | Persistent WebSocket | Keeps connection open across turns; auto-refreshes token before expiry. Pairs with `XAI_PERSISTENT_MODEL` for low-latency responses. |

All API keys are kept server-side — they are never sent to the browser.

**Configurable constants** (top of JS in `index.html`):

```js
let   TTS_PROVIDER            = 'inworld';            // default: 'deepgram' | 'inworld' | 'xai' | 'xai-persistent'
const DEEPGRAM_TTS_MODEL      = 'aura-asteria-en';
const XAI_VOICE               = 'ara';                // Eve | Ara | Rex | Sal | Leo
const INWORLD_VOICE           = 'Evelyn';
const INWORLD_MODEL           = 'inworld-tts-1.5-mini';
```

**Audio pipeline:** All providers feed into a shared Web Audio API pipeline (`scheduleAudioChunk`) for gapless playback. Barge-in support stops all queued audio immediately via `stopAllAudio()`.

### STT Providers (Speech-to-Text)

| Provider | Model | API | Notes |
|----------|-------|-----|-------|
| **Deepgram Flux** | `flux-general-en` | v2 `/listen` | Default STT. Native turn detection via `TurnInfo` events. EOT threshold: 0.8. Do NOT send `language` or `punctuate` params. |
| **Deepgram Nova-3 (Diarize)** | `nova-3` | v1 `/listen` | Used in DI mic mode only. `diarize=true`, labels each speaker as `[Speaker N]: text`. |

Audio capture uses an AudioWorklet (PCM16-LE) with ScriptProcessorNode fallback for iOS Safari. PCM is buffered to ~80ms chunks before sending (Flux requirement). The server-side WebSocket proxy (`/api/stt-proxy`) injects the Deepgram `Authorization` header so the API key never reaches the browser.

### Mic Modes

The rightmost button cycles through four STT modes:

| Mode | Icon | Behavior |
|------|------|----------|
| **Off** | mic icon | Mic disabled in full-voice mode |
| **Barge-in** | **B** (red) | Incoming speech during TTS immediately stops playback — best for headphones/AirPods |
| **Speaker** | **S** (amber) | Mic stays on but transcripts are suppressed during TTS — safe for phone speaker use. 1500ms cooldown after audio ends. |
| **Diarize** | **DI** (blue/red pulse) | Deepgram nova-3 + speaker diarization; each turn prefixed with `[Speaker N]:` for multi-person conversations |

If you are using a phone or tablet without headphones, use **S** or **DI** mode to prevent feedback loops.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



## Commands

These commands are typed in the input field (keyboard mode in default, or the chat input in cognitive mode):

| Command | Mode | Effect |
|---------|------|--------|
| `#mode default` | Any | Switch to the Samaritan voice UI |
| `#mode cognitive` | Any | Switch to the cognitive monitoring dashboard |
| `#mode chat` | Default | Redirect to `/chat` (Chat UI) |
| `#mode chat-ged` | Default | Redirect to `/chat-ged` (GED Study UI) |
| `#screen_mode dark` | Default | Switch to dark theme (3s crossfade) |
| `#screen_mode light` | Default | Switch to light theme |
| `#inworld_voice <name>` | Default | Change Inworld TTS voice at runtime |
| `#db <name>` | Cognitive | Switch active database across all cognitive sessions |

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- CONFIGURATION -->
## Configuration

All configuration lives in `.env` in the project root. A template is provided — copy it and fill in your values:

```sh
cp .env.example .env
```

`.env` is listed in `.gitignore` and must never be committed. The variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `SAMARITAN_API_KEY` | Yes | Access password for the web UI. Set to any strong secret string. Must not end with `!` (iOS autofill strips it). |
| `LLMEM_GW_API_KEY` | No | Bearer token forwarded to llmem-gw. Leave blank if llmem-gw has no key set. |
| `LLMEM_GW_URL` | No | Base URL of the llmem-gw service. Default: `http://localhost:8767`. |
| `DEEPGRAM_API_KEY` | For STT + Deepgram TTS | Used server-side for STT WebSocket proxy and TTS streaming. Never sent to browser. [console.deepgram.com](https://console.deepgram.com/) |
| `XAI_API_KEY` | For xAI voice | Used server-side to mint ephemeral WebSocket tokens. Never sent to browser. [console.x.ai](https://console.x.ai/) |
| `INWORLD_API_KEY` | For Inworld voice | Base64-encoded credential from Inworld Portal (Settings > API Keys). Never sent to browser. |

Additional JS constants at the top of `static/index.html`:

```js
const IDLE_TIMEOUT_SEC        = 300;                   // seconds before idle screen
const WORD_FADE               = 180;                   // ms opacity transition per word
const WORD_HOLD               = 380;                   // ms each word is visible
const WORD_GAP                = 60;                     // ms gap between words
const LONG_RESPONSE_THRESHOLD = 10;                    // words — responses >= this use terminal display
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>



## Other Frontends

This repo includes two additional chat-style frontends. Each is a self-contained single-file HTML application with its own feature set:

- **[Chat UI](docs/CHAT.md)** (`/chat`) — Claude-style scrolling chat with markdown rendering, KaTeX math, database sidebar, model selection, Inworld TTS, and Deepgram STT
- **[Chat-GED](docs/CHAT-GED.md)** (`/chat-ged`) — GED exam prep tutor with 5-subject isolation, score tracking, progress dashboards, Mermaid diagram rendering, and quiz analytics

See the linked docs for full feature descriptions and usage instructions.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- REMOTE ACCESS -->
## Remote Access via Pinggy

[Pinggy](https://pinggy.io) provides an SSH-based tunnel that terminates TLS on its end,
meaning the browser sees a valid HTTPS URL (required for the Web Speech API microphone).

The app listens on HTTP port **8801** specifically for the tunnel (no TLS — pinggy handles it):

```sh
ssh -p 443 \
    -R0:localhost:8801 \
    -o StrictHostKeyChecking=no \
    -o ServerAliveInterval=10 \
    -o ServerAliveCountMax=6 \
    -o TCPKeepAlive=yes \
    -o ExitOnForwardFailure=yes \
    -o ConnectTimeout=30 \
    -t YOUR_TOKEN@pro.pinggy.io "k:4YOUR_KEY" x:https
```

Pinggy prints the assigned public URL on connect. Share only with trusted users —
the `SAMARITAN_API_KEY` auth prompt is the access gate.

| Port | Protocol | Purpose |
|------|----------|---------|
| 8800 | HTTPS    | Local network access (self-signed cert) |
| 8801 | HTTP     | Pinggy tunnel endpoint (pinggy provides TLS) |

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- SECURITY -->
## Security

- **Cookie-based auth** is enforced on every route including `/`. Unauthorized clients are redirected to `/login`.
- `POST /login` validates the password against `SAMARITAN_API_KEY` and sets an `HttpOnly; SameSite=lax` cookie (30 days).
- Auth also accepts: `Bearer` token header or `?token=` query param (for SSE streams).
- `LLMEM_GW_API_KEY` and all voice provider keys are server-side secrets — never exposed to the browser.
- The self-signed cert on port 8800 will trigger a browser warning on first visit; accept it once.
- Cookie persists in iOS PWA (WKWebView) across launches.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- DEVELOPER NOTES -->
## Developer Notes: Adapting This Frontend

I created this front end because I wanted to combine the memory capabilities of llmem-gw, allowing me to choose any mainstream or locally hosted LLM with the voice providers of my choice.

As an example, let's say you like the Grok app's ability to handle text and voice in the same chat. What's really going on in the backend is that when in text mode, Grok is using models that have a much bigger context window than when in live voice mode — in live voice mode, as of this writing the Voice Agent is used and that is backed by a model with a much smaller 32k-token context window. There are good reasons for that, and the biggest reason I can see is optimizing for voice quality: your voice and the model handling the voice are the same, or at least together, reducing API turns.

This project is therefore a workaround, with some performance hit and possible cost implications. If you want to send voice to e.g. `grok-4-1-fast-reasoning` (or any other model that llmem-gw supports — and that includes all mainstream models and any OpenAI-compatible or llama/ollama-hosted model), then you need to process STT (your voice speech-to-text) and TTS (the model's text response to voice), with the LLM of your choice in the middle. I first started with simple Web Speech API for input and text response only. That wasn't good enough for me, so I went with Deepgram for STT and xAI and Inworld for TTS. I don't have enough resources to locally host models to do it on my own, so cloud APIs it is for me. Of course if you want to go keyboard and text only, that works too.

**The performance implication:** API turns for the LLM (plus possible tool calls), for voice input, and for voice response. I am seeing about 8-10 seconds for voice input to voice response — and for the enhanced memory, I'm okay with that.

**The cost implication:** API and token usage for everything. Figure that out based on your perceived amount of use.

**Platform note:** Since the frontend is a web browser talking to a Python service, it can run from just about anywhere — macOS, iPhones with Safari, etc. The downside of browser mode is speaker-phone use: you should run voice input in the **S** (speaker) mic mode so that barge-in is suppressed and the speaker doesn't pick up the audio output of the response.

---

### Architecture Overview

The project has two layers:

| Layer | File | Role |
|-------|------|------|
| **Browser UI** | `static/index.html` | Single-file HTML/CSS/JS — all rendering, SSE parsing, TTS/STT logic |
| **Python proxy** | `samaritan.py` | FastAPI server — auth gate, API key management, stream translation |

`samaritan.py` exists primarily to keep API keys out of the browser. It translates between the browser's expectations and whatever backend you wire up.

---

### Service Coupling Map

| Service | Where coupled | How to swap |
|---------|--------------|-------------|
| **llmem-gw** (LLM backend) | `samaritan.py` routes + `index.html` SSE parser | See [Swapping the LLM Backend](#swapping-the-llm-backend) below |
| **Deepgram** (STT) | `samaritan.py` WebSocket proxy (`/api/stt-proxy`), `index.html` AudioWorklet | Replace proxy + browser WS client |
| **Deepgram Aura** (TTS) | `samaritan.py` `/api/tts/deepgram`, `index.html` `ttsProviders.deepgram` | Implement new provider object + server route |
| **xAI Realtime** (TTS) | `samaritan.py` `/api/voice-token`, `index.html` `ttsProviders.xai` / `xai-persistent` | Implement new provider object + server route |
| **Inworld AI** (TTS) | `samaritan.py` `/api/tts/inworld`, `index.html` `ttsProviders.inworld` | Implement new provider object + server route |

---

### Swapping the LLM Backend

The frontend and backend share an internal SSE contract. As long as `samaritan.py` emits these events, `index.html` needs no changes:

| Event | Payload | Meaning |
|-------|---------|---------|
| `tok` | `{"type":"tok","text":"..."}` | One token/word to display |
| `flush` | `{"type":"flush","text":"..."}` | Intermediate checkpoint (tool call done, more coming); resets TTS buffer |
| `done` | `{"type":"done"}` | Turn complete — trigger TTS and re-open mic |
| `error` | `{"type":"error","text":"..."}` | Stream error |

To replace llmem-gw with a different LLM (OpenAI, Anthropic, Ollama, etc.), rewrite only `samaritan.py`:

1. **Submit route** (`POST /api/submit`) — translate `{text, client_id}` into your backend's request format and start a streaming response.
2. **Stream route** (`GET /api/stream/{client_id}`) — parse your backend's streaming format and emit `tok` / `flush` / `done` / `error` SSE events to the browser.
3. **Session management** — llmem-gw correlates a submitted request to its SSE stream via `client_id`. If your backend streams directly in the POST response body, you can simplify or eliminate the separate stream route.
4. **Health check** (`GET /api/health`) — point at your backend's health endpoint.

---

### iOS Safari Notes

- `AudioContext` must be created/unlocked during a direct user gesture
- `initAudioCtx()` called on every tap handler; also listens for `statechange` to auto-resume after iOS notification interruptions
- iOS kills the hardware mic when Safari backgrounds — on return, `visibilitychange` saves state to `sessionStorage` and triggers `location.reload()` to recover
- State persisted across reload: `micMode`, `ttsProvider`, `fullVoiceMode`, `SESSION_ID`
- Cookie persists in iOS PWA (WKWebView) across launches

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- CONTRIBUTING -->
## Contributing

Contributions are what make the open source community such an amazing place to learn, inspire, and create.
Any contributions you make are **greatly appreciated**.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- LICENSE -->
## License

Distributed under the MIT License. See `LICENSE.md` for more information.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- CONTACT -->
## Contact

Mark Jimenez - [@properTweetment](https://twitter.com/properTweetment) - xb12pilot@gmail.com

Project Link: [https://github.com/derezed88/samaritan-webfe](https://github.com/derezed88/samaritan-webfe)

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- ACKNOWLEDGMENTS -->
## Acknowledgments

### README template
* [othneildrew — Best-README-Template](https://github.com/othneildrew/Best-README-Template)
  — The structure and shield/badge conventions used in this README are based on this template.

### Visual design sources
* **Samaritan UI style** — inspired by the *Person of Interest* television series (CBS/Warner Bros., 2011-2016),
  created by Jonathan Nolan. The colour scheme (white radial gradient, red `#fe2d2d` accents, inverted
  black highlight), ALL-CAPS typography, animated triangle marker, and word-flash animation are a
  fan recreation for personal/educational use. No assets from the show are included.
* **Share Tech Mono** typeface — Carrois Apostrophe, licensed under the
  [SIL Open Font License 1.1](https://scripts.sil.org/OFL).
  Served via [Google Fonts](https://fonts.google.com/specimen/Share+Tech+Mono).
* **CSS scanline overlay technique** — adapted from public domain CSS snippets widely shared
  in the retro/CRT aesthetic community (no single original author identified).
* **Person of Interest web UI demo** — [phresh-it.hu/demos/poi-web-ui/](https://phresh-it.hu/demos/poi-web-ui/)
  — card designs for ASSET, THREAT, and other keyword pop-ups were adapted from this demo.

### Libraries & tools
* [FastAPI](https://fastapi.tiangolo.com/) — ASGI web framework (MIT License)
* [uvicorn](https://www.uvicorn.org/) — ASGI server (BSD License)
* [httpx](https://www.python-httpx.org/) — async HTTP client (BSD License)
* [python-dotenv](https://github.com/theskumar/python-dotenv) — `.env` file loader (BSD License)
* [Deepgram](https://deepgram.com) — streaming speech-to-text via WebSocket; proxied server-side to keep the API key out of the browser. Standard mode uses Flux (`flux-general-en`) on the v2 API for low-latency turn detection; Diarize mode uses Nova-3 (`nova-3`) on the v1 API with `diarize=true` for speaker identification.
* [Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API) — browser-native
  speech recognition used as ScriptProcessorNode fallback for iOS Safari AudioWorklet gaps (W3C specification, implemented by browser vendors)
* [Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API) — browser-native
  PCM audio scheduling for real-time TTS playback
* [xAI Realtime API](https://docs.x.ai/docs/realtime) — WebSocket-based AI voice synthesis
* [Inworld AI TTS API](https://docs.inworld.ai/docs/quickstart-tts) — Streaming AI voice synthesis
* [Pinggy](https://pinggy.io) — SSH-based HTTPS tunnel service

### AI assistance
* Interface design, architecture, and implementation assisted by
  [Claude](https://claude.ai) (Anthropic, claude-opus-4-6).

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- MARKDOWN LINKS & IMAGES -->
[contributors-shield]: https://img.shields.io/github/contributors/derezed88/samaritan-webfe.svg?style=for-the-badge
[contributors-url]: https://github.com/derezed88/samaritan-webfe/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/derezed88/samaritan-webfe.svg?style=for-the-badge
[forks-url]: https://github.com/derezed88/samaritan-webfe/network/members
[stars-shield]: https://img.shields.io/github/stars/derezed88/samaritan-webfe.svg?style=for-the-badge
[stars-url]: https://github.com/derezed88/samaritan-webfe/stargazers
[issues-shield]: https://img.shields.io/github/issues/derezed88/samaritan-webfe.svg?style=for-the-badge
[issues-url]: https://github.com/derezed88/samaritan-webfe/issues
[license-shield]: https://img.shields.io/github/license/derezed88/samaritan-webfe.svg?style=for-the-badge
[license-url]: https://github.com/derezed88/samaritan-webfe/blob/main/LICENSE.md
[linkedin-shield]: https://img.shields.io/badge/-LinkedIn-black.svg?style=for-the-badge&logo=linkedin&colorB=555
[linkedin-url]: https://linkedin.com/in/markajimenez
[Python-badge]: https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white
[Python-url]: https://python.org
[FastAPI-badge]: https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white
[FastAPI-url]: https://fastapi.tiangolo.com
[uvicorn-badge]: https://img.shields.io/badge/uvicorn-4B8BBE?style=for-the-badge&logoColor=white
[uvicorn-url]: https://www.uvicorn.org
[httpx-badge]: https://img.shields.io/badge/httpx-FF6B6B?style=for-the-badge&logoColor=white
[httpx-url]: https://www.python-httpx.org
