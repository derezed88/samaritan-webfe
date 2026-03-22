# Chat-GED UI (`/chat-ged`)

A GED exam prep tutoring interface served at `/chat-ged` by the same `samaritan.py` server.
Built on the same chat foundation as `/chat`, but specialized for GED study with subject
isolation, score tracking, progress dashboards, and Mermaid diagram rendering.

> **Note:** This is one of three independent frontends in the samaritan-webfe repo. Each is a
> self-contained single-file HTML/CSS/JS application with no shared code. If you want to use
> this GED UI separately, you would need to pull it apart from the repo — it relies on
> `samaritan.py` for auth, API key management, and SSE/WebSocket proxying. All three frontends
> are kept together as a frontend portfolio. See the [main README](../README.md) for the full picture.

## Accessing

Navigate to `https://<host>:8800/chat-ged` (or the Pinggy URL + `/chat-ged`). Auth uses the
same login cookie — log in once and all pages work. You can also reach it from the Samaritan
voice UI by typing `#mode chat-ged`.

## How It Works

On load, you see a subject selection screen with 5 GED subject cards. Pick a subject to start
chatting with the AI tutor. Each subject maintains its own conversation database and score data,
so switching subjects preserves your history in each.

## Features

### Subject Selection

**Five GED subjects**, each with its own isolated database:

| Subject | Model Key | Database |
|---------|-----------|----------|
| Mathematical Reasoning | `ged-math` | `gedmath` |
| RLA Reading | `ged-rla-reading` | `gedreading` |
| RLA Writing | `ged-rla-writing` | `gedwriting` |
| Science | `ged-science` | `gedscience` |
| Social Studies | `ged-social` | `gedsocial` |

**Two ways to select:**

1. **Subject cards** (center grid on load) — click any card to start. Auto-submits "Hi, let's start" to begin the conversation.
2. **Sidebar quick-switcher** (always available) — compact rows in the left sidebar. Active subject is highlighted.

Switching subjects runs `!reset` on the departing conversation (summarizes it), clears the chat display, and loads the new subject's database.

### Progress Dashboards (`#ged` commands)

Type these commands in the chat input to see your study progress:

#### `#ged` — Visual Dashboard (default)

Shows topic-level scores with a visual bar chart:

```
  Number Operations     ████████▒▒  80%  ✓ Strong
  Ratio & Proportion    █████▒▒▒▒▒  50%  → Building
  Geometry              ███▒▒▒▒▒▒▒  30%  ✗ Focus area

  Overall Readiness: 53%  — Need 75% to be exam ready
  Quiz Stats: 42 questions answered, 8 quiz sessions
```

Score thresholds:
- 75%+ = "Strong" (ready for exam)
- 50-74% = "Building"
- Below 50% = "Focus area"

#### `#ged all` — Cross-Subject Summary

Compares all 5 subjects side-by-side with per-subject progress bars, percentages, and an overall GED Readiness score.

#### `#ged scores` — Raw Data Table

Markdown table with Topic, Score, Correct, and Attempts columns for detailed analysis.

### Score Tracking

The backend tracks these metrics per topic:

- **Score** — float 0-1.0 (displayed as percentage)
- **Attempts** — total questions attempted
- **Correct** — number of correct answers

Stored in `{db}_ged_topic_scores` and `{db}_ged_quiz_results` tables, queried via `!db_query` through the agent.

**30+ topic labels** are mapped to human-readable names covering all GED subjects:

- **Math:** Number Operations, Ratio & Proportion, Expressions & Equations, Functions, Geometry, Statistics
- **RLA:** Informational Text, Literary Text, Main Idea, Evidence & Inference, Vocabulary in Context, Grammar & Usage, etc.
- **Science:** Life Science, Physical Science, Earth & Space Science, Experimental Design
- **Social Studies:** US History, Civics & Government, Economics, Geography & World, Historical Documents

### Mermaid Diagram Support

The AI tutor can generate visual charts and diagrams in responses:

- **Supported types:** xychart, pie, flowchart, graph, sequenceDiagram, gantt
- **Auto-fixing:** LLM output is automatically cleaned up:
  - `xychart-beta` converted to `xychart` (Mermaid v11 compatibility)
  - Typos corrected: `titie`/`titel` to `title`, `x-axs`/`y-axs` to `x-axis`/`y-axis`
  - Missing commas in arrays fixed
  - Special characters that break parsing removed
- **Error handling:** Failed charts show an inline error message without breaking the chat

### Markdown & Math Rendering

Same capabilities as the Chat UI:

- Built-in markdown renderer (bold, italic, lists, code blocks, tables)
- KaTeX math rendering for inline and display equations
- Answer choices (A/B/C/D) auto-formatted with line breaks

### Voice Output — Inworld TTS

- Toggle via the speaker button in the toolbar
- Speaks completed assistant responses
- Same Inworld streaming pipeline as Chat UI

### Voice Input — Deepgram STT

- Toggle via the mic button in the toolbar
- Deepgram Flux model via `/api/stt-proxy` WebSocket
- AudioWorklet capture with ScriptProcessorNode fallback
- Auto-submits on end-of-turn with confirmation beep

### Session Management

- `SESSION_ID` generated once per page load
- Each subject switch creates a new model/database context within the same session
- `!reset` summarizes the departing subject's conversation before switching

## Sidebar Differences from Chat UI

The generic chat sidebar elements are hidden:

- No "New Chat" button
- No "Chats" section or database list
- Instead: **GED Subjects** section with 5 clickable subject rows
- Active subject highlighted with accent color

## Configuration

Uses the same `.env` as the main Samaritan UI:

| Variable | Required for | Description |
|----------|-------------|-------------|
| `SAMARITAN_API_KEY` | Auth | Same login cookie as main UI |
| `INWORLD_API_KEY` | TTS | Inworld voice (only TTS option in chat-ged.html) |
| `DEEPGRAM_API_KEY` | STT | Deepgram Flux speech-to-text |

## API Routes Used

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/submit` | POST | Submit user message or `!command` |
| `/api/stream/{client_id}` | GET | SSE stream (tok/flush/done/error events) |
| `/api/tts/inworld` | POST | Inworld TTS streaming |
| `/api/stt-proxy` | WebSocket | Deepgram STT proxy |
