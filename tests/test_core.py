import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User


@pytest.mark.django_db
def test_home_requires_login(client: Client) -> None:
    response = client.get(reverse("core:home"))
    assert response.status_code == 302
    assert reverse("account_login") in response["Location"]


@pytest.mark.django_db
def test_home_greets_signed_in_user(client: Client, user: User) -> None:
    client.force_login(user)
    response = client.get(reverse("core:home"))
    assert response.status_code == 200
    assert b"member@example.com" in response.content


@pytest.mark.django_db
def test_health_reports_ok(client: Client) -> None:
    response = client.get(reverse("core:health"))
    assert response.json() == {"status": "ok"}
