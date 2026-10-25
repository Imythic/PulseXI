"""Shared schemas for the PulseXI pipeline. Every agent reads/writes these."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    PASS = "pass"
    SHOT = "shot"
    TACKLE = "tackle"
    POSSESSION_CHANGE = "possession_change"
    PRESSURE = "pressure"
    GOAL = "goal"
    CARD = "card"
    SUBSTITUTION = "substitution"


class Team(BaseModel):
    id: str
    name: str
    short_name: str


class Player(BaseModel):
    id: str
    name: str
    team_id: str
    position: str


class MatchEvent(BaseModel):
    id: str
    minute: int
    second: int
    type: EventType
    team_id: str
    player_id: Optional[str] = None
    target_player_id: Optional[str] = None
    x: float = Field(description="0-100 pitch coordinate, 0=own goal line")
    y: float = Field(description="0-100 pitch coordinate, 0=left touchline")
    end_x: Optional[float] = None
    end_y: Optional[float] = None
    outcome: Optional[str] = None
    speed_kmh: Optional[float] = None
    distance_m: Optional[float] = None
    pressure_index: Optional[float] = None
    extra: dict = Field(default_factory=dict)

    @property
    def clock(self) -> str:
        return f"{self.minute:02d}:{self.second:02d}"


class MatchMeta(BaseModel):
    match_id: str
    home: Team
    away: Team
    kickoff_utc: str
    venue: str
    competition: str = "Synthetic Premier League"


class PlayerStats(BaseModel):
    player_id: str
    passes_attempted: int = 0
    passes_completed: int = 0
    pass_accuracy: float = 0.0
    shots: int = 0
    shots_on_target: int = 0
    tackles: int = 0
    distance_covered_m: float = 0.0
    top_speed_kmh: float = 0.0


class TeamStats(BaseModel):
    team_id: str
    goals: int = 0
    possession_pct: float = 0.0
    passes_completed: int = 0
    pass_accuracy: float = 0.0
    shots: int = 0
    shots_on_target: int = 0
    control_vs_chaos: float = Field(0.0, description="-1 chaotic .. +1 controlled")
    pressure_index: float = 0.0


class MatchState(BaseModel):
    """The single shared state object every agent reads from and writes to."""
    meta: MatchMeta
    players: dict[str, Player]
    events_processed: list[MatchEvent] = Field(default_factory=list)
    team_stats: dict[str, TeamStats] = Field(default_factory=dict)
    player_stats: dict[str, PlayerStats] = Field(default_factory=dict)
    current_possession_team_id: Optional[str] = None
    momentum: float = Field(0.0, description="-1 away dominant .. +1 home dominant")
    last_momentum: float = 0.0
    seen_milestones: set[str] = Field(default_factory=set)


class Insight(BaseModel):
    id: str
    minute: int
    second: int
    headline: str
    explanation: str
    category: str = Field(description="e.g. momentum_shift, milestone, tactical, danger")
    importance: float = Field(ge=0.0, le=1.0)
    related_event_id: Optional[str] = None
    source: str = Field(description="llm, template, or llm_corrected, for transparency")
    verified: bool = True
    verification_note: Optional[str] = None


class OverlayCue(BaseModel):
    """Machine-readable broadcast overlay cue — the Render Agent's output contract."""
    id: str
    minute: int
    second: int
    type: str = Field(description="lower_third | stat_bug | milestone_card | momentum_bar")
    title: str
    body: str
    duration_s: float = 6.0
    style: str = "neutral"
    related_insight_id: Optional[str] = None
    verified: bool = True


class PersonaMode(str, Enum):
    ANALYST = "analyst"
    FAN = "fan"
    PLAYER_FOCUS = "player_focus"


class PersonalizedFeedRequest(BaseModel):
    mode: PersonaMode = PersonaMode.FAN
    favorite_team_id: Optional[str] = None
    favorite_player_id: Optional[str] = None
    language: str = "en"


class PersonalizedCard(BaseModel):
    minute: int
    second: int
    title: str
    body: str
    tag: str = "fan"
    verified: bool = True
