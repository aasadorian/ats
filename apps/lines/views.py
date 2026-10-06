from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.utils import request_user
from apps.leagues.models import League, LeagueWeek, Membership
from apps.leagues.permissions import commissioner_required
from apps.leagues.services import current_league_season
from apps.lines.forms import OverrideForm
from apps.lines.models import Spread, SpreadKind
from apps.lines.services import MIN_BOOKS, LineError, override_line


@commissioner_required
def review(
    request: HttpRequest, league: League, membership: Membership
) -> HttpResponse:
    league_season = current_league_season(league)
    weeks = (
        list(league_season.weeks.select_related("week").order_by("week__number"))
        if league_season is not None
        else []
    )
    if league_season is None or not weeks:
        return render(request, "lines/review.html", {"league": league, "weeks": []})

    selected = _selected_week(request.GET.get("week", ""), weeks)
    games = selected.week.games.select_related("home_team", "away_team").order_by(
        "kickoff_at"
    )
    spreads = {
        spread.game_id: spread
        for spread in Spread.objects.filter(
            league_season=league_season,
            kind=SpreadKind.LOCKED,
            game__week=selected.week,
        )
    }
    return render(
        request,
        "lines/review.html",
        {
            "league": league,
            "weeks": weeks,
            "selected": selected,
            "rows": [{"game": g, "spread": spreads.get(g.id)} for g in games],
            "min_books": MIN_BOOKS,
        },
    )


@require_POST
@commissioner_required
def override(
    request: HttpRequest, league: League, membership: Membership, pk: int
) -> HttpResponse:
    spread = get_object_or_404(
        Spread.objects.select_related("game__week", "league_season__settings"),
        pk=pk,
        league_season__league=league,
    )
    form = OverrideForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a line and a reason.")
    else:
        try:
            override_line(
                spread,
                form.cleaned_data["home_line"],
                actor=request_user(request),
                reason=form.cleaned_data["reason"],
            )
        except LineError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Line updated.")
    url = reverse("lines:review", args=[league.slug])
    return redirect(f"{url}?week={spread.game.week.number}")


def _selected_week(requested: str, weeks: list[LeagueWeek]) -> LeagueWeek:
    if requested.isdigit():
        for league_week in weeks:
            if league_week.week.number == int(requested):
                return league_week
    now = timezone.now()
    upcoming = [league_week for league_week in weeks if league_week.picks_lock_at > now]
    return upcoming[0] if upcoming else weeks[-1]
