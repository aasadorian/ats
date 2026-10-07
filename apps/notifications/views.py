from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

from apps.accounts.models import User
from apps.accounts.utils import request_user
from apps.notifications.email import read_unsubscribe_token, wants
from apps.notifications.models import Kind, NotificationPreference


@login_required
def preferences(request: HttpRequest) -> HttpResponse:
    user = request_user(request)
    if request.method == "POST":
        for kind in Kind:
            set_preference(user, kind, enabled=request.POST.get(kind.value) == "on")
        messages.success(request, "Email preferences saved.")
        return redirect("notifications:preferences")
    return render(
        request,
        "notifications/preferences.html",
        {"options": [(kind, wants(user, kind)) for kind in Kind]},
    )


# The signed token authenticates the request, and mail clients send one-click
# unsubscribes (RFC 8058) as a POST without a CSRF token.
@csrf_exempt
def unsubscribe(request: HttpRequest, token: str) -> HttpResponse:
    found = read_unsubscribe_token(token)
    user = User.objects.filter(pk=found[0]).first() if found else None
    if found is None or user is None:
        return render(
            request, "notifications/unsubscribe.html", {"invalid": True}, status=404
        )
    kind = found[1]
    if request.method == "POST":
        set_preference(user, kind, enabled=False)
        return render(
            request, "notifications/unsubscribe.html", {"kind": kind, "done": True}
        )
    return render(request, "notifications/unsubscribe.html", {"kind": kind})


def set_preference(user: User, kind: Kind, *, enabled: bool) -> None:
    NotificationPreference.objects.update_or_create(
        user=user, kind=kind, defaults={"enabled": enabled}
    )
