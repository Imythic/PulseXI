"""Orchestrator — runs one synthetic match through all six agents and
caches the result so the API layer stays thin.

Pipeline: Ingest -> Stats -> Explainer -> Verifier -> Render, then
Personalizer is applied on demand per viewer request (it needs to know
who's watching).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.agents.explainer import detect_triggers, explain
from backend.agents.ingest import ingest_event, new_match_state
from backend.agents.render import render_cue
from backend.agents.verifier import verify
from backend.data.generator import generate_match
from backend.models import Insight, MatchState, OverlayCue


@dataclass
class MatchBundle:
    state: MatchState
    insights: list[Insight] = field(default_factory=list)
    cues: list[OverlayCue] = field(default_factory=list)
    minute_snapshots: list[dict] = field(default_factory=list)


_MATCHES: dict[str, MatchBundle] = {}


def create_match(seed: int | None = None) -> MatchBundle:
    meta, players, events = generate_match(seed=seed)
    state = new_match_state(meta, players)
    bundle = MatchBundle(state=state)

    current_minute = -1
    for event in events:
        ingest_event(state, event)
        for trigger in detect_triggers(state):
            insight = explain(trigger, state)
            insight = verify(insight, trigger, state)
            bundle.insights.append(insight)
            bundle.cues.append(render_cue(insight))

        if event.minute != current_minute:
            current_minute = event.minute
            bundle.minute_snapshots.append(_snapshot(state))

    bundle.minute_snapshots.append(_snapshot(state))  # final state
    _MATCHES[meta.match_id] = bundle
    return bundle


def get_match(match_id: str) -> MatchBundle | None:
    return _MATCHES.get(match_id)


def _snapshot(state: MatchState) -> dict:
    return {
        "minute": state.events_processed[-1].minute if state.events_processed else 0,
        "momentum": state.momentum,
        "team_stats": {tid: ts.model_dump() for tid, ts in state.team_stats.items()},
        "player_stats": {pid: ps.model_dump() for pid, ps in state.player_stats.items()},
    }
