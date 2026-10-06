from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from apps.nfl.feeds.types import GameData, TeamData, WeekData
from apps.nfl.models import Game, GameStatus, Team, Week
from apps.nfl.services import sync_schedule

SEA = TeamData("26", "SEA", "Seattle", "Seahawks")
NE = TeamData("17", "NE", "New England", "Patriots")
KC = TeamData("12", "KC", "Kansas City", "Chiefs")
BUF = TeamData("2", "BUF", "Buffalo", "Bills")

KICKOFF = datetime(2026, 9, 13, 17, 0, tzinfo=UTC)


def make_week(number: int) -> WeekData:
    start = datetime(2026, 9, 9, 7, 0, tzinfo=UTC) + timedelta(weeks=number - 1)
    return WeekData(
        number=number,
        starts_at=start,
        ends_at=start + timedelta(days=7),
        sunday=date(2026, 9, 13) + timedelta(weeks=number - 1),
    )


def make_game(external_id: str = "1", **overrides: object) -> GameData:
    game = GameData(
        external_id=external_id,
        week_number=1,
        home_team=SEA,
        away_team=NE,
        kickoff_at=KICKOFF,
        kickoff_is_tbd=False,
        status=GameStatus.SCHEDULED,
        neutral_site=False,
    )
    return replace(game, **overrides)  # type: ignore[arg-type]


class FakeProvider:
    def __init__(self, games: list[GameData], weeks: int = 2) -> None:
        self.games = games
        self.weeks = [make_week(n) for n in range(1, weeks + 1)]

    def fetch_weeks(self, season: int) -> list[WeekData]:
        return self.weeks

    def fetch_games(self, season: int, week: int) -> list[GameData]:
        return [g for g in self.games if g.week_number == week]


@pytest.mark.django_db
def test_sync_creates_season_weeks_teams_and_games() -> None:
    provider = FakeProvider(
        [make_game("1"), make_game("2", home_team=KC, away_team=BUF)]
    )
    result = sync_schedule(provider, season_year=2026)
    assert result.weeks == 2
    assert result.games_created == 2
    assert Week.objects.filter(season__year=2026).count() == 2
    assert Team.objects.count() == 4
    game = Game.objects.get(external_id="1")
    assert (game.home_team.abbreviation, game.away_team.abbreviation) == ("SEA", "NE")
    assert game.week.number == 1


@pytest.mark.django_db
def test_sync_is_idempotent() -> None:
    provider = FakeProvider([make_game()])
    sync_schedule(provider, season_year=2026)
    result = sync_schedule(provider, season_year=2026)
    assert result.games_created == 0
    assert result.games_updated == 0
    assert Game.objects.count() == 1


@pytest.mark.django_db
def test_flexed_kickoff_moves_without_postponing() -> None:
    sync_schedule(FakeProvider([make_game()]), season_year=2026)
    flexed = KICKOFF + timedelta(hours=7, minutes=20)
    result = sync_schedule(
        FakeProvider([make_game(kickoff_at=flexed)]), season_year=2026
    )
    game = Game.objects.get()
    assert game.kickoff_at == flexed
    assert game.postponed_from is None
    assert result.rescheduled == ["NE @ SEA"]


@pytest.mark.django_db
def test_postponed_game_keeps_original_kickoff_and_week() -> None:
    sync_schedule(FakeProvider([make_game()]), season_year=2026)
    sync_schedule(
        FakeProvider([make_game(status=GameStatus.POSTPONED)]), season_year=2026
    )
    made_up = KICKOFF + timedelta(days=9)
    sync_schedule(
        FakeProvider([make_game(week_number=2, kickoff_at=made_up)]),
        season_year=2026,
    )
    game = Game.objects.get()
    assert game.postponed_from == KICKOFF
    assert game.kickoff_at == made_up
    assert game.week.number == 1


@pytest.mark.django_db
def test_sync_limited_to_requested_weeks() -> None:
    provider = FakeProvider([make_game("1"), make_game("2", week_number=2)])
    sync_schedule(provider, season_year=2026, weeks=[2])
    assert list(Game.objects.values_list("external_id", flat=True)) == ["2"]
