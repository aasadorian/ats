import pytest
from allauth.account.models import EmailAddress

from apps.accounts.models import User
from tests.world import World, build


@pytest.fixture
def user(db: None) -> User:
    member = User.objects.create_user(
        email="member@example.com", password="correct-horse-battery"
    )
    EmailAddress.objects.create(
        user=member, email=member.email, verified=True, primary=True
    )
    return member


@pytest.fixture
def world(db: None) -> World:
    return build()
