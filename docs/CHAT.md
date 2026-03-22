# Chat UI (`/chat`)

A Claude-style scrolling chat interface served at `/chat` by the same `samaritan.py` server.
It uses the same llmem-gw backend and auth cookie as the Samaritan voice UI, but presents
conversations as a familiar scrolling chat transcript rather than the word-flash animation.

> **Note:** This is one of three independent frontends in the samaritan-webfe repo. Each is a
> self-contained single-file HTML/CSS/JS application with no shared code. If you want to use
> this chat UI separately, you would need to pull it apart from the repo — it relies on
> `samaritan.py` for auth, API key management, and SSE/WebSocket proxying. All three frontends
> are kept together as a frontend portfolio. See the [main README](../README.md) for the full picture.

## When to Use

- You want a persistent, scrollable conversation history rather than the Samaritan animation display
- You are doing math or technical work and want LaTeX/formula rendering
- You prefer keyboard/text-only interaction without the voice controls
- You want to inspect or resume short-term memory from a previous session

## Accessing

Navigate to `https://<host>:8800/chat` (or the Pinggy URL + `/chat`). Auth uses the same login
cookie as the main UI — log in once and all pages work.

## Features

### Chat Layout

- Scrolling user/assistant bubble layout with markdown rendering
- Light/dark theme — auto-selected based on time of day (7am-8pm = light, else dark)
- Mobile-responsive at 600px breakpoint: sidebar becomes a slide-out overlay with hamburger menu
- Empty state with centered header when no messages exist

### Sidebar — Database Browser

The left sidebar shows all available llmem-gw databases:

- Click a database to switch — chat history clears and memory from the new database loads
- Protected databases (mymcp, qwen) show a lock icon and cannot be deleted
- User-created databases show a trash icon on hover for deletion
- Active database is highlighted in the accent color
- "New Chat" button at top creates a fresh session

### Model Selection

A dropdown in the toolbar below the input area lets you switch the active LLM model:

- Dynamically populated from `!model` command output
- Disabled models are filtered out
- On change, runs `!model {key}` to switch the llmem-gw session

### Markdown Rendering

Built-in markdown renderer (no external library) handles:

- Bold, italic, bold-italic (`**`, `*`, `***`)
- Headings (`#`, `##`, `###`)
- Ordered and unordered lists
- Code blocks (triple backtick) with monospace styling
- Inline code (single backtick)
- Pipe tables with auto-detection
- Hybrid tables (pipe header + tab-separated body)
- Space-aligned text tables
- Answer choices (A/B/C/D) with line breaks

### LaTeX / Math Rendering

[KaTeX](https://katex.org/) auto-render with preprocessing:

- Delimiters: `\(...\)` for inline, `\[...\]` and `$$...$$` for display math
- `preprocessMath()` wraps bare operators (`times`, `div`, `cdot`, `pm`, etc.) and exponents into delimiters
- Fixes JSON `\t`-escape corruption of `\times`
- Single `$` delimiters are only converted if content looks like LaTeX (contains `\`, `{`, `^`, `_`)

### Memory Display on Load

When you switch to a database, `loadMemoryTurns()` fetches short-term memory via `!db_query` SQL and renders each past turn as a proper user/assistant bubble — not a raw dump. Directive entries are skipped.

### Voice Output — Inworld TTS

- Toggle via the speaker button in the toolbar
- Speaks the full assistant response on turn completion
- Streaming NDJSON from `/api/tts/inworld` — base64 WAV chunks with 44-byte RIFF header stripped
- Audio pipeline: Web Audio API with `scheduleAudioChunk()` for gapless playback
- AbortController cancels ongoing TTS on new message

### Voice Input — Deepgram STT

- Toggle via the mic button in the toolbar
- WebSocket connection to `/api/stt-proxy` (Deepgram Flux model, v2 API)
- Audio capture via AudioWorklet with ScriptProcessorNode fallback
- `StartOfTurn`: clears input preview
- `Update`: shows interim results in italic
- `EndOfTurn`: finalizes input, plays 880Hz confirmation beep, auto-submits
- PCM buffered to ~80ms chunks (Flux requirement)

### Session Management

- `SESSION_ID` generated once on page load, stored in `sessionStorage` (key: `chat_session_id`)
- Reused for all turns — page reload starts a new session
- Separate `client_id` streams for non-interactive commands (model switch, DB queries)

### SMS Notifications

Polls `/api/sms-notifications` every 4 seconds for pending SMS notifications from the llmem-gw session.

## Configuration

Chat UI uses the same `.env` configuration as the main Samaritan UI. The relevant keys:

| Variable | Required for | Description |
|----------|-------------|-------------|
| `SAMARITAN_API_KEY` | Auth | Same login cookie as main UI |
| `INWORLD_API_KEY` | TTS | Inworld voice provider (the only TTS option in chat.html) |
| `DEEPGRAM_API_KEY` | STT | Deepgram Flux speech-to-text |

## API Routes Used

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/submit` | POST | Submit user message |
| `/api/stream/{client_id}` | GET | SSE stream (tok/flush/done/error events) |
| `/api/tts/inworld` | POST | Inworld TTS streaming |
| `/api/stt-proxy` | WebSocket | Deepgram STT proxy |
| `/api/sms-notifications` | GET | SMS notification polling |
