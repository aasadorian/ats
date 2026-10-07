from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.activity.models import ActorType
from apps.activity.services import record_event
from apps.leagues.models import (
    LeagueSettings,
    LeagueWeek,
    LeagueWeekStatus,
    Membership,
    PickVisibility,
)
from apps.leagues.schedule import game_lock_at
from apps.lines.models import Spread, SpreadKind, SpreadStatus, team_line
from apps.nfl.models import Game, Team
from apps.picks.models import Pick, WeeklyEntry

OPEN_STATUSES = (LeagueWeekStatus.PUBLISHED, LeagueWeekStatus.IN_PROGRESS)


class PickError(Exception):
    pass


class PickLockedError(PickError):
    pass


@dataclass(frozen=True)
class WeekContext:
    league_week: LeagueWeek
    settings: LeagueSettings
    spreads: dict[int, Spread]

    @classmethod
    def load(cls, league_week: LeagueWeek) -> "WeekContext":
        spreads = Spread.objects.filter(
            league_season=league_week.league_season,
            kind=SpreadKind.LOCKED,
            game__week=league_week.week,
        )
        return cls(
            league_week=league_week,
            settings=league_week.league_season.settings,
            spreads={spread.game_id: spread for spread in spreads},
        )

    def lock_at(self, game: Game) -> datetime:
        return game_lock_at(
            kickoff_at=game.kickoff_at,
            postponed_from=game.postponed_from,
            picks_lock_at=self.league_week.picks_lock_at,
            offset_minutes=self.settings.game_lock_offset_minutes,
        )

    def is_locked(self, game: Game, now: datetime) -> bool:
        return now >= self.lock_at(game)

    def is_revealed(self, game: Game, now: datetime) -> bool:
        if self.settings.pick_visibility == PickVisibility.AT_WEEKLY_DEADLINE:
            return now >= self.league_week.picks_lock_at
        return self.is_locked(game, now)

    def posted_spread(self, game: Game) -> Spread | None:
        spread = self.spreads.get(game.id)
        if spread is None or spread.status != SpreadStatus.POSTED:
            return None
        return spread


def save_pick(
    membership: Membership,
    league_week: LeagueWeek,
    game: Game,
    team: Team,
    *,
    actor: User | None = None,
    now: datetime | None = None,
) -> Pick:
    now = now or timezone.now()
    context = WeekContext.load(league_week)
    spread = _ensure_pickable(membership, context, game, now, actor)
    if team.id not in (game.home_team_id, game.away_team_id):
        raise PickError("That team isn't playing in this game.")
    line = team_line(spread.home_line, is_home=team.id == game.home_team_id)

    with transaction.atomic():
        _lock_entry(membership, league_week)
        pick = Pick.objects.filter(membership=membership, game=game).first()
        if pick is None:
            pick = Pick.objects.create(
                membership=membership,
                game=game,
                week=game.week,
                team=team,
                home_line_at_pick=spread.home_line,
            )
            _record(
                "pick.made",
                f"picked {team} {line} in {game}",
                membership,
                league_week,
                pick,
                actor,
                after={"team": str(team), "line": line},
            )
        elif pick.team_id != team.id:
            before = str(pick.team)
            pick.team = team
            pick.home_line_at_pick = spread.home_line
            pick.save(update_fields=["team", "home_line_at_pick", "updated_at"])
            _record(
                "pick.changed",
                f"changed {game} from {before} to {team} {line}",
                membership,
                league_week,
                pick,
                actor,
                before={"team": before},
                after={"team": str(team), "line": line},
            )
    return pick


def clear_pick(
    membership: Membership,
    league_week: LeagueWeek,
    game: Game,
    *,
    actor: User | None = None,
    now: datetime | None = None,
) -> None:
    now = now or timezone.now()
    context = WeekContext.load(league_week)
    _ensure_pickable(membership, context, game, now, actor)
    with transaction.atomic():
        _lock_entry(membership, league_week)
        pick = Pick.objects.filter(membership=membership, game=game).first()
        if pick is None:
            return
        before = {"team": str(pick.team), "best_bet": pick.is_best_bet}
        pick.delete()
        _record(
            "pick.cleared",
            f"cleared their pick in {game}",
            membership,
            league_week,
            None,
            actor,
            before=before,
        )


def set_best_bet(
    membership: Membership,
    league_week: LeagueWeek,
    game: Game,
    *,
    on: bool,
    actor: User | None = None,
    now: datetime | None = None,
) -> None:
    now = now or timezone.now()
    context = WeekContext.load(league_week)
    limit = context.settings.best_bets_per_week
    if limit == 0:
        raise PickError("This league doesn't use best bets.")
    _ensure_pickable(membership, context, game, now, actor)

    with transaction.atomic():
        _lock_entry(membership, league_week)
        pick = Pick.objects.filter(membership=membership, game=game).first()
        if pick is None:
            raise PickError("Pick a team in this game first.")
        if pick.is_best_bet == on:
            return
        if not on:
            _set_star(pick, on=False)
            _record(
                "best_bet.cleared",
                f"removed their best bet on {game}",
                membership,
                league_week,
                pick,
                actor,
            )
            return

        current = list(
            Pick.objects.filter(
                membership=membership, week=game.week, is_best_bet=True
            ).select_related("game", "team")
        )
        if len(current) < limit:
            _set_star(pick, on=True)
            _record(
                "best_bet.set",
                f"made {pick.team} in {game} a best bet",
                membership,
                league_week,
                pick,
                actor,
            )
            return
        if limit > 1:
            raise PickError(f"You already have {limit} best bets; remove one first.")

        previous = current[0]
        if context.is_locked(previous.game, now):
            raise PickLockedError(
                f"Your best bet on {previous.game} is locked and can't be moved."
            )
        _set_star(previous, on=False)
        _set_star(pick, on=True)
        _record(
            "best_bet.moved",
            f"moved their best bet from {previous.game} to {game}",
            membership,
            league_week,
            pick,
            actor,
            before={"game": str(previous.game)},
            after={"game": str(game)},
        )


def set_tiebreaker(
    membership: Membership,
    league_week: LeagueWeek,
    guess: int | None,
    *,
    actor: User | None = None,
    now: datetime | None = None,
) -> WeeklyEntry:
    now = now or timezone.now()
    if league_week.status not in OPEN_STATUSES:
        raise PickError("This week isn't open for picks yet.")
    if now >= league_week.picks_lock_at:
        raise PickLockedError("Tiebreaker guesses are locked for this week.")
    if guess is not None and not 0 <= guess <= 200:
        raise PickError("Enter a guess between 0 and 200.")
    with transaction.atomic():
        entry = _lock_entry(membership, league_week)
        if entry.tiebreaker_guess == guess:
            return entry
        before = entry.tiebreaker_guess
        entry.tiebreaker_guess = guess
        entry.save(update_fields=["tiebreaker_guess", "updated_at"])
        _record(
            "tiebreaker.changed" if before is not None else "tiebreaker.set",
            f"set their tiebreaker guess to {guess}",
            membership,
            league_week,
            entry,
            actor,
            before={"guess": before},
            after={"guess": guess},
        )
    return entry


def _ensure_pickable(
    membership: Membership,
    context: WeekContext,
    game: Game,
    now: datetime,
    actor: User | None,
) -> Spread:
    league_week = context.league_week
    if not membership.is_active:
        raise PickError("Your membership isn't active.")
    if (
        membership.league_id != league_week.league_season.league_id
        or game.week_id != league_week.week_id
    ):
        raise PickError("That game isn't part of this league week.")
    if league_week.status not in OPEN_STATUSES:
        raise PickError("This week isn't open for picks yet.")
    if context.is_locked(game, now):
        # Recorded outside any transaction so the attempt is kept for disputes.
        _record(
            "pick.rejected_locked",
            f"tried to change {game} after it locked",
            membership,
            league_week,
            None,
            actor,
        )
        raise PickLockedError(f"{game} is locked.")
    spread = context.posted_spread(game)
    if spread is None:
        raise PickError(f"{game} has no line yet.")
    return spread


def _lock_entry(membership: Membership, league_week: LeagueWeek) -> WeeklyEntry:
    WeeklyEntry.objects.get_or_create(membership=membership, league_week=league_week)
    return WeeklyEntry.objects.select_for_update().get(
        membership=membership, league_week=league_week
    )


def _set_star(pick: Pick, *, on: bool) -> None:
    pick.is_best_bet = on
    pick.save(update_fields=["is_best_bet", "updated_at"])


def _record(
    event_type: str,
    action: str,
    membership: Membership,
    league_week: LeagueWeek,
    obj: Pick | WeeklyEntry | None,
    actor: User | None,
    *,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
) -> None:
    acting_user = actor or membership.user
    on_behalf = acting_user.pk != membership.user_id
    record_event(
        event_type=event_type,
        summary=f"{acting_user} {action}"
        + (f" for {membership.user}" if on_behalf else ""),
        actor=acting_user,
        actor_type=ActorType.COMMISSIONER if on_behalf else ActorType.MEMBER,
        league=league_week.league_season.league,
        league_week=league_week,
        subject_user=membership.user,
        obj=obj,
        before=before,
        after=after,
    )
