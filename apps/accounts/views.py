from typing import Any

from allauth.account.views import SignupView

from apps.accounts.adapters import session_invite


class InviteSignupView(SignupView):  # type: ignore[misc]
    def get_initial(self) -> dict[str, Any]:
        initial: dict[str, Any] = super().get_initial()
        found = session_invite(self.request)
        if found is not None:
            initial["email"] = found.email
        return initial
