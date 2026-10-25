"""Explainer Agent — the "why it matters" stage.

Scans newly ingested events against the shared MatchState for moments
worth narrating, then explains them via an LLM (GitHub Models, free tier).
If the LLM is unavailable or slow, a template-based fallback agent takes
over so the pipeline never stalls waiting on a network call — this is the
explicit failure-recovery handoff in the agent chain.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from backend.models import EventType, Insight, MatchEvent, MatchState

GITHUB_MODELS_BASE_URL = "https://models.github.ai/inference"
DEFAULT_MODEL = os.environ.get("PULSEXI_MODEL", "openai/gpt-4o-mini")

FAST_SHOT_KMH = 108.0
HIGH_PRESSURE = 0.85
TACKLE_STREAK = 3
TACKLE_WINDOW = 8


@dataclass
class Trigger:
    category: str
    importance: float
    event: MatchEvent
    note: str  # short machine-readable hint fed into the explain prompt


def detect_triggers(state: MatchState) -> list[Trigger]:
    """Look at the most recent event in context and decide if it's insight-worthy."""
    if not state.events_processed:
        return []
    event = state.events_processed[-1]
    triggers: list[Trigger] = []

    if event.type == EventType.GOAL:
        triggers.append(Trigger("milestone", 1.0, event, "goal scored"))

    elif event.type == EventType.SHOT and event.speed_kmh and event.speed_kmh >= FAST_SHOT_KMH:
        triggers.append(Trigger("danger", 0.7, event, f"fast shot at {event.speed_kmh} km/h"))

    elif event.type == EventType.PRESSURE and (event.pressure_index or 0) >= HIGH_PRESSURE:
        triggers.append(Trigger("tactical", 0.6, event, f"pressure spike {event.pressure_index}"))

    elif event.type == EventType.TACKLE and event.outcome == "won":
        recent = state.events_processed[-TACKLE_WINDOW:]
        won_by_team = sum(1 for e in recent if e.type == EventType.TACKLE and e.outcome == "won" and e.team_id == event.team_id)
        if won_by_team >= TACKLE_STREAK:
            key = f"tackle_streak_{event.team_id}_{event.minute // 10}"
            if key not in state.seen_milestones:
                state.seen_milestones.add(key)
                triggers.append(Trigger("tactical", 0.55, event, f"{won_by_team} tackles won recently"))

    # possession milestone: only the highest newly-crossed threshold per team, per tick
    if len(state.events_processed) >= 15:  # let the window fill before trusting possession %
        for tid, ts in state.team_stats.items():
            crossed = [t for t in (60, 70, 80) if ts.possession_pct >= t and f"possession_{tid}_{t}" not in state.seen_milestones]
            if crossed:
                top = max(crossed)
                for t in (60, 70, 80):
                    if t <= top:
                        state.seen_milestones.add(f"possession_{tid}_{t}")
                triggers.append(Trigger("control", 0.5, event, f"team {tid} possession reached {top}%"))

    # momentum swing: sign flip of meaningful size
    if abs(state.momentum - state.last_momentum) >= 0.4:
        triggers.append(Trigger("momentum_shift", 0.65, event, f"momentum moved to {state.momentum}"))
    state.last_momentum = state.momentum

    return triggers


def explain(trigger: Trigger, state: MatchState) -> Insight:
    text = _try_llm_explain(trigger, state)
    source = "llm"
    if text is None:
        text = template_explain(trigger, state)
        source = "template"
    headline, explanation = text
    return Insight(
        id=str(uuid.uuid4())[:8],
        minute=trigger.event.minute,
        second=trigger.event.second,
        headline=headline,
        explanation=explanation,
        category=trigger.category,
        importance=trigger.importance,
        related_event_id=trigger.event.id,
        source=source,
    )


def _context_text(trigger: Trigger, state: MatchState) -> str:
    home, away = state.meta.home, state.meta.away
    hs = state.team_stats.get(home.id)
    aw = state.team_stats.get(away.id)
    scoreline = (
        f"{home.name} possession {hs.possession_pct if hs else 0}% / "
        f"{away.name} possession {aw.possession_pct if aw else 0}%, "
        f"momentum {state.momentum:+.2f} (+1 favors {home.name})"
    )
    player = state.players.get(trigger.event.player_id) if trigger.event.player_id else None
    player_bit = f" Player involved: {player.name} ({player.position})." if player else ""
    return f"Minute {trigger.event.minute}. Trigger: {trigger.note}. {scoreline}.{player_bit}"


def _try_llm_explain(trigger: Trigger, state: MatchState) -> tuple[str, str] | None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(base_url=GITHUB_MODELS_BASE_URL, api_key=token, timeout=6.0)
        resp = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a football broadcast analyst. Given a match moment, write a short "
                        "headline (max 7 words) and a one-sentence explanation of WHY it matters "
                        "tactically or narratively -- not just what happened. Be concrete, no cliches. "
                        "Reply as exactly two lines: 'HEADLINE: ...' then 'EXPLAIN: ...'."
                    ),
                },
                {"role": "user", "content": _context_text(trigger, state)},
            ],
            max_tokens=120,
            temperature=0.7,
        )
        raw = resp.choices[0].message.content or ""
        headline, explanation = "", ""
        for line in raw.splitlines():
            if line.upper().startswith("HEADLINE:"):
                headline = line.split(":", 1)[1].strip()
            elif line.upper().startswith("EXPLAIN:"):
                explanation = line.split(":", 1)[1].strip()
        if headline and explanation:
            return headline, explanation
        return None
    except Exception:
        return None


def template_explain(trigger: Trigger, state: MatchState) -> tuple[str, str]:
    e = trigger.event
    team = state.meta.home if e.team_id == state.meta.home.id else state.meta.away
    player = state.players.get(e.player_id) if e.player_id else None
    pname = player.name if player else "A player"

    if trigger.category == "milestone":
        return (f"GOAL — {team.name}", f"{pname} scores for {team.name} at minute {e.minute}.")
    if trigger.category == "danger":
        return (
            "Rocket shot",
            f"{pname} unleashes a shot at {e.speed_kmh} km/h — ball speed alone makes this a genuine chance.",
        )
    if trigger.category == "tactical" and "pressure" in trigger.note:
        return (
            f"{team.name} press trap",
            f"{team.name} are applying sustained pressure (index {e.pressure_index}), forcing rushed decisions.",
        )
    if trigger.category == "tactical":
        return (
            f"{team.name} winning the ball back",
            f"{team.name} have won the ball back repeatedly in a short spell — a sign of organized pressing.",
        )
    if trigger.category == "control":
        return (
            f"{team.name} dictating tempo",
            f"{team.name} are dominating possession, a classic 'control' phase that tires out the opponent.",
        )
    if trigger.category == "momentum_shift":
        direction = state.meta.home.name if state.momentum > 0 else state.meta.away.name
        return (
            "Momentum swings",
            f"The balance of the match has swung toward {direction} — control vs. chaos just flipped.",
        )
    return ("Moment flagged", f"Notable event for {team.name} at minute {e.minute}.")
