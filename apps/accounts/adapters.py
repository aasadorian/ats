from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from django import forms
from django.http import HttpRequest

from apps.accounts.models import User
from apps.leagues.models import Invite
from apps.leagues.services import accept_invite, find_invite

INVITE_SESSION_KEY = "invite_token"


def session_invite(request: HttpRequest) -> Invite | None:
    token = request.session.get(INVITE_SESSION_KEY)
    if not token:
        return None
    found = find_invite(token)
    return found if found is not None and found.is_usable else None


class InviteOnlyAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return session_invite(request) is not None

    def clean_email(self, email: str) -> str:
        email = super().clean_email(email).lower()
        found = session_invite(self.request)
        if found is not None and found.email != email:
            raise forms.ValidationError(
                "Use the email address your invite was sent to."
            )
        return email

    def save_user(
        self, request: HttpRequest, user: User, form: Any, commit: bool = True
    ) -> User:
        saved: User = super().save_user(request, user, form, commit=commit)
        found = session_invite(request)
        if commit and found is not None:
            accept_invite(found, saved)
            del request.session[INVITE_SESSION_KEY]
        return saved
