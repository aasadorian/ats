import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import time_machine
from django.test import Client
from django.urls import reverse

from apps.activity.models import ActivityEvent
from apps.leagues.models import (
    LeagueSeason,
    LeagueSettings,
    LeagueWeek,
    LeagueWeekStatus,
    LineMode,
    PickType,
    PushScoring,
    WeeklyPrizeMetric,
)
from apps.lines.models import Spread, SpreadStatus
from apps.nfl.feeds.espn import parse_games
from apps.nfl.models import Game, GameStatus, Season
from apps.nfl.services import sync_scores, weeks_with_live_games
from apps.picks import services
from apps.picks.models import Pick
from apps.standings.grading import Outcome, grade
from apps.standings.selectors import season_standings, week_results
from apps.standings.services import update_week_statuses
from tests.world import OPEN, SUNDAY_LOCKED, World, finish

FIXTURES = Path(__file__).parent / "fixtures" / "espn"
AFTER_MNF = datetime(2026, 9, 15, 12, tzinfo=UTC)


def settings_for(w: World) -> LeagueSettings:
    return LeagueSeason.objects.get(league=w.league).settings


def play(
    w: World, member: Any, game: Game, *, home: bool, best_bet: bool = False
) -> Pick:
    team = game.home_team if home else game.away_team
    made = services.save_pick(member, w.week, game, team, now=OPEN)
    if best_bet:
        services.set_best_bet(member, w.week, game, on=True, now=OPEN)
        made.refresh_from_db()
    return made


def results(w: World) -> Any:
    week = LeagueWeek.objects.select_related(
        "league_season__settings", "league_season__league", "week", "tiebreaker_game"
    ).get(pk=w.week.pk)
    return week_results(week)


def finish_week(
    w: World, sea: tuple[int, int], kc: tuple[int, int], dal: tuple[int, int]
) -> None:
    finish(w.sea, *sea)
    finish(w.kc, *kc)
    finish(w.dal, *dal)


# Grading


def test_half_point_line_win_and_loss(world: World) -> None:
    sea_pick = play(world, world.member, world.sea, home=True)
    nyg_pick = play(world, world.member, world.dal, home=False)
    finish(world.sea, 24, 20)
    finish(world.dal, 30, 23)
    league_settings = settings_for(world)
    spreads = {s.game_id: s for s in Spread.objects.all()}
    assert (
        grade(sea_pick, world.sea, spreads[world.sea.pk], league_settings).outcome
        == Outcome.WIN
    )
    graded = grade(nyg_pick, world.dal, spreads[world.dal.pk], league_settings)
    assert graded.outcome == Outcome.WIN
    assert graded.points == Decimal(1)


def test_best_bet_win_is_worth_three(world: World) -> None:
    made = play(world, world.member, world.sea, home=True, best_bet=True)
    finish(world.sea, 30, 10)
    spread = Spread.objects.get(game=world.sea)
    assert grade(made, world.sea, spread, settings_for(world)).points == Decimal(3)


@pytest.mark.parametrize(
    ("push_scoring", "points"),
    [
        (PushScoring.HALF_POINTS, Decimal("0.5")),
        (PushScoring.LOSS, Decimal(0)),
        (PushScoring.WIN, Decimal(1)),
    ],
)
def test_push_scoring_when_half_points_are_off(
    world: World, push_scoring: PushScoring, points: Decimal
) -> None:
    made = play(world, world.member, world.sea, home=True)
    Spread.objects.filter(game=world.sea).update(home_line=Decimal("-3"))
    finish(world.sea, 23, 20)
    league_settings = settings_for(world)
    league_settings.push_scoring = push_scoring
    graded = grade(made, world.sea, Spread.objects.get(game=world.sea), league_settings)
    assert graded.outcome == Outcome.PUSH
    assert graded.points == points


def test_straight_up_ignores_the_line(world: World) -> None:
    made = play(world, world.member, world.sea, home=True)
    finish(world.sea, 21, 20)
    league_settings = settings_for(world)
    league_settings.pick_type = PickType.STRAIGHT_UP
    spread = Spread.objects.get(game=world.sea)
    assert grade(made, world.sea, spread, league_settings).outcome == Outcome.WIN


def test_variable_mode_uses_the_line_at_pick_time(world: World) -> None:
    made = play(world, world.member, world.sea, home=True)
    Pick.objects.filter(pk=made.pk).update(home_line_at_pick=Decimal("-1.5"))
    made.refresh_from_db()
    finish(world.sea, 22, 20)
    league_settings = settings_for(world)
    league_settings.line_mode = LineMode.VARIABLE
    spread = Spread.objects.get(game=world.sea)
    assert grade(made, world.sea, spread, league_settings).outcome == Outcome.WIN


def test_unfinished_and_cancelled_games(world: World) -> None:
    made = play(world, world.member, world.sea, home=True)
    spread = Spread.objects.get(game=world.sea)
    league_settings = settings_for(world)
    assert grade(made, world.sea, spread, league_settings).outcome == Outcome.PENDING
    Game.objects.filter(pk=world.sea.pk).update(status=GameStatus.CANCELLED)
    world.sea.refresh_from_db()
    assert grade(made, world.sea, spread, league_settings).outcome == Outcome.VOID


# Weekly winners


def test_weekly_winner_by_points_with_best_bet(world: World) -> None:
    play(world, world.member, world.sea, home=True, best_bet=True)
    play(world, world.member, world.kc, home=True)
    play(world, world.other, world.sea, home=False)
    play(world, world.other, world.kc, home=True)
    finish_week(world, sea=(24, 20), kc=(20, 18), dal=(30, 10))

    week = results(world)
    points = {m.membership: m.points for m in week.members}
    assert points[world.member] == Decimal(3)
    assert points[world.other] == Decimal(0)
    assert week.winners == [world.member]
    assert not week.decided_by_tiebreaker


def test_tie_broken_by_closest_tiebreaker_guess(world: World) -> None:
    for member in (world.member, world.other):
        play(world, member, world.sea, home=True)
    services.set_tiebreaker(world.member, world.week, 41, now=OPEN)
    services.set_tiebreaker(world.other, world.week, 45, now=OPEN)
    finish_week(world, sea=(24, 20), kc=(20, 18), dal=(30, 10))

    week = results(world)
    assert week.tiebreaker_actual == 40
    assert week.winners == [world.member]
    assert week.decided_by_tiebreaker


def test_equally_close_guesses_split_the_prize(world: World) -> None:
    for member in (world.member, world.other):
        play(world, member, world.sea, home=True)
    services.set_tiebreaker(world.member, world.week, 38, now=OPEN)
    services.set_tiebreaker(world.other, world.week, 42, now=OPEN)
    finish_week(world, sea=(24, 20), kc=(20, 18), dal=(30, 10))

    week = results(world)
    assert set(week.winners) == {world.member, world.other}
    assert week.is_split


def test_missing_guess_loses_the_tiebreak(world: World) -> None:
    for member in (world.member, world.other):
        play(world, member, world.sea, home=True)
    services.set_tiebreaker(world.other, world.week, 99, now=OPEN)
    finish_week(world, sea=(24, 20), kc=(20, 18), dal=(30, 10))
    assert results(world).winners == [world.other]


def test_tied_leaders_stay_tied_until_tiebreaker_game_ends(world: World) -> None:
    for member in (world.member, world.other):
        play(world, member, world.sea, home=True)
    services.set_tiebreaker(world.member, world.week, 41, now=OPEN)
    finish(world.sea, 24, 20)
    week = results(world)
    assert set(week.winners) == {world.member, world.other}
    assert not week.decided_by_tiebreaker


def test_wins_metric_counts_best_bet_once(world: World) -> None:
    league_settings = settings_for(world)
    league_settings.weekly_prize_metric = WeeklyPrizeMetric.WINS
    league_settings.save()
    play(world, world.member, world.sea, home=True, best_bet=True)
    play(world, world.other, world.sea, home=True)
    play(world, world.other, world.dal, home=True)
    finish_week(world, sea=(24, 20), kc=(20, 18), dal=(30, 10))
    assert results(world).winners == [world.other]


# Week status


def test_week_goes_final_and_records_winners(world: World) -> None:
    play(world, world.member, world.sea, home=True)
    update_week_statuses(SUNDAY_LOCKED)
    assert (
        LeagueWeek.objects.get(pk=world.week.pk).status == LeagueWeekStatus.IN_PROGRESS
    )

    finish_week(world, sea=(24, 20), kc=(20, 18), dal=(30, 10))
    update_week_statuses(AFTER_MNF)
    assert LeagueWeek.objects.get(pk=world.week.pk).status == LeagueWeekStatus.FINAL
    event = ActivityEvent.objects.get(event_type="standings.weekly_winners")
    assert str(world.member.user) in event.summary


def test_postponed_game_holds_the_week_open(world: World) -> None:
    finish(world.sea, 24, 20)
    finish(world.kc, 20, 18)
    Game.objects.filter(pk=world.dal.pk).update(status=GameStatus.POSTPONED)
    update_week_statuses(AFTER_MNF)
    assert (
        LeagueWeek.objects.get(pk=world.week.pk).status == LeagueWeekStatus.IN_PROGRESS
    )

    finish(world.dal, 30, 10)
    update_week_statuses(AFTER_MNF + timedelta(days=9))
    assert LeagueWeek.objects.get(pk=world.week.pk).status == LeagueWeekStatus.FINAL


def test_void_game_scores_zero_for_everyone(world: World) -> None:
    play(world, world.member, world.dal, home=True)
    Spread.objects.filter(game=world.dal).update(
        status=SpreadStatus.VOID, home_line=None
    )
    finish_week(world, sea=(24, 20), kc=(20, 18), dal=(30, 10))
    member = next(m for m in results(world).members if m.membership == world.member)
    assert member.points == 0


# Season standings


def test_season_standings_rank_and_best_bets(world: World) -> None:
    play(world, world.member, world.sea, home=True, best_bet=True)
    play(world, world.other, world.sea, home=True)
    play(world, world.other, world.kc, home=False)
    play(world, world.other, world.dal, home=True)
    finish_week(world, sea=(24, 20), kc=(20, 18), dal=(30, 10))
    update_week_statuses(SUNDAY_LOCKED)
    update_week_statuses(AFTER_MNF)

    standings = season_standings(LeagueSeason.objects.get(league=world.league))
    rows = {row.membership: row for row in standings.rows}
    assert rows[world.member].points == Decimal(3)
    assert rows[world.other].points == Decimal(3)
    assert rows[world.member].rank == rows[world.other].rank == 1
    assert set(standings.points_leaders) == {world.member, world.other}
    assert standings.best_bet_leaders == [world.member]
    assert rows[world.member].weekly_wins == rows[world.other].weekly_wins == 1
    assert not standings.is_complete


def test_deactivated_member_keeps_their_week(world: World) -> None:
    play(world, world.other, world.sea, home=True)
    world.other.is_active = False
    world.other.save()
    finish_week(world, sea=(24, 20), kc=(20, 18), dal=(30, 10))
    members = [m.membership for m in results(world).members]
    assert world.other in members


# Score sync


def test_espn_scores_parsed_only_for_live_or_final_games() -> None:
    final = json.loads((FIXTURES / "scoreboard_2026_week1.json").read_text())
    upcoming = json.loads((FIXTURES / "scoreboard_2026_week12.json").read_text())
    game = parse_games(final)[0]
    assert (game.home_score, game.away_score) == (13, 10)
    assert parse_games(upcoming)[0].home_score is None


class CountingProvider:
    def __init__(self) -> None:
        self.weeks_requested: list[int] = []

    def fetch_weeks(self, season: int) -> list[Any]:
        raise AssertionError("calendar should come from the database")

    def fetch_games(self, season: int, week: int) -> list[Any]:
        self.weeks_requested.append(week)
        return []


def test_score_sync_skips_feed_when_nothing_is_live(world: World) -> None:
    provider = CountingProvider()
    assert sync_scores(provider, season_year=2026, now=OPEN) is None
    assert provider.weeks_requested == []


def test_score_sync_fetches_only_live_weeks(world: World) -> None:
    season = Season.objects.get(year=2026)
    assert weeks_with_live_games(season, SUNDAY_LOCKED) == [1]
    provider = CountingProvider()
    sync_scores(provider, season_year=2026, now=SUNDAY_LOCKED)
    assert provider.weeks_requested == [1]


# Views


def test_standings_pages_render(client: Client, world: World) -> None:
    play(world, world.member, world.sea, home=True)
    services.set_tiebreaker(world.other, world.week, 51, now=OPEN)
    finish_week(world, sea=(24, 20), kc=(20, 18), dal=(30, 10))
    client.force_login(world.member.user)

    season = client.get(reverse("standings:season", args=[world.league.slug]))
    assert season.status_code == 200
    with time_machine.travel(OPEN):
        week = client.get(
            reverse("standings:week", args=[world.league.slug]), {"week": 1}
        )
    assert week.status_code == 200
    assert b"51" not in week.content
    assert b"Hidden" in week.content
