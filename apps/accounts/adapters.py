from allauth.account.adapter import DefaultAccountAdapter
from django.http import HttpRequest


class InviteOnlyAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest) -> bool:
        # Signup opens only through league invites, which arrive in a later milestone.
        return False
