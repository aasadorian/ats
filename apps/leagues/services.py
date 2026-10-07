import hashlib
import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.activity.models import ActorType
from apps.activity.services import record_event
from apps.leagues.models import (
    Invite,
    League,
    LeagueSeason,
    LeagueSettings,
    LeagueWeek,
    LeagueWeekStatus,
    Membership,
    Role,
    TiebreakerGame,
)
from apps.leagues.schedule import lock_times
from apps.nfl.models import Game, GameStatus, Season

INVITE_LIFETIME = timedelta(days=14)


class LeagueError(Exception):
    pass


class InviteError(LeagueError):
    pass


class AlreadyMemberError(LeagueError):
    pass


class LastCommissionerError(LeagueError):
    pass


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# Leagues, seasons and weeks


@transaction.atomic
def create_league(
    *, name: str, slug: str, commissioner: User, season_year: int
) -> League:
    league = League.objects.create(name=name, slug=slug)
    Membership.objects.create(user=commissioner, league=league, role=Role.COMMISSIONER)
    record_event(
        event_type="league.created",
        summary=f"League {name} created with {commissioner} as commissioner",
        actor_type=ActorType.ADMIN,
        league=league,
        subject_user=commissioner,
        obj=league,
    )
    start_league_season(league, Season.objects.get(year=season_year))
    return league


@transaction.atomic
def start_league_season(league: League, season: Season) -> LeagueSeason:
    league_season = LeagueSeason.objects.create(league=league, season=season)
    previous = (
        LeagueSettings.objects.filter(league_season__league=league)
        .exclude(league_season=league_season)
        .order_by("-league_season__season__year")
        .first()
    )
    if previous is None:
        LeagueSettings.objects.create(league_season=league_season)
    else:
        previous.pk = None
        previous.league_season = league_season
        previous._state.adding = True
        previous.save()
    ensure_league_weeks(league_season)
    return league_season


def ensure_league_weeks(league_season: LeagueSeason) -> list[LeagueWeek]:
    league_settings = league_season.settings
    timezone_name = league_season.league.timezone
    existing = set(league_season.weeks.values_list("week_id", flat=True))
    created = []
    for week in league_season.season.weeks.exclude(id__in=existing):
        spreads_at, picks_at = lock_times(
            week.sunday,
            spread_weekday=league_settings.spread_lock_weekday,
            spread_time=league_settings.spread_lock_time,
            picks_weekday=league_settings.picks_lock_weekday,
            picks_time=league_settings.picks_lock_time,
            timezone_name=timezone_name,
        )
        created.append(
            LeagueWeek.objects.create(
                league_season=league_season,
                week=week,
                spreads_lock_at=spreads_at,
                picks_lock_at=picks_at,
            )
        )
    refresh_tiebreaker_games(league_season)
    return created


def last_game_of_week(league_week: LeagueWeek) -> Game | None:
    return (
        league_week.week.games.exclude(status=GameStatus.CANCELLED)
        .order_by("-kickoff_at", "-external_id")
        .first()
    )


def refresh_tiebreaker_games(
    league_season: LeagueSeason, now: datetime | None = None
) -> None:
    """Point each week at its last game; changes stop once picks lock."""
    if league_season.settings.tiebreaker_game != TiebreakerGame.LAST_GAME_OF_WEEK:
        return
    now = now or timezone.now()
    weeks = league_season.weeks.filter(
        Q(picks_lock_at__gt=now) | Q(tiebreaker_game__isnull=True)
    ).select_related("week")
    for league_week in weeks:
        game = last_game_of_week(league_week)
        if game is not None and league_week.tiebreaker_game_id != game.id:
            previous = league_week.tiebreaker_game
            league_week.tiebreaker_game = game
            league_week.save(update_fields=["tiebreaker_game"])
            record_event(
                event_type=(
                    "tiebreaker_game.changed" if previous else "tiebreaker_game.set"
                ),
                summary=f"{league_week.week} tiebreaker game: {game}",
                league=league_season.league,
                league_week=league_week,
                obj=league_week,
                before={"tiebreaker_game": str(previous)} if previous else None,
                after={"tiebreaker_game": str(game)},
            )


def refresh_league_weeks(season: Season) -> None:
    for league_season in LeagueSeason.objects.filter(season=season):
        with transaction.atomic():
            ensure_league_weeks(league_season)


def current_league_season(league: League) -> LeagueSeason | None:
    return league.seasons.select_related("season", "settings").first()


# Memberships and invites


def active_membership(user: User, league: League) -> Membership | None:
    if not user.is_authenticated:
        return None
    return Membership.objects.filter(user=user, league=league, is_active=True).first()


@transaction.atomic
def invite_member(
    league: League, *, email: str, role: Role, invited_by: User
) -> tuple[Invite, str]:
    email = email.strip().lower()
    if Membership.objects.filter(
        league=league, user__email=email, is_active=True
    ).exists():
        raise AlreadyMemberError(f"{email} is already a member of {league}.")
    for stale in Invite.objects.pending().filter(league=league, email=email):
        _revoke(stale, actor=invited_by, reason="replaced by a new invite")

    token = secrets.token_urlsafe(32)
    invite = Invite.objects.create(
        league=league,
        email=email,
        role=role,
        token_hash=hash_token(token),
        invited_by=invited_by,
        expires_at=timezone.now() + INVITE_LIFETIME,
    )
    record_event(
        event_type="invite.sent",
        summary=f"{invited_by} invited {email} as {role.label.lower()}",
        actor=invited_by,
        actor_type=ActorType.COMMISSIONER,
        league=league,
        obj=invite,
        after={"email": email, "role": role.value},
    )
    transaction.on_commit(lambda: send_invite_email(invite, token))
    return invite, token


def resend_invite(invite: Invite, *, actor: User) -> tuple[Invite, str]:
    if not invite.is_usable:
        raise InviteError("Only pending invites can be resent.")
    return invite_member(
        invite.league, email=invite.email, role=Role(invite.role), invited_by=actor
    )


@transaction.atomic
def revoke_invite(invite: Invite, *, actor: User) -> None:
    if not invite.is_usable:
        raise InviteError("Only pending invites can be revoked.")
    _revoke(invite, actor=actor, reason="revoked")


def _revoke(invite: Invite, *, actor: User, reason: str) -> None:
    invite.revoked_at = timezone.now()
    invite.save(update_fields=["revoked_at"])
    record_event(
        event_type="invite.revoked",
        summary=f"Invite for {invite.email} {reason}",
        actor=actor,
        actor_type=ActorType.COMMISSIONER,
        league=invite.league,
        obj=invite,
    )


def find_invite(token: str) -> Invite | None:
    return (
        Invite.objects.select_related("league")
        .filter(token_hash=hash_token(token))
        .first()
    )


@transaction.atomic
def accept_invite(invite: Invite, user: User) -> Membership:
    invite = Invite.objects.select_for_update().get(pk=invite.pk)
    if not invite.is_usable:
        raise InviteError("This invite is no longer valid.")
    if invite.email != user.email:
        raise InviteError("This invite was sent to a different email address.")

    membership, created = Membership.objects.get_or_create(
        user=user, league=invite.league, defaults={"role": invite.role}
    )
    if not created:
        membership.is_active = True
        membership.deactivated_at = None
        membership.role = invite.role
        membership.save(update_fields=["is_active", "deactivated_at", "role"])

    invite.accepted_at = timezone.now()
    invite.accepted_by = user
    invite.save(update_fields=["accepted_at", "accepted_by"])
    record_event(
        event_type="invite.accepted",
        summary=f"{user} joined {invite.league}",
        actor=user,
        league=invite.league,
        obj=membership,
        after={"role": membership.role},
    )
    return membership


@transaction.atomic
def change_role(membership: Membership, role: Role, *, actor: User) -> None:
    if membership.role == role:
        return
    if membership.role == Role.COMMISSIONER:
        _ensure_another_commissioner(membership)
    before = membership.role
    membership.role = role
    membership.save(update_fields=["role"])
    record_event(
        event_type="membership.role_changed",
        summary=f"{actor} changed {membership.user} from {before} to {role}",
        actor=actor,
        actor_type=ActorType.COMMISSIONER,
        league=membership.league,
        subject_user=membership.user,
        obj=membership,
        before={"role": before},
        after={"role": role.value},
    )
    transaction.on_commit(lambda: send_role_changed_email(membership, actor))


@transaction.atomic
def deactivate_membership(membership: Membership, *, actor: User) -> None:
    if not membership.is_active:
        return
    if membership.role == Role.COMMISSIONER:
        _ensure_another_commissioner(membership)
    membership.is_active = False
    membership.deactivated_at = timezone.now()
    membership.save(update_fields=["is_active", "deactivated_at"])
    record_event(
        event_type="membership.deactivated",
        summary=f"{actor} deactivated {membership.user}",
        actor=actor,
        actor_type=ActorType.COMMISSIONER,
        league=membership.league,
        subject_user=membership.user,
        obj=membership,
    )


@transaction.atomic
def reactivate_membership(membership: Membership, *, actor: User) -> None:
    if membership.is_active:
        return
    membership.is_active = True
    membership.deactivated_at = None
    membership.save(update_fields=["is_active", "deactivated_at"])
    record_event(
        event_type="membership.reactivated",
        summary=f"{actor} reactivated {membership.user}",
        actor=actor,
        actor_type=ActorType.COMMISSIONER,
        league=membership.league,
        subject_user=membership.user,
        obj=membership,
    )


def _ensure_another_commissioner(membership: Membership) -> None:
    others = (
        Membership.objects.select_for_update()
        .filter(league=membership.league, role=Role.COMMISSIONER, is_active=True)
        .exclude(pk=membership.pk)
    )
    if not others.exists():
        raise LastCommissionerError("A league must keep at least one commissioner.")


def send_role_changed_email(membership: Membership, actor: User) -> None:
    send_mail(
        subject=f"Your role in {membership.league} changed",
        message=render_to_string(
            "email/role_changed.txt", {"membership": membership, "actor": actor}
        ),
        from_email=None,
        recipient_list=[membership.user.email],
    )


def send_invite_email(invite: Invite, token: str) -> None:
    context = {
        "invite": invite,
        "url": settings.SITE_URL + reverse("leagues:invite", args=[token]),
        "expires": timezone.localtime(invite.expires_at),
    }
    send_mail(
        subject=f"You're invited to {invite.league}",
        message=render_to_string("email/invite.txt", context),
        from_email=None,
        recipient_list=[invite.email],
    )


# Settings

SCHEDULE_FIELDS = (
    "spread_lock_weekday",
    "spread_lock_time",
    "picks_lock_weekday",
    "picks_lock_time",
)
SCORING_FIELDS = (
    "pick_type",
    "points_per_win",
    "best_bets_per_week",
    "best_bet_bonus",
    "push_scoring",
    "weekly_prize_metric",
)


class RetroactiveChangeError(LeagueError):
    pass


@transaction.atomic
def update_settings(
    league_settings: LeagueSettings,
    changes: dict[str, object],
    *,
    actor: User,
    apply_to_season: bool = False,
) -> list[str]:
    """Apply settings changes under the mid-season rules in docs/08 section 3.

    Scoring changes after the first week opens recalculate the whole season, so
    they need explicit confirmation. Lock-time changes recompute every week that
    hasn't opened yet.
    """
    changed = [
        name
        for name, value in changes.items()
        if getattr(league_settings, name) != value
    ]
    if not changed:
        return []
    league_season = league_settings.league_season
    season_started = league_season.weeks.exclude(
        status=LeagueWeekStatus.SCHEDULED
    ).exists()
    scoring = [name for name in changed if name in SCORING_FIELDS]
    if scoring and season_started and not apply_to_season:
        raise RetroactiveChangeError(
            "Scoring settings changed after the season started: "
            + ", ".join(scoring)
            + ". Confirm that the change applies to the whole season."
        )

    before = {name: _jsonable(getattr(league_settings, name)) for name in changed}
    for name in changed:
        setattr(league_settings, name, changes[name])
    league_settings.full_clean()
    league_settings.save()

    if any(name in SCHEDULE_FIELDS for name in changed):
        _recompute_unpublished_weeks(league_season)
    record_event(
        event_type="settings.changed",
        summary=f"{actor} changed {', '.join(changed)}"
        + (" (applied to the whole season)" if scoring and season_started else ""),
        actor=actor,
        actor_type=ActorType.COMMISSIONER,
        league=league_season.league,
        obj=league_settings,
        before=before,
        after={name: _jsonable(getattr(league_settings, name)) for name in changed},
    )
    return changed


def _recompute_unpublished_weeks(league_season: LeagueSeason) -> None:
    league_settings = league_season.settings
    for league_week in league_season.weeks.filter(
        status=LeagueWeekStatus.SCHEDULED
    ).select_related("week"):
        spreads_at, picks_at = lock_times(
            league_week.week.sunday,
            spread_weekday=league_settings.spread_lock_weekday,
            spread_time=league_settings.spread_lock_time,
            picks_weekday=league_settings.picks_lock_weekday,
            picks_time=league_settings.picks_lock_time,
            timezone_name=league_season.league.timezone,
        )
        league_week.spreads_lock_at = spreads_at
        league_week.picks_lock_at = picks_at
        league_week.save(update_fields=["spreads_lock_at", "picks_lock_at"])


def _jsonable(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool | list | dict):
        return value
    return str(value)


@transaction.atomic
def leave_league(membership: Membership) -> None:
    if not membership.is_active:
        return
    if membership.role == Role.COMMISSIONER:
        _ensure_another_commissioner(membership)
    membership.is_active = False
    membership.deactivated_at = timezone.now()
    membership.save(update_fields=["is_active", "deactivated_at"])
    record_event(
        event_type="member.left",
        summary=f"{membership.user} left the league",
        actor=membership.user,
        league=membership.league,
        subject_user=membership.user,
        obj=membership,
    )
