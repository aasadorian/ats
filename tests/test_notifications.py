from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from apps.leagues.models import LeagueWeek, LeagueWeekStatus, Role
from apps.leagues.services import change_role
from apps.notifications.email import unsubscribe_token
from apps.notifications.models import Dispatch, Kind, NotificationPreference
from apps.notifications.services import reminder_slots, send_notifications
from apps.picks import services as pick_services
from apps.standings.services import update_week_statuses
from tests.world import OPEN, World, finish

THURSDAY_REMINDER = datetime(2026, 9, 10, 19, 30, tzinfo=UTC)
AFTER_MNF = datetime(2026, 9, 15, 12, tzinfo=UTC)


def recipients(subject_part: str) -> set[str]:
    return {
        address
        for message in mail.outbox
        if subject_part in message.subject
        for address in message.to
    }


def test_reminder_slots_fall_inside_the_picking_window(world: World) -> None:
    slots = reminder_slots(world.week)
    assert [slot.astimezone(UTC) for slot in slots] == [
        datetime(2026, 9, 10, 19, 0, tzinfo=UTC),
        datetime(2026, 9, 13, 15, 0, tzinfo=UTC),
    ]


def test_week_open_emails_members_and_commissioner_once(world: World) -> None:
    send_notifications(OPEN)
    members = recipients("make your picks")
    assert world.member.user.email in members
    assert world.other.user.email in members
    commissioner = world.league.memberships.get(role=Role.COMMISSIONER).user
    assert recipients("lines locked") == {commissioner.email}
    count = len(mail.outbox)

    send_notifications(OPEN + timedelta(minutes=15))
    assert len(mail.outbox) == count
    assert Dispatch.objects.get(kind=Kind.WEEK_OPEN).recipients == count


def test_opted_out_member_gets_nothing(world: World) -> None:
    NotificationPreference.objects.create(
        user=world.member.user, kind=Kind.WEEK_OPEN, enabled=False
    )
    send_notifications(OPEN)
    assert world.member.user.email not in recipients("make your picks")


def test_emails_carry_one_click_unsubscribe(world: World) -> None:
    send_notifications(OPEN)
    message = next(m for m in mail.outbox if "make your picks" in m.subject)
    assert "/unsubscribe/" in message.extra_headers["List-Unsubscribe"]
    assert (
        message.extra_headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    )
    assert "/unsubscribe/" in message.body


def test_reminder_only_to_members_with_something_missing(world: World) -> None:
    for game in (world.kc, world.dal):
        pick_services.save_pick(
            world.member, world.week, game, game.home_team, now=OPEN
        )
    pick_services.set_best_bet(world.member, world.week, world.kc, on=True, now=OPEN)
    pick_services.set_tiebreaker(world.member, world.week, 44, now=OPEN)
    send_notifications(OPEN)
    mail.outbox.clear()

    send_notifications(THURSDAY_REMINDER)
    reminded = recipients("Reminder")
    assert world.other.user.email in reminded
    assert world.member.user.email not in reminded

    mail.outbox.clear()
    send_notifications(THURSDAY_REMINDER + timedelta(minutes=15))
    assert recipients("Reminder") == set()


def test_late_reminders_are_skipped(world: World) -> None:
    send_notifications(datetime(2026, 9, 11, 4, 0, tzinfo=UTC))
    assert recipients("Reminder") == set()


def test_weekly_results_sent_once_after_final(world: World) -> None:
    pick_services.save_pick(
        world.member, world.week, world.kc, world.kc.home_team, now=OPEN
    )
    for game, score in (
        (world.sea, (24, 20)),
        (world.kc, (30, 10)),
        (world.dal, (30, 10)),
    ):
        finish(game, *score)
    update_week_statuses(datetime(2026, 9, 13, 18, tzinfo=UTC))
    update_week_statuses(AFTER_MNF)
    assert LeagueWeek.objects.get(pk=world.week.pk).status == LeagueWeekStatus.FINAL

    send_notifications(AFTER_MNF)
    results = [m for m in mail.outbox if "results" in m.subject]
    member_mail = next(m for m in results if world.member.user.email in m.to)
    assert "Winner" in member_mail.body
    assert "1 points (1-0-0)" in member_mail.body
    count = len(mail.outbox)
    send_notifications(AFTER_MNF + timedelta(hours=1))
    assert len(mail.outbox) == count


def test_unsubscribe_link_disables_that_email(client: Client, world: World) -> None:
    url = reverse(
        "notifications:unsubscribe",
        args=[unsubscribe_token(world.member.user, Kind.REMINDERS)],
    )
    assert client.get(url).status_code == 200
    assert client.post(url).status_code == 200
    assert not NotificationPreference.objects.get(
        user=world.member.user, kind=Kind.REMINDERS
    ).enabled


def test_tampered_unsubscribe_token_is_rejected(client: Client, world: World) -> None:
    url = reverse("notifications:unsubscribe", args=["not-a-real-token"])
    assert client.post(url).status_code == 404


def test_preferences_page_saves(client: Client, world: World) -> None:
    client.force_login(world.member.user)
    url = reverse("notifications:preferences")
    assert client.get(url).status_code == 200
    client.post(url, {"week_open": "on", "weekly_results": "on"})
    assert not NotificationPreference.objects.get(
        user=world.member.user, kind=Kind.REMINDERS
    ).enabled


@pytest.mark.django_db
def test_role_change_emails_the_member(
    world: World, django_capture_on_commit_callbacks: Any
) -> None:
    commissioner = world.league.memberships.get(role=Role.COMMISSIONER).user
    with django_capture_on_commit_callbacks(execute=True):
        change_role(world.member, Role.COMMISSIONER, actor=commissioner)
    assert recipients("role") == {world.member.user.email}
