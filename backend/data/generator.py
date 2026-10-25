"""Synthetic, football-realistic match data generator.

Produces an entirely fictional match: made-up clubs, made-up players,
procedurally generated events. No real Premier League data is used or
redistributed anywhere in this file or its output.
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone

from backend.models import EventType, MatchEvent, MatchMeta, Player, Team

FIRST_NAMES = [
    "Kobe", "Darius", "Mateo", "Elian", "Noah", "Finn", "Jaden", "Theo",
    "Rafael", "Amir", "Leo", "Kian", "Oscar", "Milo", "Zane", "Idris",
    "Soren", "Pablo", "Jaxon", "Enzo", "Ravi", "Aaron", "Cole", "Mason",
]
LAST_NAMES = [
    "Okafor", "Lindqvist", "Marchetti", "Dubois", "Haaland-Smit", "Varga",
    "Castellano", "Nkemdirim", "Fontaine", "Brandt", "Soriano", "Vukovic",
    "Pereira", "Lindgren", "Osei", "Kowalski", "Abara", "Delgado",
    "Whitfield", "Tanaka", "Bergstrom", "Mbeki", "Riordan", "Salerno",
]
CLUB_NAMES = [
    ("Ironbridge United", "IBU"),
    ("Meridian City", "MCY"),
    ("Harlow Athletic", "HAR"),
    ("Castlegate Rovers", "CGR"),
]
FORMATION_POSITIONS = (
    ["GK"] + ["CB", "CB", "LB", "RB"] + ["CM", "CM", "CDM"] + ["LW", "RW", "ST"]
)


def _make_team(name: str, short_name: str) -> Team:
    return Team(id=str(uuid.uuid4())[:8], name=name, short_name=short_name)


def _make_squad(team: Team, rng: random.Random) -> list[Player]:
    used = set()
    squad = []
    for pos in FORMATION_POSITIONS:
        while True:
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
            if name not in used:
                used.add(name)
                break
        squad.append(
            Player(id=str(uuid.uuid4())[:8], name=name, team_id=team.id, position=pos)
        )
    return squad


def generate_match(seed: int | None = None) -> tuple[MatchMeta, dict[str, Player], list[MatchEvent]]:
    rng = random.Random(seed)
    (home_name, home_short), (away_name, away_short) = rng.sample(CLUB_NAMES, 2)
    home = _make_team(home_name, home_short)
    away = _make_team(away_name, away_short)

    home_squad = _make_squad(home, rng)
    away_squad = _make_squad(away, rng)
    players: dict[str, Player] = {p.id: p for p in home_squad + away_squad}

    meta = MatchMeta(
        match_id=str(uuid.uuid4())[:8],
        home=home,
        away=away,
        kickoff_utc=datetime.now(timezone.utc).isoformat(),
        venue="Synthetic Park",
    )

    events: list[MatchEvent] = []
    possession_team = home if rng.random() < 0.5 else away

    def other(team: Team) -> Team:
        return away if team.id == home.id else home

    def outfielders(team_id: str) -> list[Player]:
        return [p for p in players.values() if p.team_id == team_id and p.position != "GK"]

    x, y = 50.0, 50.0  # shared "ball position" on a 0-100 pitch, home attacks toward x=100

    total_minutes = 90
    for minute in range(total_minutes + 1):
        # stoppage-time-ish extra events near half/full time handled by just running to 90
        events_this_minute = rng.randint(4, 9)
        for _ in range(events_this_minute):
            second = rng.randint(0, 59)
            attackers = outfielders(possession_team.id)
            defenders = outfielders(other(possession_team).id)
            passer = rng.choice(attackers)

            roll = rng.random()
            attacking_third = (x > 66) if possession_team.id == home.id else (x < 34)

            if roll < 0.62:
                # PASS
                target = rng.choice([p for p in attackers if p.id != passer.id])
                direction = 1 if possession_team.id == home.id else -1
                dx = rng.uniform(-15, 25) * direction
                dy = rng.uniform(-20, 20)
                end_x = max(0.0, min(100.0, x + dx))
                end_y = max(0.0, min(100.0, y + dy))
                distance = ((end_x - x) ** 2 + (end_y - y) ** 2) ** 0.5
                # harder passes (longer, more lateral into pressure) succeed less
                difficulty = min(1.0, distance / 60 + (0.15 if attacking_third else 0))
                success = rng.random() > difficulty * 0.55
                ev = MatchEvent(
                    id=str(uuid.uuid4())[:8],
                    minute=minute,
                    second=second,
                    type=EventType.PASS,
                    team_id=possession_team.id,
                    player_id=passer.id,
                    target_player_id=target.id,
                    x=x, y=y, end_x=end_x, end_y=end_y,
                    outcome="complete" if success else "incomplete",
                    distance_m=round(distance * 1.05, 1),
                    extra={"difficulty": round(difficulty, 2)},
                )
                events.append(ev)
                if success:
                    x, y = end_x, end_y
                else:
                    possession_team = other(possession_team)
                    events.append(_possession_change(minute, second, possession_team))

            elif roll < 0.72 and attacking_third:
                # SHOT
                shooter = passer
                on_target = rng.random() < 0.45
                is_goal = on_target and rng.random() < 0.28
                speed = round(rng.uniform(85, 128), 1)
                outcome = "goal" if is_goal else ("on_target" if on_target else "off_target")
                ev = MatchEvent(
                    id=str(uuid.uuid4())[:8],
                    minute=minute,
                    second=second,
                    type=EventType.SHOT,
                    team_id=possession_team.id,
                    player_id=shooter.id,
                    x=x, y=y,
                    outcome=outcome,
                    speed_kmh=speed,
                )
                events.append(ev)
                if is_goal:
                    events.append(MatchEvent(
                        id=str(uuid.uuid4())[:8], minute=minute, second=min(second + 1, 59),
                        type=EventType.GOAL, team_id=possession_team.id, player_id=shooter.id,
                        x=x, y=y, outcome="goal",
                    ))
                    possession_team = other(possession_team)
                    x, y = 50.0, 50.0
                else:
                    possession_team = other(possession_team)
                    x, y = max(0, min(100, 100 - x)), y
                    events.append(_possession_change(minute, second, possession_team))

            elif roll < 0.88:
                # TACKLE
                defender = rng.choice(defenders)
                won = rng.random() < 0.52
                ev = MatchEvent(
                    id=str(uuid.uuid4())[:8],
                    minute=minute,
                    second=second,
                    type=EventType.TACKLE,
                    team_id=other(possession_team).id,
                    player_id=defender.id,
                    target_player_id=passer.id,
                    x=x, y=y,
                    outcome="won" if won else "foul",
                )
                events.append(ev)
                if won:
                    possession_team = other(possession_team)
                    events.append(_possession_change(minute, second, possession_team))

            else:
                # PRESSURE event — opponent closing down in a dangerous zone
                pressor = rng.choice(defenders)
                pressure_index = round(rng.uniform(0.3, 1.0) * (1.4 if attacking_third else 1.0), 2)
                ev = MatchEvent(
                    id=str(uuid.uuid4())[:8],
                    minute=minute,
                    second=second,
                    type=EventType.PRESSURE,
                    team_id=other(possession_team).id,
                    player_id=pressor.id,
                    target_player_id=passer.id,
                    x=x, y=y,
                    pressure_index=min(pressure_index, 1.0),
                )
                events.append(ev)

    events.sort(key=lambda e: (e.minute, e.second))
    return meta, players, events


def _possession_change(minute: int, second: int, new_team: Team) -> MatchEvent:
    return MatchEvent(
        id=str(uuid.uuid4())[:8],
        minute=minute,
        second=second,
        type=EventType.POSSESSION_CHANGE,
        team_id=new_team.id,
        x=50.0, y=50.0,
    )


if __name__ == "__main__":
    import json

    meta, players, events = generate_match(seed=7)
    print(f"{meta.home.name} vs {meta.away.name} — {len(events)} events generated")
    out = {
        "meta": meta.model_dump(),
        "players": {pid: p.model_dump() for pid, p in players.items()},
        "events": [e.model_dump() for e in events],
    }
    with open("backend/data/sample_match.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("Wrote backend/data/sample_match.json")
