"""Stats Agent — turns raw events into meaningful football statistics.

Pure, deterministic aggregation: no LLM calls here. Takes the shared
MatchState and the newest event, and updates team/player stats in place.
"""
from __future__ import annotations

from backend.models import EventType, MatchEvent, MatchState, PlayerStats, TeamStats

PRESSURE_WINDOW = 40  # events of rolling history used for momentum/pressure smoothing


def _team_stats(state: MatchState, team_id: str) -> TeamStats:
    if team_id not in state.team_stats:
        state.team_stats[team_id] = TeamStats(team_id=team_id)
    return state.team_stats[team_id]


def _player_stats(state: MatchState, player_id: str) -> PlayerStats:
    if player_id not in state.player_stats:
        state.player_stats[player_id] = PlayerStats(player_id=player_id)
    return state.player_stats[player_id]


def update_stats(state: MatchState, event: MatchEvent) -> None:
    """Fold one new event into the shared MatchState. Called by the Ingest Agent."""
    ts = _team_stats(state, event.team_id)

    if event.type == EventType.PASS:
        ps = _player_stats(state, event.player_id) if event.player_id else None
        ts.passes_completed += 1 if event.outcome == "complete" else 0
        if ps:
            ps.passes_attempted += 1
            if event.outcome == "complete":
                ps.passes_completed += 1
            ps.pass_accuracy = round(ps.passes_completed / max(ps.passes_attempted, 1), 3)
            if event.distance_m:
                ps.distance_covered_m += event.distance_m

    elif event.type == EventType.SHOT:
        ts.shots += 1
        if event.outcome in ("on_target", "goal"):
            ts.shots_on_target += 1
        if event.player_id:
            ps = _player_stats(state, event.player_id)
            ps.shots += 1
            if event.outcome in ("on_target", "goal"):
                ps.shots_on_target += 1
            if event.speed_kmh and event.speed_kmh > ps.top_speed_kmh:
                ps.top_speed_kmh = event.speed_kmh

    elif event.type == EventType.TACKLE:
        if event.player_id:
            ps = _player_stats(state, event.player_id)
            ps.tackles += 1

    elif event.type == EventType.POSSESSION_CHANGE:
        state.current_possession_team_id = event.team_id

    elif event.type == EventType.PRESSURE and event.pressure_index is not None:
        ts.pressure_index = round(_ema(ts.pressure_index, event.pressure_index, alpha=0.25), 3)

    _recompute_derived(state)


def _ema(prev: float, new: float, alpha: float) -> float:
    return prev * (1 - alpha) + new * alpha if prev else new


def _recompute_derived(state: MatchState) -> None:
    """Recompute cheap aggregate fields (possession %, accuracy, control vs chaos, momentum)."""
    team_ids = list(state.team_stats.keys())
    if len(team_ids) < 1:
        return

    # possession % from the tail of recent events attributed to each team
    recent = state.events_processed[-PRESSURE_WINDOW:]
    counts: dict[str, int] = {}
    for e in recent:
        counts[e.team_id] = counts.get(e.team_id, 0) + 1
    total = sum(counts.values()) or 1
    for tid in team_ids:
        ts = state.team_stats[tid]
        ts.possession_pct = round(100 * counts.get(tid, 0) / total, 1)

        attempted = sum(1 for e in recent if e.type == EventType.PASS and e.team_id == tid)
        completed = sum(
            1 for e in recent if e.type == EventType.PASS and e.team_id == tid and e.outcome == "complete"
        )
        ts.pass_accuracy = round(100 * completed / attempted, 1) if attempted else ts.pass_accuracy

        # control vs chaos: high pass accuracy + low opponent pressure on us = control (+1)
        opp_pressure = next(
            (state.team_stats[o].pressure_index for o in team_ids if o != tid), 0.0
        )
        acc_component = (ts.pass_accuracy / 100 - 0.5) * 2  # -1..1
        pressure_component = -opp_pressure  # being pressed pushes toward chaos
        ts.control_vs_chaos = round(max(-1.0, min(1.0, 0.7 * acc_component + 0.3 * pressure_component)), 2)

    if len(team_ids) == 2:
        a, b = team_ids
        state.momentum = round(
            max(-1.0, min(1.0, state.team_stats[a].control_vs_chaos - state.team_stats[b].control_vs_chaos)) / 2,
            2,
        )
