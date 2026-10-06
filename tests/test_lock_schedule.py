from datetime import UTC, date, datetime, time

import pytest
from django.core.exceptions import ValidationError

from apps.leagues.models import LeagueSettings, Weekday
from apps.leagues.schedule import lock_times, picks_lock_date, spreads_lock_date

PACIFIC = "America/Los_Angeles"


def default_lock_times(sunday: date) -> tuple[datetime, datetime]:
    return lock_times(
        sunday,
        spread_weekday=Weekday.TUESDAY,
        spread_time=time(3, 0),
        picks_weekday=Weekday.SUNDAY,
        picks_time=time(10, 0),
        timezone_name=PACIFIC,
    )


def test_default_lock_times_during_daylight_time() -> None:
    spreads_at, picks_at = default_lock_times(date(2026, 9, 13))
    assert spreads_at == datetime(2026, 9, 8, 10, 0, tzinfo=UTC)
    assert picks_at == datetime(2026, 9, 13, 17, 0, tzinfo=UTC)


def test_default_lock_times_after_daylight_time_ends() -> None:
    spreads_at, picks_at = default_lock_times(date(2026, 11, 8))
    assert spreads_at == datetime(2026, 11, 3, 11, 0, tzinfo=UTC)
    assert picks_at == datetime(2026, 11, 8, 18, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("weekday", "expected"),
    [
        (Weekday.MONDAY, date(2026, 9, 7)),
        (Weekday.TUESDAY, date(2026, 9, 8)),
        (Weekday.SATURDAY, date(2026, 9, 12)),
        (Weekday.SUNDAY, date(2026, 9, 6)),
    ],
)
def test_spreads_lock_date_is_in_the_six_days_before_sunday(
    weekday: Weekday, expected: date
) -> None:
    assert spreads_lock_date(date(2026, 9, 13), weekday) == expected


@pytest.mark.parametrize(
    ("weekday", "expected"),
    [
        (Weekday.THURSDAY, date(2026, 9, 10)),
        (Weekday.SUNDAY, date(2026, 9, 13)),
        (Weekday.MONDAY, date(2026, 9, 14)),
    ],
)
def test_picks_lock_date_spans_thursday_to_wednesday(
    weekday: Weekday, expected: date
) -> None:
    assert picks_lock_date(date(2026, 9, 13), weekday) == expected


def test_settings_reject_spread_lock_after_pick_deadline() -> None:
    league_settings = LeagueSettings(
        spread_lock_weekday=Weekday.SATURDAY, picks_lock_weekday=Weekday.THURSDAY
    )
    with pytest.raises(ValidationError):
        league_settings.clean()


def test_default_settings_are_valid() -> None:
    LeagueSettings().clean()
