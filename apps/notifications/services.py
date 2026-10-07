import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.urls import reverse

from apps.leagues.models import LeagueWeek, LeagueWeekStatus, Membership, Role
from apps.lines.models import Spread, SpreadKind, SpreadStatus
from apps.lines.services import MIN_BOOKS, describe
from apps.notifications.email import send
from apps.notifications.models import Dispatch, Kind
from apps.picks.selectors import pick_sheet
from apps.picks.services import OPEN_STATUSES
from apps.standings.selectors import week_results

logger = logging.getLogger(__name__)

REMINDER_WINDOW = timedelta(hours=6)
RESULTS_WINDOW = timedelta(days=30)


def send_notifications(now: datetime) -> list[str]:
    sent: list[str] = []
    open_weeks = _weeks().filter(status__in=OPEN_STATUSES, picks_lock_at__gt=now)
    for league_week in open_weeks:
        sent += _week_open(league_week, now)
        sent += _reminders(league_week, now)
    final_weeks = _weeks().filter(
        status=LeagueWeekStatus.FINAL, week__ends_at__gt=now - RESULTS_WINDOW
    )
    for league_week in final_weeks:
        sent += _weekly_results(league_week, now)
    return sent


def reminder_slots(league_week: LeagueWeek) -> list[datetime]:
    """Configured reminder times that fall between line lock and the pick deadline."""
    league_season = league_week.league_season
    tz = ZoneInfo(league_season.league.timezone)
    start = league_week.spreads_lock_at.astimezone(tz)
    end = league_week.picks_lock_at.astimezone(tz)
    slots = []
    for reminder in league_season.settings.reminder_times:
        hour, minute = (int(part) for part in str(reminder["time"]).split(":"))
        day = start.date()
        while day <= end.date():
            if day.weekday() == int(reminder["weekday"]):
                moment = datetime.combine(day, time(hour, minute), tzinfo=tz)
                if start < moment <= end:
                    slots.append(moment)
            day += timedelta(days=1)
    return sorted(slots)


def _week_open(league_week: LeagueWeek, now: datetime) -> list[str]:
    if not _claim(Kind.WEEK_OPEN, league_week, "", now):
        return []
    url = _url("picks:sheet", league_week)
    count = 0
    for membership in _members(league_week):
        count += send(
            membership.user,
            Kind.WEEK_OPEN,
            subject=f"{league_week.week} lines are locked: make your picks",
            template="email/week_open.txt",
            context={"league_week": league_week, "url": url},
        )
    spreads = list(
        Spread.objects.filter(
            league_season=league_week.league_season,
            kind=SpreadKind.LOCKED,
            game__week=league_week.week,
        ).select_related("game__home_team", "game__away_team")
    )
    flagged = [
        describe(s)
        for s in spreads
        if s.status != SpreadStatus.POSTED
        or (s.book_count < MIN_BOOKS and not s.overridden)
    ]
    for membership in _members(league_week).filter(role=Role.COMMISSIONER):
        count += send(
            membership.user,
            Kind.COMMISSIONER,
            subject=f"{league_week.week} lines locked: {len(flagged)} to review",
            template="email/lines_locked.txt",
            context={
                "league_week": league_week,
                "lines": [describe(s) for s in spreads],
                "flagged": flagged,
                "url": _url("lines:review", league_week),
            },
        )
    _record(Kind.WEEK_OPEN, league_week, "", count)
    return [f"{league_week}: week open ({count} emails)"]


def _reminders(league_week: LeagueWeek, now: datetime) -> list[str]:
    results = []
    for slot in reminder_slots(league_week):
        if not slot <= now < slot + REMINDER_WINDOW:
            continue
        key = slot.isoformat()
        if not _claim(Kind.REMINDERS, league_week, key, now):
            continue
        count = 0
        for membership in _members(league_week):
            sheet = pick_sheet(membership, league_week, now)
            missing_guess = sheet.entry is None or sheet.entry.tiebreaker_guess is None
            missing_best_bet = sheet.best_bet_limit > 0 and sheet.best_bets == 0
            if not (sheet.unpicked_open or missing_best_bet or missing_guess):
                continue
            count += send(
                membership.user,
                Kind.REMINDERS,
                subject=f"Reminder: {league_week.week} picks",
                template="email/reminder.txt",
                context={
                    "league_week": league_week,
                    "sheet": sheet,
                    "missing_best_bet": missing_best_bet,
                    "missing_guess": missing_guess,
                    "url": _url("picks:sheet", league_week),
                },
            )
        _record(Kind.REMINDERS, league_week, key, count)
        results.append(f"{league_week}: reminder {key} ({count} emails)")
    return results


def _weekly_results(league_week: LeagueWeek, now: datetime) -> list[str]:
    if not _claim(Kind.WEEKLY_RESULTS, league_week, "", now):
        return []
    results = week_results(league_week)
    count = 0
    for member in results.members:
        if not member.membership.is_active:
            continue
        count += send(
            member.membership.user,
            Kind.WEEKLY_RESULTS,
            subject=f"{league_week.week} results",
            template="email/weekly_results.txt",
            context={
                "league_week": league_week,
                "results": results,
                "member": member,
                "url": _url("standings:week", league_week),
            },
        )
    _record(Kind.WEEKLY_RESULTS, league_week, "", count)
    return [f"{league_week}: results ({count} emails)"]


def _claim(kind: Kind, league_week: LeagueWeek, key: str, now: datetime) -> bool:
    try:
        with transaction.atomic():
            Dispatch.objects.create(
                kind=kind, league_week=league_week, key=key, sent_at=now
            )
    except IntegrityError:
        return False
    return True


def _record(kind: Kind, league_week: LeagueWeek, key: str, count: int) -> None:
    Dispatch.objects.filter(kind=kind, league_week=league_week, key=key).update(
        recipients=count
    )
    logger.info("Sent %s %s %s to %s recipients", kind, league_week, key, count)


def _weeks() -> QuerySet[LeagueWeek]:
    return LeagueWeek.objects.select_related(
        "week",
        "league_season__league",
        "league_season__settings",
        "tiebreaker_game__home_team",
        "tiebreaker_game__away_team",
    )


def _members(league_week: LeagueWeek) -> QuerySet[Membership]:
    return league_week.league_season.league.memberships.filter(
        is_active=True
    ).select_related("user")


def _url(name: str, league_week: LeagueWeek) -> str:
    path = reverse(name, args=[league_week.league_season.league.slug])
    return f"{settings.SITE_URL}{path}?week={league_week.week.number}"
