import json
from copy import deepcopy
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from apps.nfl.feeds.espn import (
    EspnFeedError,
    EspnScheduleProvider,
    parse_games,
    parse_regular_season_weeks,
)
from apps.nfl.models import GameStatus

FIXTURES = Path(__file__).parent / "fixtures" / "espn"


def load(name: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return payload


@pytest.fixture
def week1() -> dict[str, Any]:
    return load("scoreboard_2026_week1.json")


def test_regular_season_has_18_weeks(week1: dict[str, Any]) -> None:
    weeks = parse_regular_season_weeks(week1)
    assert [w.number for w in weeks] == list(range(1, 19))


@pytest.mark.parametrize(
    ("number", "sunday"),
    [(1, date(2026, 9, 13)), (12, date(2026, 11, 29)), (18, date(2027, 1, 10))],
)
def test_week_sunday_is_last_sunday_in_window(
    week1: dict[str, Any], number: int, sunday: date
) -> None:
    weeks = {w.number: w for w in parse_regular_season_weeks(week1)}
    assert weeks[number].sunday == sunday


def test_parse_games_maps_teams_and_kickoff(week1: dict[str, Any]) -> None:
    game = parse_games(week1)[0]
    assert game.external_id == "401872656"
    assert game.week_number == 1
    assert game.home_team.abbreviation == "SEA"
    assert game.away_team.abbreviation == "NE"
    assert game.kickoff_at == datetime(2026, 9, 10, 0, 20, tzinfo=UTC)
    assert game.status == GameStatus.FINAL
    assert not game.kickoff_is_tbd


def test_parse_games_scheduled_week() -> None:
    games = parse_games(load("scoreboard_2026_week12.json"))
    assert {g.status for g in games} == {GameStatus.SCHEDULED}
    assert games[0].away_team.abbreviation == "GB"


@pytest.mark.parametrize(
    ("status_type", "expected"),
    [
        (
            {"name": "STATUS_POSTPONED", "state": "post", "completed": False},
            "postponed",
        ),
        ({"name": "STATUS_CANCELED", "state": "post", "completed": False}, "cancelled"),
        (
            {"name": "STATUS_IN_PROGRESS", "state": "in", "completed": False},
            "in_progress",
        ),
        ({"name": "STATUS_HALFTIME", "state": "in", "completed": False}, "in_progress"),
        ({"name": "STATUS_SCHEDULED", "state": "pre", "completed": False}, "scheduled"),
    ],
)
def test_status_mapping(
    week1: dict[str, Any], status_type: dict[str, Any], expected: str
) -> None:
    payload = deepcopy(week1)
    payload["events"][0]["competitions"][0]["status"]["type"] = status_type
    assert parse_games(payload)[0].status == expected


def test_tbd_flex_is_flagged(week1: dict[str, Any]) -> None:
    payload = deepcopy(week1)
    payload["events"][0]["competitions"][0]["status"]["isTBDFlex"] = True
    assert parse_games(payload)[0].kickoff_is_tbd


def test_provider_wraps_http_errors() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    provider = EspnScheduleProvider(httpx.Client(transport=transport))
    with pytest.raises(EspnFeedError):
        provider.fetch_games(2026, 1)


def test_provider_requests_regular_season_week(week1: dict[str, Any]) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=week1)

    provider = EspnScheduleProvider(
        httpx.Client(transport=httpx.MockTransport(handler))
    )
    provider.fetch_games(2026, 1)
    assert seen[0].url.params["seasontype"] == "2"
    assert seen[0].url.params["week"] == "1"
    assert seen[0].url.params["dates"] == "2026"
