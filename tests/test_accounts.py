import pytest
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User


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
