import logging
from collections.abc import Iterable
from dataclasses import dataclass, field

from django.db import transaction

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


def sync_schedule(
    provider: ScheduleProvider, *, season_year: int, weeks: Iterable[int] | None = None
) -> SyncResult:
    result = SyncResult()
    week_data = provider.fetch_weeks(season_year)
    week_numbers = list(weeks) if weeks is not None else [w.number for w in week_data]
    games_by_week = {n: provider.fetch_games(season_year, n) for n in week_numbers}

    with transaction.atomic():
        season, _ = Season.objects.get_or_create(year=season_year)
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
    }
    game = Game.objects.filter(external_id=data.external_id).first()
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
    elif game.postponed_from is None:
        game.week = week_by_number[data.week_number]

    if game.kickoff_at != data.kickoff_at:
        result.rescheduled.append(str(game))

    changed = [name for name, value in fields.items() if getattr(game, name) != value]
    for name in changed:
        setattr(game, name, fields[name])
    if changed or (game.week_id, game.postponed_from) != original:
        game.save()
        result.games_updated += 1
