from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class TeamData:
    external_id: str
    abbreviation: str
    location: str
    name: str


@dataclass(frozen=True)
class WeekData:
    number: int
    starts_at: datetime
    ends_at: datetime
    sunday: date


@dataclass(frozen=True)
class GameData:
    external_id: str
    week_number: int
    home_team: TeamData
    away_team: TeamData
    kickoff_at: datetime
    kickoff_is_tbd: bool
    status: str
    neutral_site: bool
    home_score: int | None = None
    away_score: int | None = None


class ScheduleProvider(Protocol):
    def fetch_weeks(self, season: int) -> list[WeekData]: ...

    def fetch_games(self, season: int, week: int) -> list[GameData]: ...
