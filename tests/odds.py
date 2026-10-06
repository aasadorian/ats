from datetime import UTC, datetime
from typing import Any

from apps.lines.feeds.odds_api import OddsFetch, parse_odds

BOOKS = ["draftkings", "fanduel", "betmgm", "caesars", "espnbet", "betrivers"]


def odds_event(
    home: str,
    away: str,
    home_points: list[float],
    *,
    moneyline: tuple[int, int] | None = None,
    commence: datetime | None = None,
) -> dict[str, Any]:
    """An event shaped like The Odds API v4 /odds response."""
    bookmakers = []
    for index, point in enumerate(home_points):
        markets: list[dict[str, Any]] = [
            {
                "key": "spreads",
                "outcomes": [
                    {"name": home, "price": -110, "point": point},
                    {"name": away, "price": -110, "point": -point},
                ],
            }
        ]
        if moneyline is not None:
            markets.append(
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": home, "price": moneyline[0]},
                        {"name": away, "price": moneyline[1]},
                    ],
                }
            )
        bookmakers.append(
            {"key": BOOKS[index], "title": BOOKS[index].title(), "markets": markets}
        )
    return {
        "id": f"{home}-{away}",
        "sport_key": "americanfootball_nfl",
        "commence_time": (commence or datetime(2026, 9, 13, 17, tzinfo=UTC))
        .isoformat()
        .replace("+00:00", "Z"),
        "home_team": home,
        "away_team": away,
        "bookmakers": bookmakers,
    }


class FakeOddsProvider:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = events
        self.calls = 0

    def fetch(self, start: datetime, end: datetime) -> OddsFetch:
        self.calls += 1
        return OddsFetch(games=parse_odds(self.events), payload=self.events)
