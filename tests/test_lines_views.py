from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from apps.leagues.models import Membership
from apps.lines.models import Spread
from apps.lines.services import lock_spreads
from tests.factories import make_league, make_user
from tests.odds import FakeOddsProvider, odds_event


@pytest.fixture
def locked_league(db: None, settings: Any) -> Any:
    settings.COMMISSIONER_MFA_REQUIRED = False
    league = make_league()
    lock_spreads(
        FakeOddsProvider(
            [odds_event("Seattle Seahawks", "New England Patriots", [-3, -3, -3.5])]
        ),
        now=datetime(2026, 9, 8, 11, tzinfo=UTC),
    )
    return league


def test_commissioner_sees_locked_lines(client: Client, locked_league: Any) -> None:
    client.force_login(locked_league.memberships.get().user)
    response = client.get(
        reverse("lines:review", args=[locked_league.slug]), {"week": 1}
    )
    assert response.status_code == 200
    assert b"SEA -3.5" in response.content
    assert b"Off the board" in response.content


def test_members_cannot_review_lines(client: Client, locked_league: Any) -> None:
    member = make_user()
    Membership.objects.create(user=member, league=locked_league)
    client.force_login(member)
    response = client.get(reverse("lines:review", args=[locked_league.slug]))
    assert response.status_code == 404


def test_commissioner_overrides_line(client: Client, locked_league: Any) -> None:
    client.force_login(locked_league.memberships.get().user)
    spread = Spread.objects.get(game__home_team__abbreviation="SEA")
    response = client.post(
        reverse("lines:override", args=[locked_league.slug, spread.pk]),
        {"home_line": "-4.5", "reason": "Injury news"},
    )
    assert response.status_code == 302
    spread.refresh_from_db()
    assert spread.home_line == Decimal("-4.5")


def test_override_from_another_league_is_404(
    client: Client, locked_league: Any
) -> None:
    other = make_league(slug="other")
    client.force_login(other.memberships.get().user)
    spread = Spread.objects.get(game__home_team__abbreviation="SEA")
    response = client.post(
        reverse("lines:override", args=[other.slug, spread.pk]),
        {"home_line": "-9.5", "reason": "x"},
    )
    assert response.status_code == 404
