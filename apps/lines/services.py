import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.activity.models import ActorType
from apps.activity.services import record_event
from apps.leagues.models import (
    HalfPointRounding,
    LeagueSettings,
    LeagueWeek,
    LeagueWeekStatus,
    OffLineCutoff,
    OffLineFallback,
    OffLineHandling,
)
from apps.leagues.schedule import game_lock_at
from apps.lines.feeds.odds_api import SOURCE, GameOdds, OddsFetch, OddsProvider
from apps.lines.models import OddsSnapshot, Spread, SpreadKind, SpreadStatus
from apps.lines.normalize import is_half_point, median_line, normalize_home_line
from apps.nfl.models import Game, GameStatus, Week

logger = logging.getLogger(__name__)

MIN_BOOKS = 3
HALF = Decimal("0.5")
OFF_LINE_REFRESH_INTERVAL = timedelta(hours=2)


class LineError(Exception):
    pass


@dataclass
class LineRunResult:
    weeks_published: list[str] = field(default_factory=list)
    lines_posted: int = 0
    lines_off: int = 0
    lines_voided: int = 0
    low_book_games: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MatchedOdds:
    raw_home_line: Decimal
    book_count: int
    home_is_moneyline_favorite: bool | None


def describe(spread: Spread) -> str:
    game = spread.game
    if spread.status == SpreadStatus.VOID:
        return f"{game} void"
    if spread.home_line is None:
        return f"{game} OFF"
    if spread.home_line == 0:
        return f"{game} PK"
    if spread.home_line < 0:
        return f"{game} {game.home_team} {spread.home_line:.1f}"
    return f"{game} {game.away_team} {-spread.home_line:.1f}"


class OddsCache:
    """One feed request per NFL week per run, shared by every league."""

    def __init__(self, provider: OddsProvider, now: datetime) -> None:
        self._provider = provider
        self._now = now
        self._by_week: dict[int, OddsFetch] = {}

    def for_week(self, week: Week) -> OddsFetch:
        if week.id not in self._by_week:
            fetched = self._provider.fetch(week.starts_at, week.ends_at)
            OddsSnapshot.objects.create(
                source=SOURCE, payload=fetched.payload, fetched_at=self._now
            )
            self._by_week[week.id] = fetched
        return self._by_week[week.id]


def match_odds(game: Game, fetched: OddsFetch) -> MatchedOdds | None:
    home = game.home_team.display_name.lower()
    away = game.away_team.display_name.lower()
    for odds in fetched.games:
        names = (odds.home_team.lower(), odds.away_team.lower())
        if names == (home, away) and odds.home_points:
            return _matched(odds, flip=False)
        if names == (away, home) and odds.home_points:
            # Neutral-site games can list the teams the other way around.
            return _matched(odds, flip=True)
    return None


def _matched(odds: GameOdds, *, flip: bool) -> MatchedOdds:
    raw = median_line(list(odds.home_points))
    favorite = odds.home_is_moneyline_favorite
    if flip:
        raw = -raw
        favorite = None if favorite is None else not favorite
    return MatchedOdds(
        raw_home_line=raw,
        book_count=len(odds.home_points),
        home_is_moneyline_favorite=favorite,
    )


def normalized(matched: MatchedOdds, league_settings: LeagueSettings) -> Decimal:
    return normalize_home_line(
        matched.raw_home_line,
        half_point_lines=league_settings.half_point_lines,
        favorite_gives=(
            league_settings.half_point_rounding == HalfPointRounding.FAVORITE_GIVES
        ),
        home_is_moneyline_favorite=matched.home_is_moneyline_favorite,
    )


def weeks_due_for_lock(now: datetime) -> QuerySet[LeagueWeek]:
    return LeagueWeek.objects.filter(
        status=LeagueWeekStatus.SCHEDULED,
        spreads_lock_at__lte=now,
        picks_lock_at__gt=now,
    ).select_related("league_season__league", "league_season__settings", "week")


def lock_spreads(provider: OddsProvider, now: datetime | None = None) -> LineRunResult:
    now = now or timezone.now()
    result = LineRunResult()
    cache = OddsCache(provider, now)
    for league_week in weeks_due_for_lock(now):
        fetched = cache.for_week(league_week.week)
        with transaction.atomic():
            _lock_week(league_week, fetched, now, result)
    return result


def _lock_week(
    league_week: LeagueWeek, fetched: OddsFetch, now: datetime, result: LineRunResult
) -> None:
    league_season = league_week.league_season
    league_settings = league_season.settings
    locked = set(
        Spread.objects.filter(
            league_season=league_season,
            kind=SpreadKind.LOCKED,
            game__week=league_week.week,
        ).values_list("game_id", flat=True)
    )
    games = league_week.week.games.exclude(status=GameStatus.CANCELLED).select_related(
        "home_team", "away_team"
    )
    for game in games:
        if game.id in locked:
            continue
        matched = match_odds(game, fetched)
        if matched is None:
            spread = Spread.objects.create(
                league_season=league_season,
                game=game,
                status=SpreadStatus.OFF,
                source=SOURCE,
                locked_at=now,
            )
            result.lines_off += 1
            _record(spread, league_week, "line.off", f"{game}: no line available")
            continue

        spread = Spread.objects.create(
            league_season=league_season,
            game=game,
            home_line=normalized(matched, league_settings),
            feed_line=matched.raw_home_line,
            book_count=matched.book_count,
            source=f"{SOURCE}:median",
            locked_at=now,
        )
        result.lines_posted += 1
        if matched.book_count < MIN_BOOKS:
            result.low_book_games.append(str(game))
        _record(
            spread,
            league_week,
            "line.locked",
            f"{describe(spread)} (feed {matched.raw_home_line:+}, "
            f"{matched.book_count} books)",
            after={"home_line": str(spread.home_line)},
        )

    _publish_if_ready(league_week, result)


def _publish_if_ready(league_week: LeagueWeek, result: LineRunResult) -> None:
    if league_week.status != LeagueWeekStatus.SCHEDULED:
        return
    has_off = Spread.objects.filter(
        league_season=league_week.league_season,
        game__week=league_week.week,
        kind=SpreadKind.LOCKED,
        status=SpreadStatus.OFF,
    ).exists()
    handling = league_week.league_season.settings.off_line_handling
    if has_off and handling == OffLineHandling.HOLD_WEEK:
        return
    league_week.status = LeagueWeekStatus.PUBLISHED
    league_week.save(update_fields=["status"])
    result.weeks_published.append(str(league_week))
    record_event(
        event_type="week.published",
        summary=f"{league_week.week} open for picks",
        league=league_week.league_season.league,
        league_week=league_week,
        obj=league_week,
    )


def off_line_cutoff(spread: Spread, league_week: LeagueWeek) -> datetime:
    league_settings = league_week.league_season.settings
    game = spread.game
    if league_settings.off_line_cutoff == OffLineCutoff.GAME_LOCK:
        return game_lock_at(
            kickoff_at=game.kickoff_at,
            postponed_from=game.postponed_from,
            picks_lock_at=league_week.picks_lock_at,
            offset_minutes=league_settings.game_lock_offset_minutes,
        )
    first = (
        league_week.week.games.exclude(status=GameStatus.CANCELLED)
        .order_by("kickoff_at")
        .values_list("postponed_from", "kickoff_at")
        .first()
    )
    if first is None:
        return league_week.picks_lock_at
    return first[0] or first[1]


def refresh_off_lines(
    provider: OddsProvider, now: datetime | None = None
) -> LineRunResult:
    now = now or timezone.now()
    result = LineRunResult()
    cache = OddsCache(provider, now)
    for league_week, spreads in _off_spreads_by_week():
        due = [s for s in spreads if now >= off_line_cutoff(s, league_week)]
        waiting = [s for s in spreads if s not in due]
        with transaction.atomic():
            for spread in due:
                _apply_fallback(spread, league_week, result)
            if waiting and _may_refresh(now):
                fetched = cache.for_week(league_week.week)
                for spread in waiting:
                    _post_if_available(spread, league_week, fetched, now, result)
            _publish_if_ready(league_week, result)
    return result


def _may_refresh(now: datetime) -> bool:
    """Throttle feed requests for off-the-board games to protect the API quota."""
    last = OddsSnapshot.objects.order_by("-fetched_at").values_list(
        "fetched_at", flat=True
    )
    latest = last.first()
    return latest is None or now - latest >= OFF_LINE_REFRESH_INTERVAL


def _off_spreads_by_week() -> Iterable[tuple[LeagueWeek, list[Spread]]]:
    spreads = Spread.objects.filter(
        kind=SpreadKind.LOCKED, status=SpreadStatus.OFF
    ).select_related("game__home_team", "game__away_team", "league_season")
    grouped: dict[tuple[int, int], list[Spread]] = {}
    for spread in spreads:
        key = (spread.league_season_id, spread.game.week_id)
        grouped.setdefault(key, []).append(spread)
    for (league_season_id, week_id), items in grouped.items():
        league_week = LeagueWeek.objects.select_related(
            "league_season__league", "league_season__settings", "week"
        ).get(league_season_id=league_season_id, week_id=week_id)
        yield league_week, items


def _apply_fallback(
    spread: Spread, league_week: LeagueWeek, result: LineRunResult
) -> None:
    fallback = league_week.league_season.settings.off_line_fallback
    if fallback == OffLineFallback.VOID:
        spread.status = SpreadStatus.VOID
        spread.save(update_fields=["status"])
        result.lines_voided += 1
        _record(spread, league_week, "line.voided", f"{spread.game}: void this week")
        return
    spread.home_line = -HALF if fallback == OffLineFallback.FAVORITE_MINUS_HALF else 0
    spread.status = SpreadStatus.POSTED
    spread.source = f"fallback:{fallback}"
    spread.save(update_fields=["home_line", "status", "source"])
    result.lines_posted += 1
    _record(
        spread,
        league_week,
        "line.posted_late",
        f"{describe(spread)} (no line by cutoff; {fallback})",
        after={"home_line": str(spread.home_line)},
    )


def _post_if_available(
    spread: Spread,
    league_week: LeagueWeek,
    fetched: OddsFetch,
    now: datetime,
    result: LineRunResult,
) -> None:
    matched = match_odds(spread.game, fetched)
    if matched is None:
        return
    spread.home_line = normalized(matched, league_week.league_season.settings)
    spread.feed_line = matched.raw_home_line
    spread.book_count = matched.book_count
    spread.status = SpreadStatus.POSTED
    spread.source = f"{SOURCE}:median"
    spread.locked_at = now
    spread.save()
    result.lines_posted += 1
    _record(
        spread,
        league_week,
        "line.posted_late",
        f"{describe(spread)} (feed {matched.raw_home_line:+}, "
        f"{matched.book_count} books)",
        after={"home_line": str(spread.home_line)},
    )


@transaction.atomic
def override_line(
    spread: Spread, home_line: Decimal, *, actor: User, reason: str
) -> None:
    league_settings = spread.league_season.settings
    if league_settings.half_point_lines and not is_half_point(home_line):
        raise LineError("This league uses half-point lines, like -3.5 or +7.5.")
    before = {"home_line": _str(spread.home_line), "status": spread.status}
    spread.home_line = home_line
    spread.status = SpreadStatus.POSTED
    spread.overridden = True
    spread.source = "manual"
    spread.save(update_fields=["home_line", "status", "overridden", "source"])
    league_week = LeagueWeek.objects.select_related(
        "league_season__league", "league_season__settings", "week"
    ).get(league_season=spread.league_season, week=spread.game.week)
    record_event(
        event_type="line.overridden",
        summary=f"{actor} set {describe(spread)}: {reason}",
        actor=actor,
        actor_type=ActorType.COMMISSIONER,
        league=spread.league_season.league,
        league_week=league_week,
        obj=spread,
        before=before,
        after={"home_line": str(home_line), "status": spread.status, "reason": reason},
    )
    _publish_if_ready(league_week, LineRunResult())


def _record(
    spread: Spread,
    league_week: LeagueWeek,
    event_type: str,
    summary: str,
    after: dict[str, object] | None = None,
) -> None:
    record_event(
        event_type=event_type,
        summary=summary,
        league=league_week.league_season.league,
        league_week=league_week,
        obj=spread,
        after=after,
    )


def _str(value: Decimal | None) -> str | None:
    return None if value is None else str(value)
