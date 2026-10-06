from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import time_machine
from django.core import mail
from django.utils import timezone

from apps.activity.models import ActivityEvent
from apps.leagues import services
from apps.leagues.models import Invite, LeagueSeason, Membership, Role
from apps.nfl.models import Game, Season, Week
from tests.factories import SEASON_YEAR, make_game, make_league, make_user

CaptureCallbacks = Callable[..., AbstractContextManager[Any]]


@pytest.mark.django_db
def test_create_league_sets_up_commissioner_settings_and_weeks() -> None:
    commissioner = make_user()
    league = make_league(commissioner)

    membership = Membership.objects.get(league=league)
    assert membership.user == commissioner
    assert membership.role == Role.COMMISSIONER
    league_season = LeagueSeason.objects.get(league=league)
    assert league_season.settings.best_bet_bonus == 2
    assert league_season.weeks.count() == 2


@pytest.mark.django_db
def test_league_weeks_get_default_lock_times_and_last_game_tiebreaker() -> None:
    league = make_league()
    week1 = LeagueSeason.objects.get(league=league).weeks.get(week__number=1)
    assert week1.spreads_lock_at == datetime(2026, 9, 8, 10, 0, tzinfo=UTC)
    assert week1.picks_lock_at == datetime(2026, 9, 13, 17, 0, tzinfo=UTC)
    assert week1.tiebreaker_game is not None
    assert str(week1.tiebreaker_game) == "NYG @ DAL"


@pytest.mark.django_db
def test_tiebreaker_follows_schedule_until_picks_lock() -> None:
    league = make_league()
    league_season = LeagueSeason.objects.get(league=league)
    week = Week.objects.get(season__year=SEASON_YEAR, number=1)
    late = make_game(week, "LAR", "SF", kickoff_offset=timedelta(days=1, hours=4))

    with time_machine.travel(datetime(2026, 9, 9, tzinfo=UTC)):
        services.refresh_tiebreaker_games(league_season)
    assert league_season.weeks.get(week=week).tiebreaker_game == late

    Game.objects.filter(pk=late.pk).update(
        kickoff_at=late.kickoff_at - timedelta(days=2)
    )
    with time_machine.travel(datetime(2026, 9, 14, tzinfo=UTC)):
        services.refresh_tiebreaker_games(league_season)
    assert league_season.weeks.get(week=week).tiebreaker_game == late


@pytest.mark.django_db
def test_new_season_copies_previous_settings() -> None:
    league = make_league()
    settings_2026 = LeagueSeason.objects.get(league=league).settings
    settings_2026.best_bet_bonus = 4
    settings_2026.save()

    season_2027 = Season.objects.create(year=2027)
    league_season = services.start_league_season(league, season_2027)
    assert league_season.settings.best_bet_bonus == 4
    assert league_season.settings.pk != settings_2026.pk


@pytest.mark.django_db
def test_invite_member_sends_email_and_logs(
    django_capture_on_commit_callbacks: CaptureCallbacks,
) -> None:
    league = make_league()
    commissioner = league.memberships.get().user
    with django_capture_on_commit_callbacks(execute=True):
        invite, token = services.invite_member(
            league, email="New@Example.com", role=Role.MEMBER, invited_by=commissioner
        )

    assert invite.email == "new@example.com"
    assert invite.token_hash == services.hash_token(token)
    assert token not in invite.token_hash
    assert len(mail.outbox) == 1
    assert f"/invites/{token}/" in mail.outbox[0].body
    assert ActivityEvent.objects.filter(event_type="invite.sent").exists()


@pytest.mark.django_db
def test_new_invite_replaces_pending_invite() -> None:
    league = make_league()
    commissioner = league.memberships.get().user
    first, _ = services.invite_member(
        league, email="a@example.com", role=Role.MEMBER, invited_by=commissioner
    )
    services.invite_member(
        league, email="a@example.com", role=Role.MEMBER, invited_by=commissioner
    )
    first.refresh_from_db()
    assert first.revoked_at is not None
    assert Invite.objects.pending().count() == 1


@pytest.mark.django_db
def test_cannot_invite_existing_member() -> None:
    commissioner = make_user()
    league = make_league(commissioner)
    with pytest.raises(services.AlreadyMemberError):
        services.invite_member(
            league, email=commissioner.email, role=Role.MEMBER, invited_by=commissioner
        )


@pytest.mark.django_db
def test_accept_invite_creates_membership_once() -> None:
    league = make_league()
    commissioner = league.memberships.get().user
    invite, _ = services.invite_member(
        league, email="a@example.com", role=Role.MEMBER, invited_by=commissioner
    )
    member = make_user(email="a@example.com")

    membership = services.accept_invite(invite, member)
    assert membership.role == Role.MEMBER
    assert membership.is_active
    with pytest.raises(services.InviteError):
        services.accept_invite(invite, member)


@pytest.mark.django_db
def test_invite_only_works_for_invited_email() -> None:
    league = make_league()
    commissioner = league.memberships.get().user
    invite, _ = services.invite_member(
        league, email="a@example.com", role=Role.MEMBER, invited_by=commissioner
    )
    with pytest.raises(services.InviteError):
        services.accept_invite(invite, make_user(email="b@example.com"))


@pytest.mark.django_db
def test_expired_invite_is_rejected() -> None:
    league = make_league()
    commissioner = league.memberships.get().user
    invite, _ = services.invite_member(
        league, email="a@example.com", role=Role.MEMBER, invited_by=commissioner
    )
    member = make_user(email="a@example.com")
    with (
        time_machine.travel(timezone.now() + timedelta(days=15)),
        pytest.raises(services.InviteError),
    ):
        services.accept_invite(invite, member)


@pytest.mark.django_db
def test_league_keeps_at_least_one_commissioner() -> None:
    league = make_league()
    only = league.memberships.get()
    with pytest.raises(services.LastCommissionerError):
        services.change_role(only, Role.MEMBER, actor=only.user)
    with pytest.raises(services.LastCommissionerError):
        services.deactivate_membership(only, actor=only.user)


@pytest.mark.django_db
def test_deactivate_and_reactivate_member() -> None:
    league = make_league()
    commissioner = league.memberships.get().user
    member = Membership.objects.create(user=make_user(), league=league)

    services.deactivate_membership(member, actor=commissioner)
    member.refresh_from_db()
    assert not member.is_active
    assert member.deactivated_at is not None

    services.reactivate_membership(member, actor=commissioner)
    member.refresh_from_db()
    assert member.is_active
    assert (
        ActivityEvent.objects.filter(
            event_type__in=["membership.deactivated", "membership.reactivated"],
            subject_user=member.user,
        ).count()
        == 2
    )
