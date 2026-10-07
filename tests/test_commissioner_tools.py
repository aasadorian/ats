from datetime import UTC, datetime, time, timedelta
from typing import Any

import pytest
import time_machine
from django.core import mail
from django.test import Client
from django.urls import reverse

from apps.accounts.services import delete_account
from apps.activity.context import event_context
from apps.activity.models import ActivityEvent
from apps.activity.selectors import LogFilters, commissioner_log, visible
from apps.activity.services import prune_ip_addresses, record_event
from apps.leagues import services as league_services
from apps.leagues.models import LeagueSeason, LeagueWeek, Membership, Role, Weekday
from apps.nfl.feeds.types import GameData, TeamData
from apps.nfl.models import GameStatus
from apps.nfl.services import sync_schedule
from apps.picks import services as pick_services
from apps.picks.models import Pick
from apps.standings.services import correct_score, restore_feed_score
from tests.world import OPEN, SUNDAY_LOCKED, World


def commissioner(w: World) -> Any:
    return w.league.memberships.get(role=Role.COMMISSIONER).user


@pytest.fixture
def no_mfa(settings: Any) -> None:
    settings.COMMISSIONER_MFA_REQUIRED = False


# Settings


def test_scoring_change_after_season_starts_needs_confirmation(world: World) -> None:
    league_settings = LeagueSeason.objects.get(league=world.league).settings
    with pytest.raises(league_services.RetroactiveChangeError):
        league_services.update_settings(
            league_settings, {"best_bet_bonus": 4}, actor=commissioner(world)
        )
    changed = league_services.update_settings(
        league_settings,
        {"best_bet_bonus": 4},
        actor=commissioner(world),
        apply_to_season=True,
    )
    assert changed == ["best_bet_bonus"]
    event = ActivityEvent.objects.get(event_type="settings.changed")
    assert event.before == {"best_bet_bonus": 2}
    assert "whole season" in event.summary


def test_lock_time_change_only_moves_unopened_weeks(world: World) -> None:
    league_settings = LeagueSeason.objects.get(league=world.league).settings
    week1_before = LeagueWeek.objects.get(week__number=1).spreads_lock_at
    league_services.update_settings(
        league_settings,
        {"spread_lock_weekday": Weekday.WEDNESDAY, "spread_lock_time": time(6, 0)},
        actor=commissioner(world),
    )
    assert LeagueWeek.objects.get(week__number=1).spreads_lock_at == week1_before
    week2 = LeagueWeek.objects.get(week__number=2)
    assert week2.spreads_lock_at == datetime(2026, 9, 16, 13, 0, tzinfo=UTC)


def test_settings_page_saves(client: Client, world: World, no_mfa: None) -> None:
    client.force_login(commissioner(world))
    url = reverse("leagues:settings", args=[world.league.slug])
    page = client.get(url)
    assert page.status_code == 200
    data = {
        key: value
        for key, value in page.context["form"].initial.items()
        if key in page.context["form"].fields
    }
    data = {k: ("on" if v is True else v) for k, v in data.items() if v is not False}
    data["tiebreaker_type"] = "margin_of_victory"
    response = client.post(url, data)
    assert response.status_code == 302
    league_settings = LeagueSeason.objects.get(league=world.league).settings
    assert league_settings.tiebreaker_type == "margin_of_victory"


# Score corrections


def test_corrected_score_survives_feed_sync(world: World) -> None:
    correct_score(
        world.sea,
        home_score=27,
        away_score=24,
        league=world.league,
        actor=commissioner(world),
        reason="Feed missed a late touchdown",
    )

    class Provider:
        def fetch_weeks(self, season: int) -> list[Any]:
            raise AssertionError

        def fetch_games(self, season: int, week: int) -> list[GameData]:
            game = world.sea
            return [
                GameData(
                    external_id=game.external_id,
                    week_number=1,
                    home_team=TeamData("SEA", "SEA", "Seattle", "Seahawks"),
                    away_team=TeamData("NE", "NE", "New England", "Patriots"),
                    kickoff_at=game.kickoff_at,
                    kickoff_is_tbd=False,
                    status=GameStatus.FINAL,
                    neutral_site=False,
                    home_score=20,
                    away_score=24,
                )
            ]

    sync_schedule(Provider(), season_year=2026, weeks=[1])
    world.sea.refresh_from_db()
    assert (world.sea.home_score, world.sea.away_score) == (27, 24)

    restore_feed_score(world.sea, league=world.league, actor=commissioner(world))
    sync_schedule(Provider(), season_year=2026, weeks=[1])
    world.sea.refresh_from_db()
    assert (world.sea.home_score, world.sea.away_score) == (20, 24)


# Commissioner pick entry


def test_commissioner_enters_pick_for_member(
    client: Client, world: World, no_mfa: None, django_capture_on_commit_callbacks: Any
) -> None:
    client.force_login(commissioner(world))
    url = reverse("picks:member_picks", args=[world.league.slug, world.member.pk])
    with time_machine.travel(OPEN), django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            url,
            {
                "week": 1,
                "game": world.kc.pk,
                "team": world.kc.home_team.pk,
                "best_bet": "on",
                "reason": "Texted me before kickoff",
            },
        )
    assert response.status_code == 302
    made = Pick.objects.get(membership=world.member, game=world.kc)
    assert made.is_best_bet
    event = ActivityEvent.objects.get(event_type="pick.entered_for_member")
    assert event.subject_user == world.member.user
    assert len(mail.outbox) == 1
    assert "Texted me before kickoff" in mail.outbox[0].body


def test_commissioner_pick_entry_respects_locks(
    client: Client, world: World, no_mfa: None
) -> None:
    client.force_login(commissioner(world))
    url = reverse("picks:member_picks", args=[world.league.slug, world.member.pk])
    with time_machine.travel(SUNDAY_LOCKED):
        client.post(
            url,
            {
                "week": 1,
                "game": world.kc.pk,
                "team": world.kc.home_team.pk,
                "reason": "x",
            },
        )
    assert not Pick.objects.exists()


# Activity log


def test_other_members_pick_events_hidden_until_deadline(world: World) -> None:
    pick_services.save_pick(
        world.other, world.week, world.kc, world.kc.away_team, now=OPEN
    )
    event = ActivityEvent.objects.get(event_type="pick.made")
    viewer = commissioner(world)
    hidden = visible(event, viewer, OPEN)
    assert hidden.redacted
    assert "BUF" not in hidden.summary
    assert hidden.after is None
    shown = visible(event, viewer, SUNDAY_LOCKED)
    assert not shown.redacted
    assert "BUF" in shown.summary
    assert visible(event, world.other.user, OPEN).summary == event.summary


def test_commissioner_log_filters_by_member(world: World) -> None:
    pick_services.save_pick(
        world.member, world.week, world.kc, world.kc.home_team, now=OPEN
    )
    pick_services.save_pick(
        world.other, world.week, world.kc, world.kc.home_team, now=OPEN
    )
    events = commissioner_log(world.league, LogFilters(member=world.member.user))
    assert events.filter(event_type="pick.made").count() == 1


def test_activity_pages_render_and_export(
    client: Client, world: World, no_mfa: None
) -> None:
    pick_services.save_pick(
        world.other, world.week, world.kc, world.kc.away_team, now=OPEN
    )
    client.force_login(commissioner(world))
    with time_machine.travel(OPEN):
        log = client.get(reverse("activity:log", args=[world.league.slug]))
        csv = client.get(
            reverse("activity:log", args=[world.league.slug]), {"format": "csv"}
        )
    assert log.status_code == 200
    assert b"updated their picks" in log.content
    assert b"picked BUF" not in log.content
    assert csv["Content-Type"] == "text/csv"
    assert b"updated their picks" in csv.content

    client.force_login(world.member.user)
    assert (
        client.get(reverse("activity:feed", args=[world.league.slug])).status_code
        == 200
    )
    assert (
        client.get(reverse("activity:mine", args=[world.league.slug])).status_code
        == 200
    )
    assert (
        client.get(reverse("activity:log", args=[world.league.slug])).status_code == 404
    )


# Account actions


def test_member_can_leave_but_last_commissioner_cannot(world: World) -> None:
    league_services.leave_league(world.member)
    world.member.refresh_from_db()
    assert not world.member.is_active
    assert ActivityEvent.objects.filter(event_type="member.left").exists()
    only = world.league.memberships.get(role=Role.COMMISSIONER)
    with pytest.raises(league_services.LastCommissionerError):
        league_services.leave_league(only)


def test_deleted_account_is_anonymized_but_picks_remain(world: World) -> None:
    user = world.member.user
    email = user.email
    record_event(
        event_type="invite.sent", summary=f"invited {email}", after={"email": email}
    )
    pick_services.save_pick(
        world.member, world.week, world.kc, world.kc.home_team, now=OPEN
    )

    delete_account(user)

    user.refresh_from_db()
    assert user.email.endswith("@invalid.example")
    assert user.display_name == f"Former member #{user.pk}"
    assert not user.has_usable_password()
    assert not Membership.objects.get(pk=world.member.pk).is_active
    assert Pick.objects.filter(membership=world.member).count() == 1
    for event in ActivityEvent.objects.all():
        assert email not in event.summary
        assert email not in str(event.after)


def test_old_ip_addresses_are_pruned(world: World) -> None:
    with event_context("web", ip_address="203.0.113.9"):
        event = record_event(event_type="auth.login_failed", summary="x")
    assert prune_ip_addresses(event.occurred_at + timedelta(days=30)) == 0
    assert prune_ip_addresses(event.occurred_at + timedelta(days=91)) == 1
    event.refresh_from_db()
    assert event.ip_address is None
