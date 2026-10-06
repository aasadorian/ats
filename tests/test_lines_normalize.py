from datetime import UTC, datetime
from decimal import Decimal

import pytest

from apps.lines.feeds.odds_api import parse_odds
from apps.lines.models import format_line
from apps.lines.normalize import (
    is_half_point,
    median_line,
    normalize_home_line,
    round_to_half,
)
from tests.odds import odds_event

D = Decimal


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (D("-3"), D("-3")),
        (D("-3.25"), D("-3.5")),
        (D("3.25"), D("3.5")),
        (D("-3.2"), D("-3")),
        (D("-3.75"), D("-4")),
        (D("0.1"), D("0")),
    ],
)
def test_round_to_half(raw: Decimal, expected: Decimal) -> None:
    assert round_to_half(raw) == expected


@pytest.mark.parametrize(
    ("raw", "favorite_gives", "expected"),
    [
        (D("-3"), True, D("-3.5")),
        (D("3"), True, D("3.5")),
        (D("-3"), False, D("-2.5")),
        (D("3"), False, D("2.5")),
        (D("-6.5"), True, D("-6.5")),
        (D("-1.75"), True, D("-2.5")),
    ],
)
def test_half_point_normalization(
    raw: Decimal, favorite_gives: bool, expected: Decimal
) -> None:
    line = normalize_home_line(
        raw,
        half_point_lines=True,
        favorite_gives=favorite_gives,
        home_is_moneyline_favorite=None,
    )
    assert line == expected
    assert is_half_point(line)


@pytest.mark.parametrize(
    ("home_favored", "expected"),
    [(True, D("-0.5")), (False, D("0.5")), (None, D("-0.5"))],
)
def test_pickem_goes_to_moneyline_favorite(
    home_favored: bool | None, expected: Decimal
) -> None:
    line = normalize_home_line(
        D("0"),
        half_point_lines=True,
        favorite_gives=True,
        home_is_moneyline_favorite=home_favored,
    )
    assert line == expected


def test_whole_lines_kept_when_half_points_off() -> None:
    line = normalize_home_line(
        D("-3"),
        half_point_lines=False,
        favorite_gives=True,
        home_is_moneyline_favorite=True,
    )
    assert line == D("-3")


def test_median_of_even_count() -> None:
    assert median_line([D("-3"), D("-3.5"), D("-3"), D("-3.5")]) == D("-3.25")


@pytest.mark.parametrize(
    ("line", "text"),
    [(D("-3.5"), "-3.5"), (D("7.5"), "+7.5"), (D("0"), "PK"), (None, "OFF")],
)
def test_format_line(line: Decimal | None, text: str) -> None:
    assert format_line(line) == text


def test_parse_odds_reads_home_points_and_moneyline() -> None:
    payload = [
        odds_event(
            "Seattle Seahawks",
            "New England Patriots",
            [-3, -3, -3.5],
            moneyline=(-160, 135),
            commence=datetime(2026, 9, 10, 0, 20, tzinfo=UTC),
        )
    ]
    game = parse_odds(payload)[0]
    assert game.home_points == (D("-3"), D("-3"), D("-3.5"))
    assert game.home_is_moneyline_favorite is True
    assert game.commence_time == datetime(2026, 9, 10, 0, 20, tzinfo=UTC)
