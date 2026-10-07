from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from apps.leagues.models import LeagueSeason, LeagueWeek, Membership
from apps.lines.models import Spread, SpreadStatus, team_line
from apps.nfl.models import Game, GameStatus
from apps.picks.models import Pick, WeeklyEntry
from apps.picks.services import OPEN_STATUSES, WeekContext


@dataclass(frozen=True)
class SheetRow:
    game: Game
    state: str
    lock_at: datetime
    home_line: Decimal | None
    home_text: str
    away_text: str
    pick: Pick | None

    @property
    def is_open(self) -> bool:
        return self.state == "open"


@dataclass
class PickSheet:
    league_week: LeagueWeek
    rows: list[SheetRow]
    entry: WeeklyEntry | None
    best_bet_limit: int
    tiebreaker_locked: bool
    week_open: bool

    @property
    def picked(self) -> int:
        return sum(1 for row in self.rows if row.pick is not None)

    @property
    def pickable(self) -> int:
        return sum(1 for row in self.rows if row.state in ("open", "locked"))

    @property
    def best_bets(self) -> int:
        return sum(1 for row in self.rows if row.pick and row.pick.is_best_bet)

    @property
    def unpicked_open(self) -> int:
        return sum(1 for row in self.rows if row.is_open and row.pick is None)


@dataclass(frozen=True)
class GridCell:
    revealed: bool
    has_pick: bool
    pick: Pick | None


@dataclass
class GridRow:
    membership: Membership
    cells: list[GridCell]
    tiebreaker_guess: int | None
    tiebreaker_revealed: bool


@dataclass(frozen=True)
class GridColumn:
    game: Game
    home_text: str


@dataclass
class PicksGrid:
    league_week: LeagueWeek
    columns: list[GridColumn]
    rows: list[GridRow] = field(default_factory=list)


def default_week(league_season: LeagueSeason, now: datetime) -> LeagueWeek | None:
    weeks = list(league_season.weeks.select_related("week").order_by("week__number"))
    for league_week in weeks:
        if league_week.week.ends_at > now:
            return league_week
    return weeks[-1] if weeks else None


def pick_sheet(
    membership: Membership, league_week: LeagueWeek, now: datetime
) -> PickSheet:
    context = WeekContext.load(league_week)
    games = _games(league_week)
    picks = {
        pick.game_id: pick
        for pick in Pick.objects.filter(
            membership=membership, week=league_week.week
        ).select_related("team")
    }
    week_open = league_week.status in OPEN_STATUSES
    rows = []
    for game in games:
        spread = context.spreads.get(game.id)
        home_line = spread.home_line if spread else None
        rows.append(
            SheetRow(
                game=game,
                state=_state(game, spread, context, now, week_open),
                lock_at=context.lock_at(game),
                home_line=home_line,
                home_text=team_line(home_line, is_home=True),
                away_text=team_line(home_line, is_home=False),
                pick=picks.get(game.id),
            )
        )
    return PickSheet(
        league_week=league_week,
        rows=rows,
        entry=WeeklyEntry.objects.filter(
            membership=membership, league_week=league_week
        ).first(),
        best_bet_limit=context.settings.best_bets_per_week,
        tiebreaker_locked=now >= league_week.picks_lock_at,
        week_open=week_open,
    )


def picks_grid(league_week: LeagueWeek, viewer: Membership, now: datetime) -> PicksGrid:
    context = WeekContext.load(league_week)
    games = _games(league_week)
    memberships = list(
        league_week.league_season.league.memberships.filter(is_active=True)
        .select_related("user")
        .order_by("user__display_name")
    )
    picks: dict[tuple[int, int], Pick] = {
        (pick.membership_id, pick.game_id): pick
        for pick in Pick.objects.filter(
            week=league_week.week, membership__in=memberships
        ).select_related("team")
    }
    entries = {
        entry.membership_id: entry.tiebreaker_guess
        for entry in WeeklyEntry.objects.filter(league_week=league_week)
    }
    revealed = {game.id: context.is_revealed(game, now) for game in games}
    tiebreakers_revealed = now >= league_week.picks_lock_at

    grid = PicksGrid(
        league_week=league_week,
        columns=[
            GridColumn(game=game, home_text=_home_text(context, game)) for game in games
        ],
    )
    for membership in memberships:
        own = membership.pk == viewer.pk
        grid.rows.append(
            GridRow(
                membership=membership,
                cells=[
                    _cell(picks.get((membership.pk, game.id)), own or revealed[game.id])
                    for game in games
                ],
                tiebreaker_guess=entries.get(membership.pk)
                if own or tiebreakers_revealed
                else None,
                tiebreaker_revealed=own or tiebreakers_revealed,
            )
        )
    return grid


def _home_text(context: WeekContext, game: Game) -> str:
    spread = context.spreads.get(game.id)
    if spread is None:
        return ""
    if spread.status == SpreadStatus.VOID:
        return "void"
    return team_line(spread.home_line, is_home=True)


def _cell(pick: Pick | None, revealed: bool) -> GridCell:
    # Unrevealed cells carry no pick at all, so templates cannot leak them.
    return GridCell(
        revealed=revealed, has_pick=pick is not None, pick=pick if revealed else None
    )


def _games(league_week: LeagueWeek) -> list[Game]:
    return list(
        league_week.week.games.exclude(status=GameStatus.CANCELLED)
        .select_related("home_team", "away_team")
        .order_by("kickoff_at", "external_id")
    )


def _state(
    game: Game,
    spread: Spread | None,
    context: WeekContext,
    now: datetime,
    week_open: bool,
) -> str:
    if spread is not None and spread.status == SpreadStatus.VOID:
        return "void"
    if context.is_locked(game, now):
        return "locked"
    if not week_open:
        return "not_open"
    if spread is None or spread.status == SpreadStatus.OFF:
        return "off"
    return "open"
