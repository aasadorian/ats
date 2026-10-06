from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from apps.activity.models import ActivityEvent
from apps.leagues.models import (
    LeagueSeason,
    LeagueWeek,
    LeagueWeekStatus,
    OffLineHandling,
)
from apps.lines.models import OddsSnapshot, Spread, SpreadStatus
from apps.lines.services import (
    LineError,
    lock_spreads,
    override_line,
    refresh_off_lines,
)
from tests.factories import make_league
from tests.odds import FakeOddsProvider, odds_event

AFTER_LOCK = datetime(2026, 9, 8, 11, tzinfo=UTC)
BEFORE_FIRST_KICKOFF = datetime(2026, 9, 9, 12, tzinfo=UTC)
AFTER_FIRST_KICKOFF = datetime(2026, 9, 10, 2, tzinfo=UTC)

SEA_NE = odds_event(
    "Seattle Seahawks",
    "New England Patriots",
    [-3, -3, -3.5, -3],
    moneyline=(-160, 135),
)
KC_BUF = odds_event("Kansas City Chiefs", "Buffalo Bills", [-1.5, -2, -2, -1.5])
DAL_NYG = odds_event("Dallas Cowboys", "New York Giants", [-6.5, -7, -7])


def spread_for(home: str) -> Spread:
    return Spread.objects.select_related("game").get(game__home_team__abbreviation=home)


def week1() -> LeagueWeek:
    return LeagueWeek.objects.get(week__number=1)


@pytest.fixture
def league(db: None) -> Any:
    return make_league()


def test_lock_publishes_week_with_normalized_lines(league: Any) -> None:
    provider = FakeOddsProvider([SEA_NE, KC_BUF])
    result = lock_spreads(provider, now=AFTER_LOCK)

    sea = spread_for("SEA")
    assert sea.home_line == Decimal("-3.5")
    assert sea.feed_line == Decimal("-3")
    assert sea.book_count == 4
    assert spread_for("KC").home_line == Decimal("-2.5")
    assert spread_for("DAL").status == SpreadStatus.OFF
    assert week1().status == LeagueWeekStatus.PUBLISHED
    assert result.lines_posted == 2
    assert result.lines_off == 1
    assert provider.calls == 1
    events = set(ActivityEvent.objects.values_list("event_type", flat=True))
    assert {"line.locked", "line.off", "week.published"} <= events


def test_nothing_happens_before_lock_time(league: Any) -> None:
    provider = FakeOddsProvider([SEA_NE])
    lock_spreads(provider, now=datetime(2026, 9, 7, tzinfo=UTC))
    assert provider.calls == 0
    assert not Spread.objects.exists()


def test_locking_twice_changes_nothing(league: Any) -> None:
    lock_spreads(FakeOddsProvider([SEA_NE, KC_BUF]), now=AFTER_LOCK)
    later = FakeOddsProvider(
        [odds_event("Seattle Seahawks", "New England Patriots", [-7])]
    )
    lock_spreads(later, now=AFTER_LOCK)
    assert later.calls == 0
    assert spread_for("SEA").home_line == Decimal("-3.5")


def test_weeks_already_locked_for_picks_are_skipped(league: Any) -> None:
    provider = FakeOddsProvider([SEA_NE])
    lock_spreads(provider, now=datetime(2026, 9, 14, tzinfo=UTC))
    assert not Spread.objects.filter(game__week__number=1).exists()


def test_off_line_posted_when_it_appears_before_cutoff(league: Any) -> None:
    lock_spreads(FakeOddsProvider([SEA_NE, KC_BUF]), now=AFTER_LOCK)
    refresh_off_lines(FakeOddsProvider([DAL_NYG]), now=BEFORE_FIRST_KICKOFF)
    dal = spread_for("DAL")
    assert dal.status == SpreadStatus.POSTED
    assert dal.home_line == Decimal("-7.5")
    assert ActivityEvent.objects.filter(event_type="line.posted_late").exists()


def test_off_line_voided_at_first_kickoff_of_week(league: Any) -> None:
    lock_spreads(FakeOddsProvider([SEA_NE, KC_BUF]), now=AFTER_LOCK)
    late = FakeOddsProvider([DAL_NYG])
    refresh_off_lines(late, now=AFTER_FIRST_KICKOFF)
    dal = spread_for("DAL")
    assert dal.status == SpreadStatus.VOID
    assert dal.home_line is None
    assert late.calls == 0


def test_hold_week_setting_waits_for_commissioner(league: Any) -> None:
    league_settings = LeagueSeason.objects.get(league=league).settings
    league_settings.off_line_handling = OffLineHandling.HOLD_WEEK
    league_settings.save()

    lock_spreads(FakeOddsProvider([SEA_NE, KC_BUF]), now=AFTER_LOCK)
    assert week1().status == LeagueWeekStatus.SCHEDULED

    commissioner = league.memberships.get().user
    override_line(
        spread_for("DAL"), Decimal("-6.5"), actor=commissioner, reason="posted late"
    )
    assert week1().status == LeagueWeekStatus.PUBLISHED


def test_override_requires_half_point_line(league: Any) -> None:
    lock_spreads(FakeOddsProvider([SEA_NE, KC_BUF]), now=AFTER_LOCK)
    commissioner = league.memberships.get().user
    with pytest.raises(LineError):
        override_line(spread_for("SEA"), Decimal("-3"), actor=commissioner, reason="x")


def test_override_is_logged_with_before_and_after(league: Any) -> None:
    lock_spreads(FakeOddsProvider([SEA_NE, KC_BUF]), now=AFTER_LOCK)
    commissioner = league.memberships.get().user
    override_line(
        spread_for("SEA"), Decimal("-4.5"), actor=commissioner, reason="QB out"
    )
    sea = spread_for("SEA")
    assert sea.home_line == Decimal("-4.5")
    assert sea.overridden
    event = ActivityEvent.objects.get(event_type="line.overridden")
    assert event.before == {"home_line": "-3.5", "status": "posted"}
    assert event.after is not None
    assert event.after["reason"] == "QB out"
    assert event.actor == commissioner


def test_reversed_home_and_away_in_feed_is_flipped(league: Any) -> None:
    reversed_feed = odds_event(
        "New England Patriots", "Seattle Seahawks", [3, 3, 3.5], moneyline=(135, -160)
    )
    lock_spreads(FakeOddsProvider([reversed_feed, KC_BUF]), now=AFTER_LOCK)
    assert spread_for("SEA").home_line == Decimal("-3.5")


def test_low_book_count_is_reported(league: Any) -> None:
    thin = odds_event("Kansas City Chiefs", "Buffalo Bills", [-2.5, -2.5])
    result = lock_spreads(FakeOddsProvider([SEA_NE, thin]), now=AFTER_LOCK)
    assert result.low_book_games == ["BUF @ KC"]


def test_off_line_refresh_is_throttled(league: Any) -> None:
    lock_spreads(FakeOddsProvider([SEA_NE, KC_BUF]), now=AFTER_LOCK)
    assert OddsSnapshot.objects.get().fetched_at == AFTER_LOCK

    too_soon = FakeOddsProvider([DAL_NYG])
    refresh_off_lines(too_soon, now=AFTER_LOCK + timedelta(minutes=15))
    assert too_soon.calls == 0
    assert spread_for("DAL").status == SpreadStatus.OFF

    later = FakeOddsProvider([DAL_NYG])
    refresh_off_lines(later, now=AFTER_LOCK + timedelta(hours=2))
    assert later.calls == 1
    assert spread_for("DAL").status == SpreadStatus.POSTED
