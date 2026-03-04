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
    A <em>Person of Interest</em>-themed web front-end for the agent-mcp AI service.
    Streams LLM responses word-by-word in the Samaritan UI style with full voice I/O — speak to Samaritan and hear it speak back.
    <br />
    <a href="https://github.com/derezed88/kaliLinuxNWScripts"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://github.com/derezed88/kaliLinuxNWScripts/issues/new?labels=bug&template=bug-report---.md">Report Bug</a>
    &middot;
    <a href="https://github.com/derezed88/kaliLinuxNWScripts/issues/new?labels=enhancement&template=feature-request---.md">Request Feature</a>
  </p>
</div>



<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li><a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li><a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#configuration">Configuration</a></li>
    <li><a href="#remote-access">Remote Access via Pinggy</a></li>
    <li><a href="#security">Security</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>



<!-- ABOUT THE PROJECT -->
## About The Project

`samaritan-webfe` is a Python web service that provides a browser-based AI chat client styled
after the **Samaritan** interface from the CBS television series *Person of Interest* (2011–2016).
It acts as a front-end proxy to the [agent-mcp](https://github.com/derezed88/kaliLinuxNWScripts)
AI agent service, streaming responses token-by-token in the show's distinctive word-flash animation style.

**Key features:**

- Samaritan visual style — white radial-gradient background, ALL-CAPS monospace font, red accent triangle, scanline overlay
- Word-by-word token animation (one word flashes center-screen at a time); longer responses use a typewriter terminal panel
- **Voice input** via the Web Speech API — auto-submits on recognition, mic restarts automatically after each response
- **Voice output (TTS)** via a pluggable provider architecture — switch between xAI Realtime and Inworld AI (and future providers) with a single tap at runtime
- **Full-voice hands-free loop** — speak a prompt, hear the response, mic reopens automatically for the next turn; works continuously for multiple turns
- Keyboard mode for typed input — reopens automatically after each response; typed prompts also get spoken responses in full-voice mode
- Configurable idle screen: returns to `CONNECTION ESTABLISHED.` after inactivity
- HTTP Basic Auth gate — browser credential dialog prevents unauthorized access before the page loads
- Dual-port server: HTTPS on 8800 (local, mic-capable) and HTTP on 8801 (pinggy tunnel endpoint)
- Self-signed TLS certificate auto-generated on first start for local HTTPS

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
- [agent-mcp](https://github.com/derezed88/kaliLinuxNWScripts/tree/main/mymcp) running on the same host (default port 8767)
- `openssl` (for self-signed cert generation — usually pre-installed on Linux/macOS)
- At least one voice provider API key (required for FULL VOICE mode — see [Configuration](#configuration))

### Installation

1. Clone the repo
   ```sh
   git clone https://github.com/derezed88/kaliLinuxNWScripts.git
   cd kaliLinuxNWScripts/samaritan-webfe
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
   - **Pinggy tunnel:** `https://<assigned-pinggy-url>` (see [Remote Access](#remote-access))

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- USAGE EXAMPLES -->
## Usage

Once the page loads, the browser prompts for credentials (HTTP Basic Auth).
Enter anything as the username and your `SAMARITAN_API_KEY` as the password.
The browser caches this for the session — you will not be prompted again until the tab is closed.

**Voice input (LIVE mode):**
1. Tap the **MIC** button — the label changes to **LIVE** and the interface listens
2. Speak your query — it auto-submits when you finish speaking
3. The response streams word-by-word on screen
4. When the response finishes, the mic restarts automatically for the next turn

**Full-voice hands-free mode (FULL VOICE + LIVE):**
1. Tap **VOICE: XAI** (or **VOICE: INWORLD**) to select the TTS provider for this session
2. Tap **FULL VOICE** to enable spoken responses, then tap **MIC** to start listening
3. Speak your query — Samaritan responds in text *and* speaks the response aloud via AI voice
4. After the audio finishes, the mic reopens automatically — the loop continues hands-free indefinitely
5. Works over remote access (Pinggy tunnel) from any device with a browser and microphone

> **Note:** Voice responses require at least one provider API key in `.env` (see [Configuration](#configuration)).
> Tap the **VOICE:** button in the control bar to switch providers at any time without reloading.
> Supported browsers: Chrome, Edge, Safari (iOS 14.5+). Firefox does not support the Web Speech API.

**Keyboard mode:**
1. Tap the **⌫** button to open the text input
2. Type your query and press **Enter** or tap **SEND**
3. The input panel closes while the response streams, then reopens ready for the next message
4. If FULL VOICE is active, typed prompts also receive a spoken response

**Idle behaviour:**
After `IDLE_TIMEOUT_SEC` seconds (default 30, configurable at the top of the JS in `static/index.html`),
the screen clears and returns to the blinking `CONNECTION ESTABLISHED.` state.

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
| `SAMARITAN_API_KEY` | Yes | Access password for the web UI (HTTP Basic Auth). Set to any strong secret string. |
| `AGENT_MCP_API_KEY` | No | Bearer token forwarded to agent-mcp. Leave blank if agent-mcp has no key set. |
| `AGENT_MCP_URL` | No | Base URL of the agent-mcp service. Default: `http://localhost:8767`. |
| `XAI_API_KEY` | For xAI voice | xAI API key. Used server-side only to mint ephemeral WebSocket tokens — never sent to the browser. Get one at [console.x.ai](https://console.x.ai/). |
| `INWORLD_API_KEY` | For Inworld voice | Inworld API key (Base64-encoded credential from the Inworld Portal under Settings → API Keys). Used server-side only — never sent to the browser. |

The idle timeout, word animation timings, and voice provider settings are constants at the top
of the JavaScript block in `static/index.html`:

```js
const IDLE_TIMEOUT_SEC        = 30;                  // seconds before screen returns to idle message
const WORD_FADE               = 180;                 // ms opacity transition per word
const WORD_HOLD               = 380;                 // ms each word is visible
const WORD_GAP                = 60;                  // ms gap between words
const LONG_RESPONSE_THRESHOLD = 10;                  // words — responses >= this use terminal typewriter display
let   TTS_PROVIDER            = 'xai';               // default voice provider: 'xai' | 'inworld'
const XAI_VOICE               = 'ara';               // xAI voice: Eve | Ara | Rex | Sal | Leo
const INWORLD_VOICE           = 'Evelyn';            // Inworld voice name
const INWORLD_MODEL           = 'inworld-tts-1.5-max'; // Inworld model ID
```

### Voice Providers

Samaritan uses a pluggable TTS provider architecture. The active provider can be switched at runtime via the **VOICE:** button in the control bar, or set permanently via `TTS_PROVIDER` in the JS config block.

| Provider | Button label | API key required | Notes |
|----------|-------------|-----------------|-------|
| **xAI Realtime** | `VOICE: XAI` | `XAI_API_KEY` | WebSocket streaming; ephemeral token minted server-side. Voices: Eve, Ara, Rex, Sal, Leo. |
| **Inworld AI** | `VOICE: INWORLD` | `INWORLD_API_KEY` | Batch HTTP; MP3 decoded by browser. Voice: configurable via `INWORLD_VOICE`. |

To add a new provider, implement the `speak(text, token, onDone, onError)` / `stop()` interface in the `ttsProviders` registry in `static/index.html` and add the corresponding server-side proxy route in `samaritan.py` if the API key must stay server-side.

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
the `SAMARITAN_API_KEY` Basic Auth prompt is the access gate.

| Port | Protocol | Purpose |
|------|----------|---------|
| 8800 | HTTPS    | Local network access (self-signed cert) |
| 8801 | HTTP     | Pinggy tunnel endpoint (pinggy provides TLS) |

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- SECURITY -->
## Security

- **HTTP Basic Auth** is enforced on every route including `/`. Unauthorized clients never see the page.
- The `SAMARITAN_API_KEY` is the password. Username is ignored.
- The browser caches credentials per-session (cleared on tab close).
- `AGENT_MCP_API_KEY` is a separate server-side secret forwarded to agent-mcp — it is never exposed to the browser.
- The self-signed cert on port 8800 will trigger a browser warning on first visit; accept it once. It is valid for 10 years for the configured local IP.
- When using the Pinggy tunnel, the obscure URL provides minimal protection on its own — always set a strong `SAMARITAN_API_KEY`.

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

Distributed under the MIT License. See `LICENSE.txt` for more information.

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
* **Samaritan UI style** — inspired by the *Person of Interest* television series (CBS/Warner Bros., 2011–2016),
  created by Jonathan Nolan. The colour scheme (white radial gradient, red `#fe2d2d` accents, inverted
  black highlight), ALL-CAPS typography, animated triangle marker, and word-flash animation are a
  fan recreation for personal/educational use. No assets from the show are included.
* **Share Tech Mono** typeface — Carrois Apostrophe, licensed under the
  [SIL Open Font License 1.1](https://scripts.sil.org/OFL).
  Served via [Google Fonts](https://fonts.google.com/specimen/Share+Tech+Mono).
* **CSS scanline overlay technique** — adapted from public domain CSS snippets widely shared
  in the retro/CRT aesthetic community (no single original author identified).

### Libraries & tools
* [FastAPI](https://fastapi.tiangolo.com/) — ASGI web framework (MIT License)
* [uvicorn](https://www.uvicorn.org/) — ASGI server (BSD License)
* [httpx](https://www.python-httpx.org/) — async HTTP client (BSD License)
* [python-dotenv](https://github.com/theskumar/python-dotenv) — `.env` file loader (BSD License)
* [Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API) — browser-native
  speech recognition (W3C specification, implemented by browser vendors)
* [Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API) — browser-native
  PCM audio scheduling for real-time TTS playback
* [xAI Realtime API](https://docs.x.ai/docs/realtime) — WebSocket-based AI voice synthesis
* [Inworld AI TTS API](https://docs.inworld.ai/docs/quickstart-tts) — Batch HTTP AI voice synthesis
* [Pinggy](https://pinggy.io) — SSH-based HTTPS tunnel service

### AI assistance
* Interface design, architecture, and implementation assisted by
  [Claude](https://claude.ai) (Anthropic, claude-sonnet-4-6).

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- MARKDOWN LINKS & IMAGES -->
[contributors-shield]: https://img.shields.io/github/contributors/derezed88/kaliLinuxNWScripts.svg?style=for-the-badge
[contributors-url]: https://github.com/derezed88/kaliLinuxNWScripts/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/derezed88/kaliLinuxNWScripts.svg?style=for-the-badge
[forks-url]: https://github.com/derezed88/kaliLinuxNWScripts/network/members
[stars-shield]: https://img.shields.io/github/stars/derezed88/kaliLinuxNWScripts.svg?style=for-the-badge
[stars-url]: https://github.com/derezed88/kaliLinuxNWScripts/stargazers
[issues-shield]: https://img.shields.io/github/issues/derezed88/kaliLinuxNWScripts.svg?style=for-the-badge
[issues-url]: https://github.com/derezed88/kaliLinuxNWScripts/issues
[license-shield]: https://img.shields.io/github/license/derezed88/kaliLinuxNWScripts.svg?style=for-the-badge
[license-url]: https://github.com/derezed88/kaliLinuxNWScripts/blob/master/LICENSE.txt
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
