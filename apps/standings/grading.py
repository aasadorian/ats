from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from apps.leagues.models import LeagueSettings, LineMode, PickType, PushScoring
from apps.lines.models import Spread, SpreadStatus
from apps.nfl.models import Game, GameStatus
from apps.picks.models import Pick

ZERO = Decimal(0)


class Outcome(StrEnum):
    WIN = "win"
    LOSS = "loss"
    PUSH = "push"
    PENDING = "pending"
    VOID = "void"


@dataclass(frozen=True)
class GradedPick:
    pick: Pick
    outcome: Outcome
    points: Decimal

    @property
    def is_best_bet(self) -> bool:
        return self.pick.is_best_bet


def scoring_line(
    pick: Pick, spread: Spread | None, league_settings: LeagueSettings
) -> Decimal | None:
    if league_settings.pick_type == PickType.STRAIGHT_UP:
        return ZERO
    if league_settings.line_mode == LineMode.VARIABLE:
        return pick.home_line_at_pick
    # Closing-line mode is a later phase; until then it scores like fixed-at-lock.
    return spread.home_line if spread is not None else None


def grade(
    pick: Pick, game: Game, spread: Spread | None, league_settings: LeagueSettings
) -> GradedPick:
    if game.status == GameStatus.CANCELLED or (
        spread is not None and spread.status == SpreadStatus.VOID
    ):
        return GradedPick(pick, Outcome.VOID, ZERO)
    if (
        game.status != GameStatus.FINAL
        or game.home_score is None
        or game.away_score is None
    ):
        return GradedPick(pick, Outcome.PENDING, ZERO)
    line = scoring_line(pick, spread, league_settings)
    if line is None:
        return GradedPick(pick, Outcome.VOID, ZERO)

    margin = Decimal(game.home_score - game.away_score) + line
    if pick.team_id == game.away_team_id:
        margin = -margin
    if margin > 0:
        outcome = Outcome.WIN
    elif margin < 0:
        outcome = Outcome.LOSS
    else:
        outcome = Outcome.PUSH
    return GradedPick(pick, outcome, points_for(outcome, pick, league_settings))


def points_for(
    outcome: Outcome, pick: Pick, league_settings: LeagueSettings
) -> Decimal:
    base = Decimal(league_settings.points_per_win)
    if pick.is_best_bet:
        base += league_settings.best_bet_bonus
    if outcome == Outcome.WIN:
        return base
    if outcome == Outcome.PUSH:
        return {
            PushScoring.HALF_POINTS: base / 2,
            PushScoring.WIN: base,
            PushScoring.LOSS: ZERO,
        }[PushScoring(league_settings.push_scoring)]
    return ZERO


def cover_margin(game: Game, line: Decimal | None) -> Decimal | None:
    """Home team's margin against the line; positive means the home team covered."""
    if line is None or game.home_score is None or game.away_score is None:
        return None
    return Decimal(game.home_score - game.away_score) + line
