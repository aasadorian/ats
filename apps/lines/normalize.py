from decimal import ROUND_HALF_UP, Decimal
from statistics import median

HALF = Decimal("0.5")


def median_line(points: list[Decimal]) -> Decimal:
    if not points:
        raise ValueError("No lines to take a median of.")
    return Decimal(median(points))


def round_to_half(line: Decimal) -> Decimal:
    """Nearest half point; exact quarters round away from zero."""
    doubled = (abs(line) * 2).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    rounded = doubled / 2
    return rounded if line >= 0 else -rounded


def normalize_home_line(
    raw: Decimal,
    *,
    half_point_lines: bool,
    favorite_gives: bool,
    home_is_moneyline_favorite: bool | None,
) -> Decimal:
    """Turn a raw home line into the line the league plays.

    With half-point lines on, a whole number moves half a point: away from zero
    when the favorite gives the extra half (-3 becomes -3.5, +3 becomes +3.5),
    toward zero when the favorite gets it. A pick'em goes to the moneyline
    favorite at -0.5, or to the home team when there is no favorite.
    """
    line = round_to_half(raw)
    if not half_point_lines or line % 1 != 0:
        return line
    if line == 0:
        return -HALF if home_is_moneyline_favorite is not False else HALF
    away_from_zero = HALF if line > 0 else -HALF
    return line + away_from_zero if favorite_gives else line - away_from_zero


def is_half_point(line: Decimal) -> bool:
    return abs(line) % 1 == HALF
