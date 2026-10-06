from typing import Any

import pytest
from allauth.account.models import EmailAddress
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.leagues import services
from apps.leagues.models import Membership, Role
from tests.factories import make_league, make_user


@pytest.fixture
def no_mfa(settings: Any) -> None:
    settings.COMMISSIONER_MFA_REQUIRED = False


@pytest.mark.django_db
def test_league_home_hidden_from_non_members(client: Client) -> None:
    league = make_league()
    client.force_login(make_user())
    response = client.get(reverse("leagues:home", args=[league.slug]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_league_home_visible_to_members(client: Client) -> None:
    league = make_league()
    member = make_user()
    Membership.objects.create(user=member, league=league)
    client.force_login(member)
    response = client.get(reverse("leagues:home", args=[league.slug]))
    assert response.status_code == 200


@pytest.mark.django_db
def test_members_page_hidden_from_regular_members(client: Client, no_mfa: None) -> None:
    league = make_league()
    member = make_user()
    Membership.objects.create(user=member, league=league)
    client.force_login(member)
    response = client.get(reverse("leagues:members", args=[league.slug]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_other_leagues_commissioner_gets_404(client: Client, no_mfa: None) -> None:
    league = make_league(slug="ours")
    other = make_league(slug="theirs")
    client.force_login(other.memberships.get().user)
    response = client.get(reverse("leagues:members", args=[league.slug]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_commissioner_without_mfa_is_sent_to_setup(client: Client) -> None:
    league = make_league()
    client.force_login(league.memberships.get().user)
    response = client.get(reverse("leagues:members", args=[league.slug]))
    assert response.status_code == 302
    assert response["Location"] == reverse("mfa_activate_totp")


@pytest.mark.django_db
def test_commissioner_can_invite(client: Client, no_mfa: None) -> None:
    league = make_league()
    client.force_login(league.memberships.get().user)
    response = client.post(
        reverse("leagues:members", args=[league.slug]),
        {"email": "friend@example.com", "role": Role.MEMBER},
    )
    assert response.status_code == 302
    assert league.invites.pending().filter(email="friend@example.com").exists()


@pytest.mark.django_db
def test_invalid_invite_token(client: Client) -> None:
    response = client.get(reverse("leagues:invite", args=["not-a-token"]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_new_person_signs_up_through_invite(client: Client) -> None:
    league = make_league()
    commissioner = league.memberships.get().user
    _, token = services.invite_member(
        league, email="friend@example.com", role=Role.MEMBER, invited_by=commissioner
    )

    client.get(reverse("leagues:invite", args=[token]))
    signup = client.get(reverse("account_signup"))
    assert b"friend@example.com" in signup.content

    response = client.post(
        reverse("account_signup"),
        {
            "email": "friend@example.com",
            "display_name": "Friend",
            "password1": "a-long-unique-passphrase",
            "password2": "a-long-unique-passphrase",
        },
    )
    assert response.status_code == 302
    user = User.objects.get(email="friend@example.com")
    assert user.display_name == "Friend"
    assert Membership.objects.filter(user=user, league=league, is_active=True).exists()
    assert EmailAddress.objects.get(user=user).verified


@pytest.mark.django_db
def test_signup_rejects_a_different_email(client: Client) -> None:
    league = make_league()
    commissioner = league.memberships.get().user
    _, token = services.invite_member(
        league, email="friend@example.com", role=Role.MEMBER, invited_by=commissioner
    )
    client.get(reverse("leagues:invite", args=[token]))
    response = client.post(
        reverse("account_signup"),
        {
            "email": "someone-else@example.com",
            "display_name": "Other",
            "password1": "a-long-unique-passphrase",
            "password2": "a-long-unique-passphrase",
        },
    )
    assert response.status_code == 200
    assert not User.objects.filter(email="someone-else@example.com").exists()


@pytest.mark.django_db
def test_existing_user_accepts_invite(client: Client) -> None:
    league = make_league()
    commissioner = league.memberships.get().user
    existing = make_user(email="friend@example.com")
    _, token = services.invite_member(
        league, email="friend@example.com", role=Role.MEMBER, invited_by=commissioner
    )
    client.force_login(existing)
    response = client.post(reverse("leagues:invite", args=[token]))
    assert response.status_code == 302
    assert Membership.objects.filter(user=existing, league=league).exists()
