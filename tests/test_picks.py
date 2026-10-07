from decimal import Decimal
from typing import Any

import pytest
import time_machine
from django.test import Client
from django.urls import reverse

from apps.activity.models import ActivityEvent
from apps.leagues.models import (
    LeagueSeason,
    LeagueWeek,
    Membership,
    PickVisibility,
)
from apps.nfl.models import Game
from apps.picks import services
from apps.picks.models import Pick
from apps.picks.selectors import pick_sheet, picks_grid
from tests.factories import make_league, make_user
from tests.world import (
    KC_BUF,
    OPEN,
    SEA_NE,
    SUNDAY_LOCKED,
    THURSDAY_NIGHT,
    World,
    build,
)


def pick(w: World, game: Game, home: bool = True, **kwargs: Any) -> Pick:
    team = game.home_team if home else game.away_team
    return services.save_pick(w.member, w.week, game, team, now=OPEN, **kwargs)


def test_pick_records_line_and_event(world: World) -> None:
    made = pick(world, world.sea)
    assert made.team == world.sea.home_team
    assert made.home_line_at_pick == Decimal("-3.5")
    event = ActivityEvent.objects.get(event_type="pick.made")
    assert event.subject_user == world.member.user
    assert event.league_week == world.week


def test_changing_team_updates_pick(world: World) -> None:
    pick(world, world.sea)
    pick(world, world.sea, home=False)
    assert Pick.objects.get().team == world.sea.away_team
    assert ActivityEvent.objects.filter(event_type="pick.changed").count() == 1


def test_locked_game_rejects_changes_and_logs_attempt(world: World) -> None:
    with pytest.raises(services.PickLockedError):
        services.save_pick(
            world.member, world.week, world.sea, world.sea.home_team, now=THURSDAY_NIGHT
        )
    assert not Pick.objects.exists()
    assert ActivityEvent.objects.filter(event_type="pick.rejected_locked").exists()


def test_sunday_lock_closes_late_games(world: World) -> None:
    with pytest.raises(services.PickLockedError):
        services.save_pick(
            world.member, world.week, world.dal, world.dal.home_team, now=SUNDAY_LOCKED
        )


def test_game_without_line_cannot_be_picked(db: None) -> None:
    w = build([SEA_NE, KC_BUF])
    with pytest.raises(services.PickError, match="no line"):
        services.save_pick(w.member, w.week, w.dal, w.dal.home_team, now=OPEN)


def test_week_not_published_cannot_be_picked(world: World) -> None:
    week2 = LeagueWeek.objects.get(week__number=2)
    game = week2.week.games.first()
    assert game is not None
    with pytest.raises(services.PickError, match="isn't open"):
        services.save_pick(world.member, week2, game, game.home_team, now=OPEN)


def test_member_of_another_league_is_rejected(world: World) -> None:
    outsider = Membership.objects.create(
        user=make_user(), league=make_league(slug="other")
    )
    with pytest.raises(services.PickError):
        services.save_pick(
            outsider, world.week, world.sea, world.sea.home_team, now=OPEN
        )


def test_best_bet_requires_a_pick(world: World) -> None:
    with pytest.raises(services.PickError, match="Pick a team"):
        services.set_best_bet(world.member, world.week, world.sea, on=True, now=OPEN)


def test_best_bet_moves_when_limit_is_one(world: World) -> None:
    pick(world, world.sea)
    pick(world, world.kc)
    services.set_best_bet(world.member, world.week, world.sea, on=True, now=OPEN)
    services.set_best_bet(world.member, world.week, world.kc, on=True, now=OPEN)
    stars = list(Pick.objects.filter(is_best_bet=True).values_list("game", flat=True))
    assert stars == [world.kc.pk]
    assert ActivityEvent.objects.filter(event_type="best_bet.moved").exists()


def test_locked_best_bet_cannot_be_moved(world: World) -> None:
    pick(world, world.sea)
    pick(world, world.kc)
    services.set_best_bet(world.member, world.week, world.sea, on=True, now=OPEN)
    with pytest.raises(services.PickLockedError, match="locked"):
        services.set_best_bet(
            world.member, world.week, world.kc, on=True, now=THURSDAY_NIGHT
        )
    assert Pick.objects.get(game=world.sea).is_best_bet


def test_best_bet_limit_above_one(world: World) -> None:
    league_settings = LeagueSeason.objects.get(league=world.league).settings
    league_settings.best_bets_per_week = 2
    league_settings.save()
    world.week.refresh_from_db()
    world.week.league_season.refresh_from_db()
    for game in (world.sea, world.kc, world.dal):
        pick(world, game)
    services.set_best_bet(world.member, world.week, world.sea, on=True, now=OPEN)
    services.set_best_bet(world.member, world.week, world.kc, on=True, now=OPEN)
    with pytest.raises(services.PickError, match="remove one first"):
        services.set_best_bet(world.member, world.week, world.dal, on=True, now=OPEN)


def test_clearing_a_pick_removes_its_best_bet(world: World) -> None:
    pick(world, world.sea)
    services.set_best_bet(world.member, world.week, world.sea, on=True, now=OPEN)
    services.clear_pick(world.member, world.week, world.sea, now=OPEN)
    assert not Pick.objects.exists()


def test_tiebreaker_guess_locks_with_the_week(world: World) -> None:
    services.set_tiebreaker(world.member, world.week, 44, now=OPEN)
    services.set_tiebreaker(world.member, world.week, 47, now=THURSDAY_NIGHT)
    with pytest.raises(services.PickLockedError):
        services.set_tiebreaker(world.member, world.week, 50, now=SUNDAY_LOCKED)
    events = ActivityEvent.objects.filter(event_type__startswith="tiebreaker.")
    assert list(events.values_list("event_type", flat=True).order_by("id")) == [
        "tiebreaker.set",
        "tiebreaker.changed",
    ]


def test_sheet_shows_game_states(db: None) -> None:
    w = build([SEA_NE, KC_BUF])
    sheet = pick_sheet(w.member, w.week, THURSDAY_NIGHT)
    states = {row.game.home_team.abbreviation: row.state for row in sheet.rows}
    assert states == {"SEA": "locked", "KC": "open", "DAL": "off"}
    kc = next(row for row in sheet.rows if row.game == w.kc)
    assert (kc.home_text, kc.away_text) == ("-2.5", "+2.5")


def test_grid_hides_unlocked_picks_of_others(world: World) -> None:
    services.save_pick(
        world.other, world.week, world.sea, world.sea.away_team, now=OPEN
    )
    services.save_pick(world.other, world.week, world.kc, world.kc.away_team, now=OPEN)
    pick(world, world.kc)

    grid = picks_grid(world.week, world.member, THURSDAY_NIGHT)
    other_row = next(r for r in grid.rows if r.membership == world.other)
    own_row = next(r for r in grid.rows if r.membership == world.member)
    sea_index, kc_index = 0, 1

    assert other_row.cells[sea_index].pick is not None
    assert other_row.cells[kc_index].pick is None
    assert other_row.cells[kc_index].has_pick
    assert own_row.cells[kc_index].pick is not None


def test_weekly_deadline_visibility_hides_early_games(world: World) -> None:
    league_settings = LeagueSeason.objects.get(league=world.league).settings
    league_settings.pick_visibility = PickVisibility.AT_WEEKLY_DEADLINE
    league_settings.save()
    services.save_pick(
        world.other, world.week, world.sea, world.sea.away_team, now=OPEN
    )
    week = LeagueWeek.objects.select_related("league_season__settings", "week").get(
        pk=world.week.pk
    )
    grid = picks_grid(week, world.member, THURSDAY_NIGHT)
    other_row = next(r for r in grid.rows if r.membership == world.other)
    assert other_row.cells[0].pick is None


def test_tiebreaker_guesses_hidden_until_lock(world: World) -> None:
    services.set_tiebreaker(world.other, world.week, 51, now=OPEN)
    before = picks_grid(world.week, world.member, THURSDAY_NIGHT)
    after = picks_grid(world.week, world.member, SUNDAY_LOCKED)
    other_before = next(r for r in before.rows if r.membership == world.other)
    other_after = next(r for r in after.rows if r.membership == world.other)
    assert other_before.tiebreaker_guess is None
    assert other_after.tiebreaker_guess == 51


def test_sheet_page_for_members_only(client: Client, world: World) -> None:
    url = reverse("picks:sheet", args=[world.league.slug])
    client.force_login(make_user())
    assert client.get(url).status_code == 404
    client.force_login(world.member.user)
    with time_machine.travel(OPEN):
        response = client.get(url, {"week": 1})
    assert response.status_code == 200
    assert b"SEA" in response.content


def test_htmx_pick_returns_updated_sheet(client: Client, world: World) -> None:
    client.force_login(world.member.user)
    with time_machine.travel(OPEN):
        response = client.post(
            reverse("picks:pick", args=[world.league.slug]),
            {"week": 1, "game": world.sea.pk, "team": world.sea.home_team.pk},
            HTTP_HX_REQUEST="true",
        )
    assert response.status_code == 200
    assert b'id="sheet"' in response.content
    assert b"<html" not in response.content
    assert Pick.objects.filter(membership=world.member, game=world.sea).exists()


def test_plain_post_redirects_back_to_sheet(client: Client, world: World) -> None:
    client.force_login(world.member.user)
    with time_machine.travel(OPEN):
        response = client.post(
            reverse("picks:pick", args=[world.league.slug]),
            {"week": 1, "game": world.sea.pk, "team": world.sea.away_team.pk},
        )
    assert response.status_code == 302
    assert Pick.objects.get().team == world.sea.away_team


def test_locked_pick_error_shown_in_partial(client: Client, world: World) -> None:
    client.force_login(world.member.user)
    with time_machine.travel(THURSDAY_NIGHT):
        response = client.post(
            reverse("picks:pick", args=[world.league.slug]),
            {"week": 1, "game": world.sea.pk, "team": world.sea.home_team.pk},
            HTTP_HX_REQUEST="true",
        )
    assert b"is locked" in response.content
    assert not Pick.objects.exists()


def test_grid_page_does_not_leak_hidden_picks(client: Client, world: World) -> None:
    services.save_pick(world.other, world.week, world.kc, world.kc.away_team, now=OPEN)
    client.force_login(world.member.user)
    with time_machine.travel(THURSDAY_NIGHT):
        response = client.get(
            reverse("picks:grid", args=[world.league.slug]), {"week": 1}
        )
    body = response.content.decode()
    other_row = body[body.index(str(world.other.user)) :].split("</tr>")[0]
    assert "BUF" not in other_row
    assert "Picked" in other_row
