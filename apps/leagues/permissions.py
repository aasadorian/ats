from collections.abc import Callable
from functools import wraps
from typing import Any, Concatenate

from allauth.mfa.utils import is_mfa_enabled
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect

from apps.accounts.utils import request_user
from apps.leagues.models import League, Membership
from apps.leagues.services import active_membership

LeagueView = Callable[Concatenate[HttpRequest, League, Membership, ...], HttpResponse]


def league_member_required(view: LeagueView) -> Callable[..., HttpResponse]:
    @login_required
    @wraps(view)
    def wrapper(request: HttpRequest, slug: str, **kwargs: Any) -> HttpResponse:
        league, membership = _resolve(request, slug)
        return view(request, league, membership, **kwargs)

    return wrapper


def commissioner_required(view: LeagueView) -> Callable[..., HttpResponse]:
    @login_required
    @wraps(view)
    def wrapper(request: HttpRequest, slug: str, **kwargs: Any) -> HttpResponse:
        league, membership = _resolve(request, slug)
        if not membership.is_commissioner:
            raise Http404
        if settings.COMMISSIONER_MFA_REQUIRED and not is_mfa_enabled(request.user):
            messages.warning(
                request,
                "Commissioner tools require two-factor authentication. "
                "Set up an authenticator app to continue.",
            )
            return redirect("mfa_activate_totp")
        return view(request, league, membership, **kwargs)

    return wrapper


def _resolve(request: HttpRequest, slug: str) -> tuple[League, Membership]:
    league = get_object_or_404(League, slug=slug)
    membership = active_membership(request_user(request), league)
    if membership is None:
        raise Http404
    return league, membership
