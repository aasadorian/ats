import pytest
from django.db import DatabaseError, connection, transaction

from apps.activity.context import event_context
from apps.activity.models import ActivityEvent, ActorType, Category
from apps.activity.services import category_for, record_event
from tests.factories import make_user


@pytest.mark.parametrize(
    ("event_type", "category"),
    [
        ("line.locked", Category.LINES),
        ("pick.changed", Category.PICKS),
        ("tiebreaker_game.set", Category.GAMES),
        ("invite.sent", Category.MEMBERSHIP),
        ("auth.login", Category.SECURITY),
    ],
)
def test_category_from_event_type(event_type: str, category: Category) -> None:
    assert category_for(event_type) == category


def test_unknown_event_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown"):
        category_for("mystery.happened")


@pytest.mark.django_db
def test_event_captures_context_and_actor() -> None:
    user = make_user()
    with event_context("web", ip_address="203.0.113.5"):
        event = record_event(event_type="invite.sent", summary="x", actor=user)
    assert event.source == "web"
    assert len(event.request_id) == 32
    assert event.actor_type == ActorType.MEMBER
    assert event.ip_address is None


@pytest.mark.django_db
def test_ip_kept_only_for_security_events() -> None:
    with event_context("web", ip_address="203.0.113.5"):
        event = record_event(event_type="auth.login_failed", summary="x")
    assert event.ip_address == "203.0.113.5"
    assert event.actor_type == ActorType.SYSTEM


@pytest.mark.django_db
def test_event_rolls_back_with_the_change() -> None:
    def change_that_fails() -> None:
        with transaction.atomic():
            record_event(event_type="invite.sent", summary="x")
            raise RuntimeError

    with pytest.raises(RuntimeError):
        change_that_fails()
    assert not ActivityEvent.objects.exists()


@pytest.mark.django_db
@pytest.mark.skipif(
    connection.vendor != "postgresql", reason="trigger is PostgreSQL-only"
)
def test_activity_log_is_append_only() -> None:
    event = record_event(event_type="invite.sent", summary="x")
    with pytest.raises(DatabaseError), transaction.atomic():
        ActivityEvent.objects.filter(pk=event.pk).update(summary="changed")
    with pytest.raises(DatabaseError), transaction.atomic():
        ActivityEvent.objects.filter(pk=event.pk).delete()
