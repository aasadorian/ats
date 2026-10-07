from datetime import datetime

from django.db import transaction
from django.db.models import Min

from apps.accounts.models import User
from apps.activity.models import ActorType
from apps.activity.services import record_event
from apps.leagues.models import League, LeagueWeek, LeagueWeekStatus
from apps.nfl.models import Game, GameStatus
from apps.standings.selectors import week_results

DONE_STATUSES = (GameStatus.FINAL, GameStatus.CANCELLED)


def update_week_statuses(now: datetime) -> list[str]:
    """Move weeks to in progress at first kickoff and to final once every game is.

    A postponed game is neither final nor cancelled, so it holds its week open.
    """
    changes = []
    weeks = LeagueWeek.objects.filter(
        status__in=(LeagueWeekStatus.PUBLISHED, LeagueWeekStatus.IN_PROGRESS)
    ).select_related(
        "week", "league_season__league", "league_season__settings", "tiebreaker_game"
    )
    for league_week in weeks:
        games = league_week.week.games.all()
        first = games.exclude(status=GameStatus.CANCELLED).aggregate(
            first=Min("kickoff_at")
        )["first"]
        if (
            league_week.status == LeagueWeekStatus.PUBLISHED
            and first is not None
            and first <= now
        ):
            _set_status(league_week, LeagueWeekStatus.IN_PROGRESS)
            changes.append(f"{league_week}: in progress")
        if (
            league_week.status == LeagueWeekStatus.IN_PROGRESS
            and not games.exclude(status__in=DONE_STATUSES).exists()
        ):
            _finalize(league_week)
            changes.append(f"{league_week}: final")
    return changes


def _set_status(league_week: LeagueWeek, status: LeagueWeekStatus) -> None:
    league_week.status = status
    league_week.save(update_fields=["status"])


@transaction.atomic
def _finalize(league_week: LeagueWeek) -> None:
    _set_status(league_week, LeagueWeekStatus.FINAL)
    league = league_week.league_season.league
    record_event(
        event_type="week.final",
        summary=f"{league_week.week} is final",
        league=league,
        league_week=league_week,
        obj=league_week,
    )
    results = week_results(league_week)
    names = ", ".join(str(m.user) for m in results.winners) or "no winner"
    split = " (split)" if results.is_split else ""
    top = results.members[0].points if results.members else 0
    record_event(
        event_type="standings.weekly_winners",
        summary=f"{league_week.week} winner: {names}{split} with {top} points",
        league=league,
        league_week=league_week,
        obj=league_week,
        after={
            "winners": [m.user_id for m in results.winners],
            "points": str(top),
            "tiebreaker_actual": results.tiebreaker_actual,
        },
    )


@transaction.atomic
def correct_score(
    game: Game,
    *,
    home_score: int,
    away_score: int,
    league: League,
    actor: User,
    reason: str,
) -> None:
    before = {
        "home_score": game.home_score,
        "away_score": game.away_score,
        "status": game.status,
    }
    game.home_score = home_score
    game.away_score = away_score
    game.status = GameStatus.FINAL
    game.score_overridden = True
    game.save(update_fields=["home_score", "away_score", "status", "score_overridden"])
    record_event(
        event_type="game.score_corrected",
        summary=(
            f"{actor} set {game.away_team} {away_score}, "
            f"{game.home_team} {home_score}: {reason}"
        ),
        actor=actor,
        actor_type=ActorType.COMMISSIONER,
        league=league,
        obj=game,
        before=before,
        after={"home_score": home_score, "away_score": away_score, "reason": reason},
    )


@transaction.atomic
def restore_feed_score(game: Game, *, league: League, actor: User) -> None:
    if not game.score_overridden:
        return
    game.score_overridden = False
    game.save(update_fields=["score_overridden"])
    record_event(
        event_type="game.score_corrected",
        summary=f"{actor} returned {game} to the feed score",
        actor=actor,
        actor_type=ActorType.COMMISSIONER,
        league=league,
        obj=game,
        after={"score_overridden": False},
    )
