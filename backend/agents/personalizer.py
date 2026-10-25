"""Personalizer Agent — the final stage: same MatchState, different fan.

Takes the full Insight feed plus a viewer's preferences (mode, favorite
team/player, language) and reshapes it into a genuinely different
experience: dense stats for an analyst, a highlight reel for a casual
fan, or a single-player storyline for player-focus mode.
"""
from __future__ import annotations

import os

from backend.models import Insight, MatchState, PersonaMode, PersonalizedCard, PersonalizedFeedRequest

# Minimal headline phrasebook so the UI can demonstrate multi-language output
# deterministically even when the LLM path is unreachable (sandboxed/offline).
HEADLINE_PHRASEBOOK = {
    "milestone": {"en": "GOAL", "es": "GOL", "fr": "BUT"},
    "danger": {"en": "Big chance", "es": "Gran ocasion", "fr": "Grosse occasion"},
    "tactical": {"en": "Tactical shift", "es": "Cambio tactico", "fr": "Bascule tactique"},
    "control": {"en": "Taking control", "es": "Tomando el control", "fr": "Prise de controle"},
    "momentum_shift": {"en": "Momentum swings", "es": "Cambia el momento", "fr": "Le momentum bascule"},
}


def build_feed(insights: list[Insight], state: MatchState, req: PersonalizedFeedRequest) -> list[PersonalizedCard]:
    relevant = _filter_for_request(insights, state, req)
    cards = [_render_card(ins, state, req) for ins in relevant]
    return cards


def _filter_for_request(insights: list[Insight], state: MatchState, req: PersonalizedFeedRequest) -> list[Insight]:
    if req.mode == PersonaMode.ANALYST:
        return insights  # analysts get everything, unfiltered

    if req.mode == PersonaMode.PLAYER_FOCUS and req.favorite_player_id:
        out = []
        for ins in insights:
            event = _find_event(state, ins.related_event_id)
            if event and (event.player_id == req.favorite_player_id or event.target_player_id == req.favorite_player_id):
                out.append(ins)
        return out

    if req.mode == PersonaMode.FAN:
        out = insights
        if req.favorite_team_id:
            out = [ins for ins in out if _team_of(state, ins) == req.favorite_team_id or ins.importance >= 0.9]
        # casual fans get the highlights, not every tactical nuance
        return [ins for ins in out if ins.importance >= 0.5]

    return insights


def _team_of(state: MatchState, ins: Insight) -> str | None:
    event = _find_event(state, ins.related_event_id)
    return event.team_id if event else None


def _find_event(state: MatchState, event_id: str | None):
    if not event_id:
        return None
    return next((e for e in state.events_processed if e.id == event_id), None)


def _render_card(ins: Insight, state: MatchState, req: PersonalizedFeedRequest) -> PersonalizedCard:
    headline = HEADLINE_PHRASEBOOK.get(ins.category, {}).get(req.language) or ins.headline
    body = _localize_body(ins, req)
    tag = {
        PersonaMode.ANALYST: "analyst",
        PersonaMode.FAN: "fan",
        PersonaMode.PLAYER_FOCUS: "player",
    }[req.mode]
    return PersonalizedCard(minute=ins.minute, second=ins.second, title=headline, body=body, tag=tag)


def _localize_body(ins: Insight, req: PersonalizedFeedRequest) -> str:
    body = ins.explanation
    if req.mode == PersonaMode.ANALYST:
        body = f"{body} (importance {ins.importance:.2f}, source: {ins.source})"
    elif req.mode == PersonaMode.FAN:
        body = body.replace("tactically", "").strip()

    if req.language != "en":
        translated = _try_llm_translate(body, req.language)
        body = translated if translated else f"{body} [{req.language} translation unavailable offline]"
    return body


def _try_llm_translate(text: str, language: str) -> str | None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(base_url="https://models.github.ai/inference", api_key=token, timeout=6.0)
        resp = client.chat.completions.create(
            model=os.environ.get("PULSEXI_MODEL", "openai/gpt-4o-mini"),
            messages=[
                {"role": "system", "content": f"Translate the football commentary into {language}. Reply with only the translation."},
                {"role": "user", "content": text},
            ],
            max_tokens=120,
            temperature=0.3,
        )
        return (resp.choices[0].message.content or "").strip() or None
    except Exception:
        return None
