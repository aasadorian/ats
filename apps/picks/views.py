from collections.abc import Callable

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.leagues.models import League, LeagueWeek, Membership
from apps.leagues.permissions import league_member_required
from apps.leagues.services import current_league_season
from apps.nfl.models import Game, Team
from apps.picks import services
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
