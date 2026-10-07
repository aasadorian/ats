from collections.abc import Callable

from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.utils import request_user
from apps.activity.models import ActorType
from apps.activity.services import record_event
from apps.leagues.models import League, LeagueWeek, Membership
from apps.leagues.permissions import commissioner_required, league_member_required
from apps.leagues.services import current_league_season
from apps.nfl.models import Game, Team
from apps.picks import services
from apps.picks.forms import CommissionerPickForm
from apps.picks.notifications import notify_pick_entered
from apps.picks.selectors import default_week, pick_sheet, picks_grid


@league_member_required
def sheet(request: HttpRequest, league: League, membership: Membership) -> HttpResponse:
    league_week = league_week_for(league, request.GET.get("week", ""))
    if league_week is None:
        return render(request, "picks/no_season.html", {"league": league})
    return render(
        request, "picks/sheet.html", _sheet_context(league, membership, league_week)
    )


@league_member_required
def grid(request: HttpRequest, league: League, membership: Membership) -> HttpResponse:
    league_week = league_week_for(league, request.GET.get("week", ""))
    if league_week is None:
        return render(request, "picks/no_season.html", {"league": league})
    return render(
        request,
        "picks/grid.html",
        {
            "league": league,
            "membership": membership,
            "grid": picks_grid(league_week, membership, timezone.now()),
            "weeks": weeks_for(league),
        },
    )


@require_POST
@league_member_required
def make_pick(
    request: HttpRequest, league: League, membership: Membership
) -> HttpResponse:
    league_week, game = _target(request, league)
    team = get_object_or_404(
        Team, pk=request.POST.get("team"), id__in=(game.home_team_id, game.away_team_id)
    )
    return _act(
        request,
        league,
        membership,
        league_week,
        lambda: services.save_pick(membership, league_week, game, team),
    )


@require_POST
@league_member_required
def clear_pick(
    request: HttpRequest, league: League, membership: Membership
) -> HttpResponse:
    league_week, game = _target(request, league)
    return _act(
        request,
        league,
        membership,
        league_week,
        lambda: services.clear_pick(membership, league_week, game),
    )


@require_POST
@league_member_required
def best_bet(
    request: HttpRequest, league: League, membership: Membership
) -> HttpResponse:
    league_week, game = _target(request, league)
    on = request.POST.get("on") == "1"
    return _act(
        request,
        league,
        membership,
        league_week,
        lambda: services.set_best_bet(membership, league_week, game, on=on),
    )


@require_POST
@league_member_required
def tiebreaker(
    request: HttpRequest, league: League, membership: Membership
) -> HttpResponse:
    league_week = league_week_for(league, request.POST.get("week", ""))
    if league_week is None:
        raise Http404
    raw = request.POST.get("guess", "").strip()
    if raw and not raw.isdigit():
        return _respond(
            request, league, membership, league_week, "Enter a whole number."
        )
    guess = int(raw) if raw else None
    return _act(
        request,
        league,
        membership,
        league_week,
        lambda: services.set_tiebreaker(membership, league_week, guess),
    )


def _act(
    request: HttpRequest,
    league: League,
    membership: Membership,
    league_week: LeagueWeek,
    action: Callable[[], object],
) -> HttpResponse:
    error = None
    try:
        action()
    except services.PickError as exc:
        error = str(exc)
    return _respond(request, league, membership, league_week, error)


def _respond(
    request: HttpRequest,
    league: League,
    membership: Membership,
    league_week: LeagueWeek,
    error: str | None,
) -> HttpResponse:
    if request.headers.get("HX-Request") == "true":
        context = _sheet_context(league, membership, league_week)
        context["error"] = error
        return render(request, "picks/_sheet.html", context)
    if error:
        messages.error(request, error)
    url = reverse("picks:sheet", args=[league.slug])
    return redirect(f"{url}?week={league_week.week.number}")


def _sheet_context(
    league: League, membership: Membership, league_week: LeagueWeek
) -> dict[str, object]:
    return {
        "league": league,
        "membership": membership,
        "sheet": pick_sheet(membership, league_week, timezone.now()),
        "weeks": weeks_for(league),
    }


def weeks_for(league: League) -> list[LeagueWeek]:
    league_season = current_league_season(league)
    if league_season is None:
        return []
    return list(league_season.weeks.select_related("week").order_by("week__number"))


def league_week_for(league: League, requested: str) -> LeagueWeek | None:
    league_season = current_league_season(league)
    if league_season is None:
        return None
    if requested.isdigit():
        found = (
            league_season.weeks.select_related("week", "league_season__settings")
            .filter(week__number=int(requested))
            .first()
        )
        if found is not None:
            return found
    return default_week(league_season, timezone.now())


def _target(request: HttpRequest, league: League) -> tuple[LeagueWeek, Game]:
    league_week = league_week_for(league, request.POST.get("week", ""))
    if league_week is None:
        raise Http404
    game = get_object_or_404(
        Game.objects.select_related("home_team", "away_team", "week"),
        pk=request.POST.get("game"),
        week=league_week.week,
    )
    return league_week, game


@commissioner_required
def member_picks(
    request: HttpRequest, league: League, membership: Membership, pk: int
) -> HttpResponse:
    target = get_object_or_404(
        Membership.objects.select_related("user"), pk=pk, league=league, is_active=True
    )
    league_week = league_week_for(
        league, request.POST.get("week", "") or request.GET.get("week", "")
    )
    if league_week is None:
        return render(request, "picks/no_season.html", {"league": league})

    if request.method == "POST":
        form = CommissionerPickForm(request.POST)
        game = get_object_or_404(
            Game.objects.select_related("home_team", "away_team", "week"),
            pk=request.POST.get("game"),
            week=league_week.week,
        )
        if form.is_valid():
            _commissioner_pick(request, target, league_week, game, form)
        else:
            messages.error(request, "A reason is required.")
        url = reverse("picks:member_picks", args=[league.slug, target.pk])
        return redirect(f"{url}?week={league_week.week.number}")

    return render(
        request,
        "picks/member_picks.html",
        {
            "league": league,
            "membership": membership,
            "target": target,
            "sheet": pick_sheet(target, league_week, timezone.now()),
            "weeks": weeks_for(league),
        },
    )


def _commissioner_pick(
    request: HttpRequest,
    target: Membership,
    league_week: LeagueWeek,
    game: Game,
    form: CommissionerPickForm,
) -> None:
    actor = request_user(request)
    team_id = form.cleaned_data["team"]
    reason = form.cleaned_data["reason"]
    try:
        with transaction.atomic():
            if team_id is None:
                services.clear_pick(target, league_week, game, actor=actor)
            else:
                team = get_object_or_404(
                    Team, pk=team_id, id__in=(game.home_team_id, game.away_team_id)
                )
                services.save_pick(target, league_week, game, team, actor=actor)
                services.set_best_bet(
                    target,
                    league_week,
                    game,
                    on=form.cleaned_data["best_bet"],
                    actor=actor,
                )
            record_event(
                event_type="pick.entered_for_member",
                summary=f"{actor} updated a pick for {target.user} in {game}: {reason}",
                actor=actor,
                actor_type=ActorType.COMMISSIONER,
                league=league_week.league_season.league,
                league_week=league_week,
                subject_user=target.user,
                after={"game": str(game), "reason": reason},
            )
            transaction.on_commit(
                lambda: notify_pick_entered(target, game, actor=actor, reason=reason)
            )
    except services.PickError as exc:
        messages.error(request, str(exc))
        return
    messages.success(request, f"Saved the pick for {target.user} in {game}.")
