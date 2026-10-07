import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from django.db import transaction

from apps.activity.services import record_event
from apps.nfl.feeds.types import GameData, ScheduleProvider, TeamData, WeekData
from apps.nfl.models import Game, GameStatus, Season, Team, Week

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    weeks: int = 0
    games_created: int = 0
    games_updated: int = 0
    rescheduled: list[str] = field(default_factory=list)
    postponed: list[str] = field(default_factory=list)
    finals: list[str] = field(default_factory=list)


def sync_schedule(
    provider: ScheduleProvider, *, season_year: int, weeks: Iterable[int] | None = None
) -> SyncResult:
    result = SyncResult()
    known = Week.objects.filter(season__year=season_year)
    week_data = (
        None
        if weeks is not None and known.exists()
        else provider.fetch_weeks(season_year)
    )
    if week_data is None:
        week_numbers = list(weeks or [])
    elif weeks is None:
        week_numbers = [w.number for w in week_data]
    else:
        week_numbers = list(weeks)
    games_by_week = {n: provider.fetch_games(season_year, n) for n in week_numbers}

    with transaction.atomic():
        season, _ = Season.objects.get_or_create(year=season_year)
        if week_data is None:
            week_by_number = {w.number: w for w in season.weeks.all()}
        else:
            week_by_number = {w.number: _upsert_week(season, w) for w in week_data}
        result.weeks = len(week_by_number)
        teams: dict[str, Team] = {}
        for games in games_by_week.values():
            for data in games:
                _upsert_game(data, week_by_number, teams, result)

    logger.info(
        "Synced %s schedule: %s weeks, %s games created, %s updated",
        season_year,
        result.weeks,
        result.games_created,
        result.games_updated,
    )
    return result


def _upsert_week(season: Season, data: WeekData) -> Week:
    week, _ = Week.objects.update_or_create(
        season=season,
        number=data.number,
        defaults={
            "starts_at": data.starts_at,
            "ends_at": data.ends_at,
            "sunday": data.sunday,
        },
    )
    return week


def _team(data: TeamData, cache: dict[str, Team]) -> Team:
    if data.external_id not in cache:
        cache[data.external_id], _ = Team.objects.update_or_create(
            external_id=data.external_id,
            defaults={
                "abbreviation": data.abbreviation,
                "location": data.location,
                "name": data.name,
            },
        )
    return cache[data.external_id]


def _upsert_game(
    data: GameData,
    week_by_number: dict[int, Week],
    teams: dict[str, Team],
    result: SyncResult,
) -> None:
    fields = {
        "home_team": _team(data.home_team, teams),
        "away_team": _team(data.away_team, teams),
        "kickoff_at": data.kickoff_at,
        "kickoff_is_tbd": data.kickoff_is_tbd,
        "status": data.status,
        "neutral_site": data.neutral_site,
        "home_score": data.home_score,
        "away_score": data.away_score,
    }
    game = Game.objects.filter(external_id=data.external_id).first()
    if game is not None and game.score_overridden:
        for name in ("status", "home_score", "away_score"):
            fields.pop(name)
    if game is None:
        Game.objects.create(
            external_id=data.external_id,
            week=week_by_number[data.week_number],
            **fields,
        )
        result.games_created += 1
        return

    original = (game.week_id, game.postponed_from)
    if data.status == GameStatus.POSTPONED and game.postponed_from is None:
        # Picks lock against the original kickoff, so it is kept when a game is
        # postponed and the game stays in its original week.
        game.postponed_from = game.kickoff_at
        result.postponed.append(str(game))
        record_event(
            event_type="game.postponed",
            summary=f"{game} postponed",
            obj=game,
            before={"kickoff_at": game.kickoff_at.isoformat()},
        )
    elif game.postponed_from is None:
        game.week = week_by_number[data.week_number]

    if game.kickoff_at != data.kickoff_at:
        result.rescheduled.append(str(game))
        record_event(
            event_type="game.rescheduled",
            summary=f"{game} moved to {data.kickoff_at:%Y-%m-%d %H:%M} UTC",
            obj=game,
            before={"kickoff_at": game.kickoff_at.isoformat()},
            after={"kickoff_at": data.kickoff_at.isoformat()},
        )

    if (
        data.status == GameStatus.FINAL
        and game.status != GameStatus.FINAL
        and not game.score_overridden
    ):
        result.finals.append(str(game))
        record_event(
            event_type="game.final",
            summary=(
                f"Final: {game.away_team} {data.away_score}, "
                f"{game.home_team} {data.home_score}"
            ),
            obj=game,
            after={"home_score": data.home_score, "away_score": data.away_score},
        )

    changed = [name for name, value in fields.items() if getattr(game, name) != value]
    for name in changed:
        setattr(game, name, fields[name])
    if changed or (game.week_id, game.postponed_from) != original:
        game.save()
        result.games_updated += 1


LIVE_STATUSES = (GameStatus.SCHEDULED, GameStatus.IN_PROGRESS, GameStatus.POSTPONED)


def weeks_with_live_games(season: Season, now: datetime) -> list[int]:
    """Feed week numbers holding games that have kicked off but aren't final.

    A postponed game is looked up by the feed week containing its new kickoff,
    since the feed lists it there even though our league keeps its original week.
    """
    weeks = list(season.weeks.all())
    games = Game.objects.filter(
        week__season=season, kickoff_at__lte=now, status__in=LIVE_STATUSES
    )
    numbers = {
        week.number
        for game in games
        for week in weeks
        if week.starts_at <= game.kickoff_at < week.ends_at
    }
    return sorted(numbers)


def sync_scores(
    provider: ScheduleProvider, *, season_year: int, now: datetime
) -> SyncResult | None:
    season = Season.objects.filter(year=season_year).first()
    if season is None:
        return None
    numbers = weeks_with_live_games(season, now)
    if not numbers:
        return None
    return sync_schedule(provider, season_year=season_year, weeks=numbers)
