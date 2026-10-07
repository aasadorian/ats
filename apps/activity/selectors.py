from dataclasses import dataclass
from datetime import date, datetime

from django.db.models import Q, QuerySet

from apps.accounts.models import User
from apps.activity.models import ActivityEvent, Category
from apps.leagues.models import League

FEED_CATEGORIES = (
    Category.LINES,
    Category.GAMES,
    Category.STANDINGS,
    Category.SETTINGS,
)
FEED_MEMBERSHIP_EVENTS = ("invite.accepted", "member.left")


@dataclass(frozen=True)
class EventView:
    """An event as one viewer may see it; pick details stay hidden until lock."""

    event: ActivityEvent
    summary: str
    before: object
    after: object
    redacted: bool


@dataclass(frozen=True)
class LogFilters:
    member: User | None = None
    week_number: int | None = None
    category: str = ""
    event_type: str = ""
    since: date | None = None
    until: date | None = None


def league_feed(league: League) -> QuerySet[ActivityEvent]:
    return (
        _base()
        .filter(league=league)
        .filter(
            Q(category__in=FEED_CATEGORIES) | Q(event_type__in=FEED_MEMBERSHIP_EVENTS)
        )
    )


def member_activity(league: League, user: User) -> QuerySet[ActivityEvent]:
    return _base().filter(
        Q(league=league, subject_user=user)
        | Q(league=league, actor=user)
        | Q(league__isnull=True, actor=user, category=Category.SECURITY)
    )


def commissioner_log(league: League, filters: LogFilters) -> QuerySet[ActivityEvent]:
    events = _base().filter(league=league)
    if filters.member is not None:
        events = events.filter(Q(actor=filters.member) | Q(subject_user=filters.member))
    if filters.week_number is not None:
        events = events.filter(league_week__week__number=filters.week_number)
    if filters.category:
        events = events.filter(category=filters.category)
    if filters.event_type:
        events = events.filter(event_type=filters.event_type)
    if filters.since:
        events = events.filter(occurred_at__date__gte=filters.since)
    if filters.until:
        events = events.filter(occurred_at__date__lte=filters.until)
    return events


def visible(event: ActivityEvent, viewer: User, now: datetime) -> EventView:
    """Hide which team another member picked until that week's pick deadline.

    The commissioner sees that a pick changed but not to what, the same rule as
    the picks grid; it is applied per week rather than per game because cleared
    picks no longer exist to look up.
    """
    hidden = (
        event.category == Category.PICKS
        and event.subject_user_id not in (None, viewer.pk)
        and event.actor_id != viewer.pk
        and event.league_week is not None
        and now < event.league_week.picks_lock_at
    )
    if not hidden:
        return EventView(event, event.summary, event.before, event.after, False)
    who = event.subject_user or event.actor
    return EventView(event, f"{who} updated their picks", None, None, True)


def _base() -> QuerySet[ActivityEvent]:
    return ActivityEvent.objects.select_related(
        "actor", "subject_user", "league_week__week"
    ).order_by("-occurred_at", "-id")
