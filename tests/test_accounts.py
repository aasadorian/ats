import hashlib

import httpx
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.validators import PwnedPasswordValidator
from apps.activity.models import ActivityEvent


@pytest.mark.django_db
def test_email_is_stored_lowercase() -> None:
    user = User.objects.create_user(email="Member@Example.COM", password="x" * 12)
    assert user.email == "member@example.com"


@pytest.mark.django_db
def test_email_is_unique_case_insensitively() -> None:
    User.objects.create_user(email="member@example.com", password="x" * 12)
    with pytest.raises(IntegrityError):
        User.objects.create_user(email="MEMBER@example.com", password="x" * 12)


@pytest.mark.django_db
def test_superuser_has_admin_flags() -> None:
    admin = User.objects.create_superuser(email="admin@example.com", password="x" * 12)
    assert admin.is_staff
    assert admin.is_superuser


@pytest.mark.django_db
def test_public_signup_is_closed(client: Client) -> None:
    response = client.get(reverse("account_signup"))
    assert b"Sign Up Closed" in response.content


@pytest.mark.django_db
def test_failed_login_is_logged_with_masked_email(client: Client) -> None:
    client.post(
        reverse("account_login"),
        {"login": "member@example.com", "password": "wrong-password"},
    )
    event = ActivityEvent.objects.get(event_type="auth.login_failed")
    assert "member@example.com" not in event.summary
    assert "me***@example.com" in event.summary


@pytest.mark.django_db
def test_successful_login_is_logged(client: Client, user: User) -> None:
    client.post(
        reverse("account_login"),
        {"login": "member@example.com", "password": "correct-horse-battery"},
    )
    assert ActivityEvent.objects.filter(event_type="auth.login", actor=user).exists()


def test_pwned_password_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = PwnedPasswordValidator()
    suffix = hashlib.sha1(b"password1", usedforsecurity=False).hexdigest().upper()[5:]
    monkeypatch.setattr(validator, "fetch_range", lambda prefix: f"{suffix}:42\nABC:1")
    with pytest.raises(ValidationError):
        validator.validate("password1")


def test_pwned_check_allows_password_when_service_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = PwnedPasswordValidator()

    def unavailable(prefix: str) -> str:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(validator, "fetch_range", unavailable)
    validator.validate("anything-at-all")
