"""Ingest Agent — the pipeline's front door.

Responsible only for taking the next raw event(s) off the match feed and
handing them to the Stats Agent to fold into shared state. Keeping this
agent dumb-on-purpose (no interpretation logic) is what makes the handoff
to Stats explicit and testable in isolation.
"""
from __future__ import annotations

from backend.agents.stats import update_stats
from backend.models import MatchEvent, MatchMeta, MatchState, Player


def new_match_state(meta: MatchMeta, players: dict[str, Player]) -> MatchState:
    return MatchState(meta=meta, players=players)


def ingest_event(state: MatchState, event: MatchEvent) -> MatchEvent:
    """Advance the match by exactly one event. Returns the event for downstream agents."""
    state.events_processed.append(event)
    update_stats(state, event)
    return event


def ingest_batch(state: MatchState, events: list[MatchEvent]) -> list[MatchEvent]:
    return [ingest_event(state, e) for e in events]
