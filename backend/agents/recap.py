"""Recap Agent — the capstone stage: synthesizes the whole match into a
short automated recap, built only from insights the Verifier has already
checked. The recap can't say anything the live broadcast didn't already
verify, so it needs no separate fact-check pass of its own.
"""
from __future__ import annotations

import os

from backend.agents.explainer import DEFAULT_MODEL, GITHUB_MODELS_BASE_URL
from backend.models import Insight, MatchState

MAX_HIGHLIGHTS = 5


def build_recap(insights: list[Insight], state: MatchState) -> dict:
    highlights = _select_highlights(insights)
    llm_summary = _try_llm_recap(highlights, state)
    summary = llm_summary or _template_recap(highlights, state)

    home, away = state.meta.home, state.meta.away
    hs = state.team_stats.get(home.id)
    aws = state.team_stats.get(away.id)

    return {
        "headline": f"{home.name} {hs.goals if hs else 0} – {aws.goals if aws else 0} {away.name}",
        "summary": summary,
        "source": "llm" if llm_summary else "template",
        "verified": True,
        "highlight_count": len(highlights),
    }


def _select_highlights(insights: list[Insight]) -> list[Insight]:
    goals = [i for i in insights if i.category == "milestone"]
    rest = sorted(
        (i for i in insights if i.category != "milestone"),
        key=lambda i: i.importance,
        reverse=True,
    )
    picked = goals + rest[: max(0, MAX_HIGHLIGHTS - len(goals))]
    return sorted(picked, key=lambda i: (i.minute, i.second))


def _template_recap(highlights: list[Insight], state: MatchState) -> str:
    home, away = state.meta.home, state.meta.away
    hs = state.team_stats.get(home.id)
    aws = state.team_stats.get(away.id)

    sentences = [
        f"{home.name} and {away.name} finished {hs.goals if hs else 0}-{aws.goals if aws else 0}."
    ]
    sentences.extend(h.explanation for h in highlights)
    if hs and aws:
        leader = home.name if hs.possession_pct >= aws.possession_pct else away.name
        sentences.append(
            f"{leader} controlled the ball for longer across the match, finishing "
            f"{hs.possession_pct}% to {aws.possession_pct}% in possession."
        )
    return " ".join(sentences)


def _try_llm_recap(highlights: list[Insight], state: MatchState) -> str | None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token or not highlights:
        return None
    try:
        from openai import OpenAI

        home, away = state.meta.home, state.meta.away
        hs = state.team_stats.get(home.id)
        aws = state.team_stats.get(away.id)
        facts = "\n".join(f"- (min {h.minute}) {h.explanation}" for h in highlights)
        facts += (
            f"\n- Final possession: {home.name} {hs.possession_pct if hs else 0}% / "
            f"{away.name} {aws.possession_pct if aws else 0}%"
            f"\n- Final score: {home.name} {hs.goals if hs else 0} - {aws.goals if aws else 0} {away.name}"
        )

        client = OpenAI(base_url=GITHUB_MODELS_BASE_URL, api_key=token, timeout=8.0)
        resp = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a football broadcast producer writing a 3-4 sentence full-time "
                        "match recap for a studio segment. Use ONLY the facts given below -- do "
                        "not invent any statistic, player, or event not listed. Write it as flowing "
                        "prose, not a list."
                    ),
                },
                {"role": "user", "content": facts},
            ],
            max_tokens=220,
            temperature=0.6,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or None
    except Exception:
        return None
