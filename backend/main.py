"""
PulseXI - Synthetic Match Insights Engine
FastAPI backend: exposes the 5-agent pipeline (Ingest -> Stats -> Explainer
-> Render -> Personalizer) as a small JSON API, plus a paced WebSocket
replay for the "live" demo view. Serves the static frontend too, so the
whole thing runs as one deployable service.
"""
from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.agents.personalizer import build_feed
from backend.models import PersonaMode, PersonalizedFeedRequest
from backend.orchestrator import create_match, get_match

app = FastAPI(title="PulseXI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "PulseXI API"}


@app.post("/api/match/new")
def new_match(seed: int | None = Query(default=None)):
    bundle = create_match(seed=seed)
    state = bundle.state
    return {
        "match_id": state.meta.match_id,
        "meta": state.meta.model_dump(),
        "players": {pid: p.model_dump() for pid, p in state.players.items()},
        "event_count": len(state.events_processed),
        "insight_count": len(bundle.insights),
    }


@app.get("/api/match/{match_id}/timeline")
def match_timeline(match_id: str):
    bundle = get_match(match_id)
    if not bundle:
        raise HTTPException(404, "match not found")
    state = bundle.state
    return {
        "meta": state.meta.model_dump(),
        "players": {pid: p.model_dump() for pid, p in state.players.items()},
        "events": [e.model_dump() for e in state.events_processed],
        "insights": [i.model_dump() for i in bundle.insights],
        "cues": [c.model_dump() for c in bundle.cues],
        "minute_snapshots": bundle.minute_snapshots,
        "final_team_stats": {tid: ts.model_dump() for tid, ts in state.team_stats.items()},
    }


@app.get("/api/match/{match_id}/personalize")
def personalize(
    match_id: str,
    mode: PersonaMode = Query(default=PersonaMode.FAN),
    favorite_team_id: str | None = Query(default=None),
    favorite_player_id: str | None = Query(default=None),
    language: str = Query(default="en"),
):
    bundle = get_match(match_id)
    if not bundle:
        raise HTTPException(404, "match not found")
    req = PersonalizedFeedRequest(
        mode=mode,
        favorite_team_id=favorite_team_id,
        favorite_player_id=favorite_player_id,
        language=language,
    )
    cards = build_feed(bundle.insights, bundle.state, req)
    return {"mode": mode, "language": language, "cards": [c.model_dump() for c in cards]}


@app.websocket("/ws/match/{match_id}/live")
async def live_replay(websocket: WebSocket, match_id: str, speed: float = 20.0):
    """Paced replay of the precomputed event/cue timeline, to demo the
    pipeline as it would feel ingesting a truly live feed. speed=20 means
    20 simulated match-seconds pass per real second."""
    await websocket.accept()
    bundle = get_match(match_id)
    if not bundle:
        await websocket.send_json({"type": "error", "message": "match not found"})
        await websocket.close()
        return

    events = bundle.state.events_processed
    cues = bundle.cues
    cue_idx = 0
    try:
        for event in events:
            t = event.minute * 60 + event.second
            await websocket.send_json({"type": "event", "data": event.model_dump(), "clock": t})
            while cue_idx < len(cues) and (cues[cue_idx].minute * 60 + cues[cue_idx].second) <= t:
                await websocket.send_json({"type": "cue", "data": cues[cue_idx].model_dump()})
                cue_idx += 1
            await asyncio.sleep(1.0 / speed)
        await websocket.send_json({"type": "end"})
    except WebSocketDisconnect:
        pass


FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
