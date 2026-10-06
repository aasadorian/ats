from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def spreads_lock_date(sunday: date, weekday: int) -> date:
    """The configured weekday in the six days before the week's Sunday."""
    day_before = sunday - timedelta(days=1)
    return day_before - timedelta(days=(day_before.weekday() - weekday) % 7)


def picks_lock_date(sunday: date, weekday: int) -> date:
    """The configured weekday from the Thursday before to the Wednesday after Sunday."""
    thursday = sunday - timedelta(days=3)
    return thursday + timedelta(days=(weekday - thursday.weekday()) % 7)


def local_datetime(day: date, at: time, timezone_name: str) -> datetime:
    return datetime.combine(day, at, tzinfo=ZoneInfo(timezone_name))


def lock_times(
    sunday: date,
    *,
    spread_weekday: int,
    spread_time: time,
    picks_weekday: int,
    picks_time: time,
    timezone_name: str,
) -> tuple[datetime, datetime]:
    spreads_at = local_datetime(
        spreads_lock_date(sunday, spread_weekday), spread_time, timezone_name
    )
    picks_at = local_datetime(
        picks_lock_date(sunday, picks_weekday), picks_time, timezone_name
    )
    return spreads_at, picks_at


def game_lock_at(
    *,
    kickoff_at: datetime,
    postponed_from: datetime | None,
    picks_lock_at: datetime,
    offset_minutes: int,
) -> datetime:
    """When picks on a game lock; a postponement never reopens them."""
    kickoff = postponed_from or kickoff_at
    return min(kickoff - timedelta(minutes=offset_minutes), picks_lock_at)
