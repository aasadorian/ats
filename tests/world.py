from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from apps.leagues.models import LeagueWeek, Membership
from apps.lines.services import lock_spreads
from apps.nfl.models import Game, GameStatus
from tests.factories import make_league, make_user
from tests.odds import FakeOddsProvider, odds_event

LOCK_RUN = datetime(2026, 9, 8, 11, tzinfo=UTC)
OPEN = datetime(2026, 9, 9, 12, tzinfo=UTC)
THURSDAY_NIGHT = datetime(2026, 9, 10, 2, tzinfo=UTC)
SUNDAY_LOCKED = datetime(2026, 9, 13, 17, 30, tzinfo=UTC)

SEA_NE = odds_event("Seattle Seahawks", "New England Patriots", [-3, -3, -3.5])
KC_BUF = odds_event("Kansas City Chiefs", "Buffalo Bills", [-1.5, -2.5, -2.5])
DAL_NYG = odds_event("Dallas Cowboys", "New York Giants", [-6.5, -7, -7])


@dataclass
class World:
    league: Any
    week: LeagueWeek
    member: Membership
    other: Membership
    sea: Game
    kc: Game
    dal: Game


def build(events: list[dict[str, Any]] | None = None) -> World:
    league = make_league()
    lock_spreads(FakeOddsProvider(events or [SEA_NE, KC_BUF, DAL_NYG]), now=LOCK_RUN)
    week = LeagueWeek.objects.select_related(
        "league_season__settings", "league_season__league", "week"
    ).get(week__number=1)
    games = {g.home_team.abbreviation: g for g in week.week.games.all()}
    return World(
        league=league,
        week=week,
        member=Membership.objects.create(user=make_user(), league=league),
        other=Membership.objects.create(user=make_user(), league=league),
        sea=games["SEA"],
        kc=games["KC"],
        dal=games["DAL"],
    )


def finish(game: Game, home: int, away: int) -> None:
    Game.objects.filter(pk=game.pk).update(
        status=GameStatus.FINAL, home_score=home, away_score=away
    )
    game.refresh_from_db()
