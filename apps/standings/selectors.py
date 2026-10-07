import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Q

from apps.leagues.models import (
    LeagueSeason,
    LeagueWeek,
    LeagueWeekStatus,
    Membership,
    TiebreakerType,
    WeeklyPrizeMetric,
)
from apps.lines.models import Spread
from apps.nfl.models import Game, GameStatus
from apps.picks.models import Pick, WeeklyEntry
from apps.picks.services import WeekContext
from apps.standings.grading import ZERO, GradedPick, Outcome, cover_margin, grade


@dataclass
class MemberWeek:
    membership: Membership
    graded: dict[int, GradedPick] = field(default_factory=dict)
    tiebreaker_guess: int | None = None
    tiebreaker_distance: float | None = None

    @property
    def points(self) -> Decimal:
        return sum((g.points for g in self.graded.values()), ZERO)

    def count(self, outcome: Outcome) -> int:
        return sum(1 for g in self.graded.values() if g.outcome == outcome)

    @property
    def wins(self) -> int:
        return self.count(Outcome.WIN)

    @property
    def losses(self) -> int:
        return self.count(Outcome.LOSS)

    @property
    def pushes(self) -> int:
        return self.count(Outcome.PUSH)

    @property
    def best_bet(self) -> GradedPick | None:
        return next((g for g in self.graded.values() if g.is_best_bet), None)


@dataclass(frozen=True)
class GameResult:
    game: Game
    spread: Spread | None
    home_margin: Decimal | None

    @property
    def covering_team(self) -> str:
        if self.home_margin is None or self.home_margin == 0:
            return ""
        team = self.game.home_team if self.home_margin > 0 else self.game.away_team
        return team.abbreviation


@dataclass
class WeekResults:
    league_week: LeagueWeek
    members: list[MemberWeek]
    games: list[GameResult]
    winners: list[Membership]
    tiebreaker_actual: int | None
    decided_by_tiebreaker: bool

    @property
    def is_final(self) -> bool:
        return self.league_week.status == LeagueWeekStatus.FINAL

    @property
    def is_split(self) -> bool:
        return len(self.winners) > 1


@dataclass
class SeasonRow:
    membership: Membership
    points: Decimal = ZERO
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    best_bet_wins: int = 0
    best_bet_losses: int = 0
    best_bet_pushes: int = 0
    weekly_wins: int = 0
    rank: int = 0


@dataclass
class SeasonStandings:
    league_season: LeagueSeason
    rows: list[SeasonRow]
    best_bet_rows: list[SeasonRow]
    weeks: list[WeekResults]
    is_complete: bool

    @property
    def points_leaders(self) -> list[Membership]:
        if not self.rows or self.rows[0].points == 0:
            return []
        return [row.membership for row in self.rows if row.rank == 1]

    @property
    def best_bet_leaders(self) -> list[Membership]:
        if not self.best_bet_rows or self.best_bet_rows[0].best_bet_wins == 0:
            return []
        top = self.best_bet_rows[0].best_bet_wins
        return [r.membership for r in self.best_bet_rows if r.best_bet_wins == top]


SCORED_STATUSES = (
    LeagueWeekStatus.PUBLISHED,
    LeagueWeekStatus.IN_PROGRESS,
    LeagueWeekStatus.FINAL,
)


def week_results(league_week: LeagueWeek) -> WeekResults:
    context = WeekContext.load(league_week)
    league_settings = context.settings
    games = list(
        league_week.week.games.select_related("home_team", "away_team").order_by(
            "kickoff_at", "external_id"
        )
    )
    games_by_id = {game.id: game for game in games}
    picks = list(
        Pick.objects.filter(week=league_week.week)
        .filter(membership__league=league_week.league_season.league)
        .select_related("membership__user", "team")
    )
    members: dict[int, MemberWeek] = {
        m.pk: MemberWeek(m) for m in _participants(league_week, picks)
    }
    for pick in picks:
        game = games_by_id[pick.game_id]
        members[pick.membership_id].graded[pick.game_id] = grade(
            pick, game, context.spreads.get(game.id), league_settings
        )
    for entry in WeeklyEntry.objects.filter(league_week=league_week):
        if entry.membership_id in members:
            members[entry.membership_id].tiebreaker_guess = entry.tiebreaker_guess

    actual = _tiebreaker_actual(league_week)
    metric = league_settings.weekly_prize_metric
    ordered = sorted(
        members.values(),
        key=lambda m: (-_metric(m, metric), str(m.membership.user)),
    )
    winners, decided_by_tiebreaker = _weekly_winners(ordered, metric, actual)
    return WeekResults(
        league_week=league_week,
        members=ordered,
        games=[
            GameResult(
                game=game,
                spread=context.spreads.get(game.id),
                home_margin=cover_margin(
                    game,
                    context.spreads[game.id].home_line
                    if game.id in context.spreads
                    else None,
                )
                if game.status == GameStatus.FINAL
                else None,
            )
            for game in games
        ],
        winners=winners,
        tiebreaker_actual=actual,
        decided_by_tiebreaker=decided_by_tiebreaker,
    )


def season_standings(league_season: LeagueSeason) -> SeasonStandings:
    weeks = [
        week_results(league_week)
        for league_week in league_season.weeks.filter(status__in=SCORED_STATUSES)
        .select_related("week", "league_season__settings", "league_season__league")
        .order_by("week__number")
    ]
    rows: dict[int, SeasonRow] = {}
    for results in weeks:
        for member in results.members:
            row = rows.setdefault(member.membership.pk, SeasonRow(member.membership))
            row.points += member.points
            row.wins += member.wins
            row.losses += member.losses
            row.pushes += member.pushes
            best_bet = member.best_bet
            if best_bet is not None:
                row.best_bet_wins += best_bet.outcome == Outcome.WIN
                row.best_bet_losses += best_bet.outcome == Outcome.LOSS
                row.best_bet_pushes += best_bet.outcome == Outcome.PUSH
        if results.is_final:
            for winner in results.winners:
                rows[winner.pk].weekly_wins += 1

    by_points = sorted(
        rows.values(), key=lambda r: (-r.points, -r.wins, str(r.membership.user))
    )
    _rank(by_points)
    by_best_bets = sorted(
        rows.values(),
        key=lambda r: (-r.best_bet_wins, r.best_bet_losses, str(r.membership.user)),
    )
    return SeasonStandings(
        league_season=league_season,
        rows=by_points,
        best_bet_rows=by_best_bets,
        weeks=weeks,
        is_complete=not league_season.weeks.exclude(
            status=LeagueWeekStatus.FINAL
        ).exists(),
    )


def _participants(league_week: LeagueWeek, picks: Iterable[Pick]) -> list[Membership]:
    """Active members, plus anyone who has since left but made picks that week."""
    picked = {pick.membership_id for pick in picks}
    return list(
        Membership.objects.filter(league=league_week.league_season.league)
        .filter(Q(is_active=True) | Q(pk__in=picked))
        .select_related("user")
    )


def _metric(member: MemberWeek, metric: str) -> Decimal:
    if metric == WeeklyPrizeMetric.WINS:
        return Decimal(member.wins)
    return member.points


def _tiebreaker_actual(league_week: LeagueWeek) -> int | None:
    game = league_week.tiebreaker_game
    if game is None or game.home_score is None or game.away_score is None:
        return None
    if game.status != GameStatus.FINAL:
        return None
    if league_week.league_season.settings.tiebreaker_type == (
        TiebreakerType.MARGIN_OF_VICTORY
    ):
        return abs(game.home_score - game.away_score)
    return game.home_score + game.away_score


def _weekly_winners(
    ordered: list[MemberWeek], metric: str, actual: int | None
) -> tuple[list[Membership], bool]:
    if not ordered:
        return [], False
    best = _metric(ordered[0], metric)
    if best == 0:
        return [], False
    leaders = [m for m in ordered if _metric(m, metric) == best]
    if len(leaders) == 1 or actual is None:
        return [m.membership for m in leaders], False

    distances = {}
    for member in leaders:
        guess = member.tiebreaker_guess
        distance = float(abs(guess - actual)) if guess is not None else math.inf
        member.tiebreaker_distance = distance
        distances[member.membership.pk] = distance
    closest = min(distances.values())
    winners = [m.membership for m in leaders if distances[m.membership.pk] == closest]
    return winners, True


def _rank(rows: list[SeasonRow]) -> None:
    previous: Decimal | None = None
    for position, row in enumerate(rows, start=1):
        if row.points != previous:
            row.rank = position
            previous = row.points
        else:
            row.rank = rows[position - 2].rank
