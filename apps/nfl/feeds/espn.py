from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from apps.nfl.feeds.types import GameData, TeamData, WeekData
from apps.nfl.models import GameStatus

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
REGULAR_SEASON = 2
NFL_CALENDAR_TZ = ZoneInfo("America/Los_Angeles")

_STATUS_BY_NAME = {
    "STATUS_POSTPONED": GameStatus.POSTPONED,
    "STATUS_CANCELED": GameStatus.CANCELLED,
}
_STATUS_BY_STATE = {
    "pre": GameStatus.SCHEDULED,
    "in": GameStatus.IN_PROGRESS,
}


class EspnFeedError(Exception):
    pass


class EspnScheduleProvider:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(15.0),
            transport=httpx.HTTPTransport(retries=2),
            headers={"Accept": "application/json"},
        )

    def fetch_weeks(self, season: int) -> list[WeekData]:
        return parse_regular_season_weeks(self._get(season=season, week=1))

    def fetch_games(self, season: int, week: int) -> list[GameData]:
        return parse_games(self._get(season=season, week=week))

    def _get(self, *, season: int, week: int) -> dict[str, Any]:
        params = {"seasontype": REGULAR_SEASON, "week": week, "dates": season}
        try:
            response = self._client.get(SCOREBOARD_URL, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EspnFeedError(f"ESPN request failed: {exc}") from exc
        payload: dict[str, Any] = response.json()
        return payload


def parse_regular_season_weeks(payload: dict[str, Any]) -> list[WeekData]:
    calendar = payload["leagues"][0]["calendar"]
    regular = next(
        (part for part in calendar if part.get("value") == str(REGULAR_SEASON)), None
    )
    if regular is None:
        raise EspnFeedError("Regular season missing from ESPN calendar.")
    return [
        _parse_week(entry)
        for entry in regular["entries"]
        if entry.get("value", "").isdigit()
    ]


def parse_games(payload: dict[str, Any]) -> list[GameData]:
    week_number = int(payload["week"]["number"])
    return [_parse_event(event, week_number) for event in payload.get("events", [])]


def _parse_week(entry: dict[str, Any]) -> WeekData:
    starts_at = _parse_datetime(entry["startDate"])
    ends_at = _parse_datetime(entry["endDate"])
    return WeekData(
        number=int(entry["value"]),
        starts_at=starts_at,
        ends_at=ends_at,
        sunday=_last_sunday(starts_at, ends_at),
    )


def _parse_event(event: dict[str, Any], week_number: int) -> GameData:
    competition = event["competitions"][0]
    teams = {c["homeAway"]: _parse_team(c["team"]) for c in competition["competitors"]}
    status = competition["status"]
    return GameData(
        external_id=str(event["id"]),
        week_number=week_number,
        home_team=teams["home"],
        away_team=teams["away"],
        kickoff_at=_parse_datetime(event["date"]),
        kickoff_is_tbd=bool(status.get("isTBDFlex"))
        or not competition.get("timeValid", True),
        status=_map_status(status["type"]),
        neutral_site=bool(competition.get("neutralSite")),
    )


def _parse_team(team: dict[str, Any]) -> TeamData:
    return TeamData(
        external_id=str(team["id"]),
        abbreviation=team["abbreviation"],
        location=team["location"],
        name=team["name"],
    )


def _map_status(status_type: dict[str, Any]) -> GameStatus:
    if status_type["name"] in _STATUS_BY_NAME:
        return _STATUS_BY_NAME[status_type["name"]]
    if status_type["state"] == "post" and status_type.get("completed"):
        return GameStatus.FINAL
    return _STATUS_BY_STATE.get(status_type["state"], GameStatus.SCHEDULED)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise EspnFeedError(f"Timestamp without timezone: {value}")
    return parsed


def _last_sunday(starts_at: datetime, ends_at: datetime) -> date:
    first_day = starts_at.astimezone(NFL_CALENDAR_TZ).date()
    day = ends_at.astimezone(NFL_CALENDAR_TZ).date()
    while day.weekday() != 6:
        day -= timedelta(days=1)
    if day < first_day:
        raise EspnFeedError(f"No Sunday between {starts_at} and {ends_at}.")
    return day
