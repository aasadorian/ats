from django.core.exceptions import PermissionDenied
from django.http import HttpRequest

from apps.accounts.models import User


def request_user(request: HttpRequest) -> User:
    if not isinstance(request.user, User):
        raise PermissionDenied
    return request.user
