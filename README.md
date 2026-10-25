# 💠 PulseXI — Synthetic Match Insights Engine

**Built for Microsoft x Premier League: Inside the Game Developer Hackathon**

PulseXI turns a raw stream of synthetic football events into a live, **fact-checked** broadcast overlay feed *and* a genuinely personalized, **accessible** fan experience — from the same match, at the same time, through seven purpose-built AI agents.

## Elevator pitch

Every match generates thousands of events, but only a handful of moments actually matter — and *why* they matter is almost never explained to the viewer, and when an LLM is asked to explain it, there's no guarantee the numbers it says are even true. PulseXI ingests a synthetic, football-realistic event stream (passes, shots, tackles, pressure, possession changes) and runs it through a seven-agent pipeline that interprets the raw data into real football statistics, explains why a given moment matters tactically or narratively, **verifies every numeric claim against the computed match data before it's allowed on screen**, renders the result as a machine-readable broadcast overlay cue, reshapes the same insight for three different audiences — a data-hungry analyst, a casual fan following their club, and a viewer who only cares about one player's game — and composes an automated full-time recap at the final whistle. All of it with an optional **spoken audio commentary track** for blind and partially-sighted fans. One pipeline, every fan gets a match made for them, and nothing reaches the screen that isn't true.

## The 7-agent pipeline

```
Synthetic events ──▶ Ingest ──▶ Stats ──▶ Explainer ──▶ Verifier ──▶ Render ──▶ Personalizer ──▶ Recap
                     (intake)  (derived   (why it        (fact-      (overlay   (per-viewer       (full-time
                                 stats)     matters)       check)      cue)       feed + audio)      summary)
                                    │           │              │
                                    └───────── shared MatchState ─────┘
```

- **Ingest Agent** (`backend/agents/ingest.py`) — the pipeline's front door. Takes the next raw event and hands it to Stats. Deliberately dumb: no interpretation logic, so the handoff is explicit and testable in isolation.
- **Stats Agent** (`backend/agents/stats.py`) — pure, deterministic aggregation. Possession %, pass accuracy, shot danger, goals, and a derived **control vs. chaos** score per team, updated incrementally as events arrive.
- **Explainer Agent** (`backend/agents/explainer.py`) — detects insight-worthy moments (goals, fast shots, pressure spikes, tackle streaks, possession milestones, momentum swings) and explains *why* they matter via an LLM call to **GitHub Models** (free tier, OpenAI-compatible, auth'd with a `GITHUB_TOKEN`). If the LLM is slow or unreachable, a **template-based fallback agent takes over automatically** — the pipeline never stalls on a network call.
- **Verifier Agent** (`backend/agents/verifier.py`) — the second, sharper failure-recovery path: *"the LLM responded, but is it right?"* Every percentage and speed claim in the LLM's text is extracted and cross-checked against the actual numbers in `MatchState`, matched to the correct stat by context (a "possession" claim is checked against possession %, not pass accuracy — a naive check gets fooled by coincidental overlaps). If a claim doesn't hold up, the Verifier rejects it and substitutes the always-correct template explanation, tagging the insight `source: "llm_corrected"`. Every insight carries a `verified` flag and a human-readable `verification_note` all the way to the UI.
- **Render Agent** (`backend/agents/render.py`) — converts a verified insight into a small, timestamped, machine-readable overlay cue (`{minute, second, type, title, body, duration_s, style, verified}`) rather than pixels. This mirrors how a real broadcast graphics tool would consume the feed in production — our frontend is just a reference renderer for the same contract.
- **Personalizer Agent** (`backend/agents/personalizer.py`) — same verified insight feed, three different experiences: **Analyst** (every insight, full detail), **Fan** (highlights only, optionally filtered to a favorite club), **Player Focus** (only moments involving one chosen player). Handles multi-language headlines/narratives (English baseline, LLM-translated when online, deterministic phrasebook fallback offline), and every card can be read aloud via the browser's speech synthesis — the accessibility track, not an afterthought bolted onto the UI.
- **Recap Agent** (`backend/agents/recap.py`) — runs once, at full time. Selects the match's highest-importance verified insights (goals always included), and composes a short automated recap — via LLM when available, constrained to only the supplied facts, or deterministically stitched together from the already-verified insight text when it's not. Either path is incapable of introducing a number that wasn't already checked.

## What's on screen

- A genuine 3D WebGL pitch (Three.js), not a flat diagram with a camera trick — real geometry, lighting, and shadows, with a freely orbitable broadcast "tactical cam" (drag to rotate, scroll to zoom), real markings (penalty arcs, goal mouths, corner arcs), a stadium floodlight glow, and a live scoreline in the topbar that updates the moment a goal lands
- All 22 players rendered as live, numbered 3D markers in formation (not just a ball dot), easing toward the ball and drifting naturally every frame; the player currently on the ball gets a glowing highlight ring
- Click any player for a live stat card — passes, distance covered, top speed, shots, tackles — updating in real time as the match plays, correctly positioned via live 3D-to-screen projection as the camera moves
- Manual zoom controls, a camera reset button, plus a **Follow Ball** mode that smoothly tracks the ball's live position
- Broadcast-style overlay cards (lower-thirds, stat bugs, milestone cards, a live momentum bar) appearing exactly when each insight fires, each carrying a **✓ Verified** or **~ Corrected** badge so the verification step is visible, not just logged
- A live personalization panel: switch Analyst / Fan / Player Focus, pick a favorite club or player, switch language — and watch the *same match* become a different feed in real time
- An **Audio commentary** toggle (🔊) that speaks every overlay moment aloud as it happens, plus a per-card listen button in the personalized feed — built for blind and partially-sighted fans, not just a visual demo
- An automated **full-time recap** modal — triggers automatically when playback reaches the end, or on demand via the 🏁 Recap button — with its own verified badge and listen button
- Playback controls (play/pause, speed, scrubber) over a precomputed match timeline, plus a paced WebSocket replay (`/ws/match/{id}/live`) that demonstrates the same pipeline ingesting events as they'd arrive from a genuinely live feed

## Tech stack

- **Backend:** Python + FastAPI, pydantic v2 schemas shared across every agent
- **AI:** GitHub Models (`openai/gpt-4o-mini` by default) for narrative explanation and translation, via the OpenAI-compatible client — no Azure subscription required
- **Frontend:** vanilla HTML/CSS/JS (ES modules, no build step), [Three.js](https://threejs.org/) (via CDN import map) for the 3D pitch scene + overlay renderer + personalization UI
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
│   │   ├── verifier.py        # Verifier Agent (fact-checks LLM claims)
│   │   ├── render.py          # Render Agent
│   │   ├── personalizer.py    # Personalizer Agent
│   │   └── recap.py           # Recap Agent (full-time summary)
│   ├── data/
│   │   └── generator.py       # synthetic match generator
│   ├── models.py               # shared pydantic schemas (MatchState, Insight, OverlayCue, ...)
│   ├── orchestrator.py         # runs one match through the full pipeline, caches the result
│   ├── main.py                  # FastAPI app: REST + WebSocket + static frontend
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── css/style.css
    └── js/
        ├── app.js       # UI state, playback, personalization, recap
        └── pitch3d.js   # Three.js scene: pitch, players, camera, raycasting
```

## Why this fits the brief

The brief asks for one pipeline across five stages — ingest, interpret, explain, render, personalize — and that's the literal file layout above, plus two agents we added because they're implicit in the brief's own language: Verifier, because *trustworthy* explanation is implicit in "explainable match intelligence" and most explainable-AI demos skip it; and Recap, because the brief explicitly asks for "automated match recaps," not just live moment-by-moment insights. Agentic Design is demonstrated through seven explicit, distinct agent roles, a shared `MatchState` object as the single coordination point, and two separate, concrete failure-recovery handoffs — not one: "LLM unreachable → template agent takes over" and "LLM reachable but wrong → Verifier agent rejects and corrects it." Real-World Impact comes from the overlay cue schema being structured for production broadcast tooling, not just a demo UI, and from accessibility (audio commentary) being a first-class output, not a stretch goal. And Personalization is proven live in the UI, not asserted in the README — switch modes and watch the feed change.
