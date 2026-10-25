# 💠 PulseXI — Synthetic Match Insights Engine

**Built for Microsoft x Premier League: Inside the Game Developer Hackathon**

PulseXI turns a raw stream of synthetic football events into a live broadcast overlay feed *and* a genuinely personalized fan experience — from the same match, at the same time, through five purpose-built AI agents.

## Elevator pitch

Every match generates thousands of events, but only a handful of moments actually matter — and *why* they matter is almost never explained to the viewer. PulseXI ingests a synthetic, football-realistic event stream (passes, shots, tackles, pressure, possession changes) and runs it through a five-agent pipeline that interprets the raw data into real football statistics, explains why a given moment matters tactically or narratively, renders that explanation as a machine-readable broadcast overlay cue, and finally reshapes the same insight for three different audiences — a data-hungry analyst, a casual fan following their club, and a viewer who only cares about one player's game. One pipeline, every fan gets a match made for them.

## The 5-agent pipeline

```
Synthetic events ──▶ Ingest Agent ──▶ Stats Agent ──▶ Explainer Agent ──▶ Render Agent ──▶ Personalizer Agent
                      (feed intake)   (derived stats)  (why it matters)   (overlay cue)    (per-viewer feed)
                                            │                │
                                            └──── shared MatchState ──────┘
```

- **Ingest Agent** (`backend/agents/ingest.py`) — the pipeline's front door. Takes the next raw event and hands it to Stats. Deliberately dumb: no interpretation logic, so the handoff is explicit and testable in isolation.
- **Stats Agent** (`backend/agents/stats.py`) — pure, deterministic aggregation. Possession %, pass accuracy, shot danger, and a derived **control vs. chaos** score per team, updated incrementally as events arrive.
- **Explainer Agent** (`backend/agents/explainer.py`) — detects insight-worthy moments (goals, fast shots, pressure spikes, tackle streaks, possession milestones, momentum swings) and explains *why* they matter via an LLM call to **GitHub Models** (free tier, OpenAI-compatible, auth'd with a `GITHUB_TOKEN`). If the LLM is slow or unreachable, a **template-based fallback agent takes over automatically** — the pipeline never stalls on a network call. This explicit recovery path is demonstrated live: every insight is tagged with `source: "llm"` or `"template"`.
- **Render Agent** (`backend/agents/render.py`) — converts an insight into a small, timestamped, machine-readable overlay cue (`{minute, second, type, title, body, duration_s, style}`) rather than pixels. This mirrors how a real broadcast graphics tool would consume the feed in production — our frontend is just a reference renderer for the same contract.
- **Personalizer Agent** (`backend/agents/personalizer.py`) — the final stage. Same insight feed, three different experiences: **Analyst** (every insight, full detail), **Fan** (highlights only, optionally filtered to a favorite club), **Player Focus** (only moments involving one chosen player). Also handles multi-language headlines/narratives (English baseline, LLM-translated when online, with a deterministic phrasebook fallback offline).

## What's on screen

- An animated 2D pitch tracking ball/possession position in sync with the match clock
- Broadcast-style overlay cards (lower-thirds, stat bugs, milestone cards, a live momentum bar) appearing exactly when each insight fires
- A live personalization panel: switch Analyst / Fan / Player Focus, pick a favorite club or player, switch language — and watch the *same match* become a different feed in real time
- Playback controls (play/pause, speed, scrubber) over a precomputed match timeline, plus a paced WebSocket replay (`/ws/match/{id}/live`) that demonstrates the same pipeline ingesting events as they'd arrive from a genuinely live feed

## Tech stack

- **Backend:** Python + FastAPI, pydantic v2 schemas shared across every agent
- **AI:** GitHub Models (`openai/gpt-4o-mini` by default) for narrative explanation and translation, via the OpenAI-compatible client — no Azure subscription required
- **Frontend:** vanilla HTML/CSS/JS (no build step), animated pitch + overlay renderer + personalization UI
- **Data:** a from-scratch synthetic match generator (`backend/data/generator.py`) — fictional clubs, fictional players, procedurally generated passes/shots/tackles/pressure/possession events across a full 90-minute match. No real Premier League data of any kind.

## Running it locally

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

set GITHUB_TOKEN=<a GitHub token>   # optional — enables live LLM narration + translation
uvicorn main:app --host 0.0.0.0 --port 8010
```

Then open **http://localhost:8010** — the backend serves the frontend directly, so there's nothing else to run. Without `GITHUB_TOKEN` set, every insight is generated by the template fallback agent instead (still fully functional, just less varied prose).

## Project structure

```
PulseXI/
├── backend/
│   ├── agents/
│   │   ├── ingest.py          # Ingest Agent
│   │   ├── stats.py           # Stats Agent
│   │   ├── explainer.py       # Explainer Agent (LLM + template fallback)
│   │   ├── render.py          # Render Agent
│   │   └── personalizer.py    # Personalizer Agent
│   ├── data/
│   │   └── generator.py       # synthetic match generator
│   ├── models.py               # shared pydantic schemas (MatchState, Insight, OverlayCue, ...)
│   ├── orchestrator.py         # runs one match through the full pipeline, caches the result
│   ├── main.py                  # FastAPI app: REST + WebSocket + static frontend
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── css/style.css
    └── js/app.js
```

## Why this fits the brief

The brief asks for one pipeline across five stages — ingest, interpret, explain, render, personalize — and that's the literal file layout above, not just a conceptual mapping. Agentic Design is demonstrated through explicit distinct agent roles, a shared `MatchState` object as the coordination point, and a real failure-recovery handoff (LLM → template) rather than a single monolithic prompt. Real-World Impact comes from the overlay cue schema being structured for production broadcast tooling, not just a demo UI. And Personalization is proven live in the UI, not asserted in the README — switch modes and watch the feed change.
