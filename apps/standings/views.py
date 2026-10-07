from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.utils import request_user
from apps.leagues.models import League, Membership
from apps.leagues.permissions import commissioner_required, league_member_required
from apps.leagues.services import current_league_season
from apps.nfl.models import Game
from apps.picks.views import league_week_for, weeks_for
from apps.standings.forms import ScoreCorrectionForm
from apps.standings.selectors import season_standings, week_results
from apps.standings.services import (
    correct_score,
    restore_feed_score,
    update_week_statuses,
)


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


@commissioner_required
def scores(
    request: HttpRequest, league: League, membership: Membership
) -> HttpResponse:
    league_week = league_week_for(league, request.GET.get("week", ""))
    if league_week is None:
        return render(request, "picks/no_season.html", {"league": league})
    games = league_week.week.games.select_related("home_team", "away_team").order_by(
        "kickoff_at"
    )
    return render(
        request,
        "standings/scores.html",
        {
            "league": league,
            "membership": membership,
            "selected": league_week,
            "weeks": weeks_for(league),
            "games": games,
        },
    )


@require_POST
@commissioner_required
def correct(
    request: HttpRequest, league: League, membership: Membership, pk: int
) -> HttpResponse:
    game = get_object_or_404(
        Game.objects.select_related("home_team", "away_team", "week"), pk=pk
    )
    form = ScoreCorrectionForm(request.POST)
    if not league.seasons.filter(season=game.week.season).exists():
        raise Http404
    if request.POST.get("restore"):
        restore_feed_score(game, league=league, actor=request_user(request))
        messages.success(request, f"{game} will follow the feed again.")
    elif form.is_valid():
        correct_score(
            game,
            home_score=form.cleaned_data["home_score"],
            away_score=form.cleaned_data["away_score"],
            league=league,
            actor=request_user(request),
            reason=form.cleaned_data["reason"],
        )
        update_week_statuses(timezone.now())
        messages.success(request, f"Score saved for {game}.")
    else:
        messages.error(request, "Enter both scores and a reason.")
    url = reverse("standings:scores", args=[league.slug])
    return redirect(f"{url}?week={game.week.number}")
