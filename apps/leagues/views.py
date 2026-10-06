from collections.abc import Callable

from allauth.account.adapter import get_adapter
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.adapters import INVITE_SESSION_KEY
from apps.accounts.models import User
from apps.accounts.utils import request_user
from apps.leagues import services
from apps.leagues.forms import InviteForm, RoleForm
from apps.leagues.models import Invite, League, Membership, Role
from apps.leagues.permissions import commissioner_required, league_member_required


@league_member_required
def league_home(
    request: HttpRequest, league: League, membership: Membership
) -> HttpResponse:
    members = league.memberships.filter(is_active=True).select_related("user")
    return render(
        request,
        "leagues/home.html",
        {"league": league, "membership": membership, "members": members},
    )


@commissioner_required
def members(
    request: HttpRequest, league: League, membership: Membership
) -> HttpResponse:
    form = InviteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.invite_member(
                league,
                email=form.cleaned_data["email"],
                role=Role(form.cleaned_data["role"]),
                invited_by=request_user(request),
            )
        except services.LeagueError as exc:
            form.add_error("email", str(exc))
        else:
            messages.success(request, f"Invite sent to {form.cleaned_data['email']}.")
            return redirect("leagues:members", slug=league.slug)

    return render(
        request,
        "leagues/members.html",
        {
            "league": league,
            "membership": membership,
            "form": form,
            "memberships": league.memberships.select_related("user").order_by(
                "-is_active", "user__display_name", "user__email"
            ),
            "invites": league.invites.pending(),
            "roles": Role.choices,
        },
    )


@require_POST
@commissioner_required
def invite_resend(
    request: HttpRequest, league: League, membership: Membership, pk: int
) -> HttpResponse:
    invite = get_object_or_404(Invite, pk=pk, league=league)
    _run(request, lambda: services.resend_invite(invite, actor=request_user(request)))
    return redirect("leagues:members", slug=league.slug)


@require_POST
@commissioner_required
def invite_revoke(
    request: HttpRequest, league: League, membership: Membership, pk: int
) -> HttpResponse:
    invite = get_object_or_404(Invite, pk=pk, league=league)
    _run(request, lambda: services.revoke_invite(invite, actor=request_user(request)))
    return redirect("leagues:members", slug=league.slug)


@require_POST
@commissioner_required
def membership_role(
    request: HttpRequest, league: League, membership: Membership, pk: int
) -> HttpResponse:
    target = get_object_or_404(Membership, pk=pk, league=league)
    form = RoleForm(request.POST)
    if form.is_valid():
        role = Role(form.cleaned_data["role"])
        _run(
            request,
            lambda: services.change_role(target, role, actor=request_user(request)),
        )
    return redirect("leagues:members", slug=league.slug)


@require_POST
@commissioner_required
def membership_deactivate(
    request: HttpRequest, league: League, membership: Membership, pk: int
) -> HttpResponse:
    target = get_object_or_404(Membership, pk=pk, league=league)
    _run(
        request,
        lambda: services.deactivate_membership(target, actor=request_user(request)),
    )
    return redirect("leagues:members", slug=league.slug)


@require_POST
@commissioner_required
def membership_reactivate(
    request: HttpRequest, league: League, membership: Membership, pk: int
) -> HttpResponse:
    target = get_object_or_404(Membership, pk=pk, league=league)
    _run(
        request,
        lambda: services.reactivate_membership(target, actor=request_user(request)),
    )
    return redirect("leagues:members", slug=league.slug)


def invite(request: HttpRequest, token: str) -> HttpResponse:
    found = services.find_invite(token)
    if found is None or not found.is_usable:
        return render(request, "invites/invalid.html", status=404)

    user = request.user
    if isinstance(user, User):
        if request.method == "POST":
            try:
                services.accept_invite(found, user)
            except services.InviteError as exc:
                messages.error(request, str(exc))
                return redirect("leagues:invite", token=token)
            return redirect("leagues:home", slug=found.league.slug)
        return render(
            request,
            "invites/invite.html",
            {"invite": found, "email_matches": user.email == found.email},
        )

    request.session[INVITE_SESSION_KEY] = token
    get_adapter(request).stash_verified_email(request, found.email)
    return render(
        request,
        "invites/invite.html",
        {
            "invite": found,
            "has_account": User.objects.filter(email=found.email).exists(),
            "next": request.path,
        },
    )


def _run(request: HttpRequest, action: Callable[[], object]) -> None:
    try:
        action()
    except services.LeagueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Saved.")
