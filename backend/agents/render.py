"""Render Agent — turns an Insight into a broadcast-ready overlay cue.

The output is a small, timestamped, machine-readable schema rather than
pixels. This is the "production path" contract: a real broadcast graphics
tool (the kind that composites lower-thirds over a live feed) could
consume this JSON directly. Our own frontend is just a reference renderer
for the same contract.
"""
from __future__ import annotations

import uuid

from backend.models import Insight, OverlayCue

CATEGORY_TO_TYPE = {
    "milestone": "milestone_card",
    "danger": "stat_bug",
    "tactical": "lower_third",
    "control": "lower_third",
    "momentum_shift": "momentum_bar",
}

CATEGORY_TO_STYLE = {
    "milestone": "goal",
    "danger": "warning",
    "tactical": "info",
    "control": "info",
    "momentum_shift": "momentum",
}


def render_cue(insight: Insight) -> OverlayCue:
    return OverlayCue(
        id=str(uuid.uuid4())[:8],
        minute=insight.minute,
        second=insight.second,
        type=CATEGORY_TO_TYPE.get(insight.category, "lower_third"),
        title=insight.headline,
        body=insight.explanation,
        duration_s=round(4.0 + insight.importance * 4.0, 1),
        style=CATEGORY_TO_STYLE.get(insight.category, "neutral"),
        related_insight_id=insight.id,
    )
