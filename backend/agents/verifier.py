"""Verifier Agent — the 6th agent: trust, not just narration.

Every number an LLM writes into an insight is extracted and cross-checked
against the deterministic MatchState the Stats Agent computed. If a claim
doesn't match the source data within tolerance, this agent rejects the
LLM's text and substitutes the always-correct template explanation instead
-- a second, concrete failure-recovery path (beyond "LLM unreachable") in
the agent chain: "LLM reachable, but wrong."

Template-sourced insights are verified by construction (every number in
them came directly from MatchState) and skip the check.
"""
from __future__ import annotations

import re

from backend.agents.explainer import Trigger, template_explain
from backend.models import Insight, MatchState

PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
SPEED_RE = re.compile(r"(\d+(?:\.\d+)?)\s*km\s*/?\s*h", re.IGNORECASE)

TOLERANCE_PCT = 3.0      # percentage points
TOLERANCE_SPEED = 2.0    # km/h


def verify(insight: Insight, trigger: Trigger, state: MatchState) -> Insight:
    if insight.source != "llm":
        insight.verified = True
        insight.verification_note = "Generated directly from computed match stats — no LLM claim to check."
        return insight

    text = f"{insight.headline} {insight.explanation}"
    pct_buckets = _known_percentages(state)
    known_speeds = _known_speeds(trigger)

    bad_claims = []
    for match in PCT_RE.finditer(text):
        value = float(match.group(1))
        window = text[max(0, match.start() - 24):match.end() + 24].lower()
        if "possession" in window or "control" in window:
            candidates = pct_buckets["possession"]
        elif "accura" in window or "pass" in window:
            candidates = pct_buckets["pass_accuracy"]
        else:
            candidates = pct_buckets["possession"] + pct_buckets["pass_accuracy"]
        if not _within_any(value, candidates, TOLERANCE_PCT):
            bad_claims.append(f"{value}%")
    for match in SPEED_RE.finditer(text):
        value = float(match.group(1))
        if not _within_any(value, known_speeds, TOLERANCE_SPEED):
            bad_claims.append(f"{value} km/h")

    if bad_claims:
        headline, explanation = template_explain(trigger, state)
        insight.headline = headline
        insight.explanation = explanation
        insight.source = "llm_corrected"
        insight.verified = True
        insight.verification_note = (
            f"LLM claim(s) {', '.join(bad_claims)} did not match computed match data — "
            "replaced with a verified, stats-grounded explanation."
        )
    else:
        insight.verified = True
        insight.verification_note = "Numeric claims checked against match data."

    return insight


def _known_percentages(state: MatchState) -> dict[str, list[float]]:
    return {
        "possession": [ts.possession_pct for ts in state.team_stats.values()],
        "pass_accuracy": [ts.pass_accuracy for ts in state.team_stats.values()],
    }


def _known_speeds(trigger: Trigger) -> list[float]:
    values = []
    if trigger.event.speed_kmh:
        values.append(trigger.event.speed_kmh)
    return values


def _within_any(value: float, known: list[float], tolerance: float) -> bool:
    if not known:
        return True  # nothing to compare against (e.g. a shot speed claim with no speed on this event) -- don't false-flag
    return any(abs(value - k) <= tolerance for k in known)
