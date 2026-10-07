from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.leagues.models import League, Membership
from apps.leagues.permissions import league_member_required
from apps.leagues.services import current_league_season
from apps.picks.views import league_week_for, weeks_for
from apps.standings.selectors import season_standings, week_results


@league_member_required
def season(
    request: HttpRequest, league: League, membership: Membership
) -> HttpResponse:
    league_season = current_league_season(league)
    if league_season is None:
        return render(request, "picks/no_season.html", {"league": league})
    return render(
        request,
        "standings/season.html",
        {
            "league": league,
            "membership": membership,
            "standings": season_standings(league_season),
        },
    )


@league_member_required
def week(request: HttpRequest, league: League, membership: Membership) -> HttpResponse:
    league_week = league_week_for(league, request.GET.get("week", ""))
    if league_week is None:
        return render(request, "picks/no_season.html", {"league": league})
    return render(
        request,
        "standings/week.html",
        {
            "league": league,
            "membership": membership,
            "results": week_results(league_week),
            "weeks": weeks_for(league),
            "tiebreakers_revealed": timezone.now() >= league_week.picks_lock_at,
        },
    )
