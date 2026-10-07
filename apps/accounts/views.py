from typing import Any

from allauth.account.views import SignupView
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from apps.accounts import services
from apps.accounts.adapters import session_invite
from apps.accounts.forms import DeleteAccountForm, ProfileForm
from apps.accounts.utils import request_user


class InviteSignupView(SignupView):  # type: ignore[misc]
    def get_initial(self) -> dict[str, Any]:
        initial: dict[str, Any] = super().get_initial()
        found = session_invite(self.request)
        if found is not None:
            initial["email"] = found.email
        return initial


@login_required
def profile(request: HttpRequest) -> HttpResponse:
    user = request_user(request)
    form = ProfileForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile saved.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form})


@login_required
def delete_account(request: HttpRequest) -> HttpResponse:
    user = request_user(request)
    form = DeleteAccountForm(user, request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        services.delete_account(user)
        logout(request)
        messages.success(request, "Your account has been deleted.")
        return redirect("account_login")
    return render(request, "accounts/delete.html", {"form": form})
