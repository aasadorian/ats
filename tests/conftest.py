import pytest

from apps.accounts.models import User


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user(
        email="member@example.com", password="correct-horse-battery"
    )
