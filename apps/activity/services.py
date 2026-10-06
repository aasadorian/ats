from typing import TYPE_CHECKING, Any

from django.db import models

from apps.activity.context import current_context
from apps.activity.models import ActivityEvent, ActorType, Category

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.leagues.models import League, LeagueWeek

_CATEGORY_BY_PREFIX = {
    "line": Category.LINES,
    "week": Category.LINES,
    "pick": Category.PICKS,
    "best_bet": Category.PICKS,
    "tiebreaker": Category.PICKS,
    "game": Category.GAMES,
    "tiebreaker_game": Category.GAMES,
    "standings": Category.STANDINGS,
    "settings": Category.SETTINGS,
    "league": Category.SETTINGS,
    "invite": Category.MEMBERSHIP,
    "membership": Category.MEMBERSHIP,
    "member": Category.MEMBERSHIP,
    "auth": Category.SECURITY,
    "account": Category.SECURITY,
    "email": Category.NOTIFICATIONS,
}


def category_for(event_type: str) -> Category:
    prefix = event_type.split(".", 1)[0]
    if prefix not in _CATEGORY_BY_PREFIX:
        raise ValueError(f"Unknown event type prefix: {event_type}")
    return _CATEGORY_BY_PREFIX[prefix]


def record_event(
    *,
    event_type: str,
    summary: str,
    actor: "User | None" = None,
    actor_type: ActorType | None = None,
    league: "League | None" = None,
    league_week: "LeagueWeek | None" = None,
    subject_user: "User | None" = None,
    obj: models.Model | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> ActivityEvent:
    """Append an activity event.

    Call inside the same transaction as the change being recorded, so the change
    and its event commit or roll back together.
    """
    context = current_context()
    category = category_for(event_type)
    object_type = (obj._meta.model_name or "") if obj is not None else ""
    object_id = str(obj.pk) if obj is not None else ""
    return ActivityEvent.objects.create(
        event_type=event_type,
        category=category,
        summary=summary[:255],
        actor=actor,
        actor_type=actor_type or (ActorType.MEMBER if actor else ActorType.SYSTEM),
        league=league,
        league_week=league_week,
        subject_user=subject_user,
        object_type=object_type,
        object_id=object_id,
        before=before,
        after=after,
        source=context.source,
        request_id=context.request_id,
        ip_address=context.ip_address if category == Category.SECURITY else None,
    )
