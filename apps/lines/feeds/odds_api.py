import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from statistics import median_low
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

ODDS_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
SOURCE = "the-odds-api"


class OddsFeedError(Exception):
    pass


@dataclass(frozen=True)
class GameOdds:
    home_team: str
    away_team: str
    commence_time: datetime
    home_points: tuple[Decimal, ...]
    home_is_moneyline_favorite: bool | None


@dataclass(frozen=True)
class OddsFetch:
    games: list[GameOdds]
    payload: list[dict[str, Any]]


class OddsProvider(Protocol):
    def fetch(self, start: datetime, end: datetime) -> OddsFetch: ...


class OddsApiProvider:
    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(20.0), transport=httpx.HTTPTransport(retries=2)
        )

    def fetch(self, start: datetime, end: datetime) -> OddsFetch:
        if not self._api_key:
            raise OddsFeedError("ODDS_API_KEY is not configured.")
        params = {
            "apiKey": self._api_key,
            "regions": "us",
            "markets": "spreads,h2h",
            "oddsFormat": "american",
            "commenceTimeFrom": _iso(start),
            "commenceTimeTo": _iso(end),
        }
        try:
            response = self._client.get(ODDS_URL, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OddsFeedError(f"Odds API request failed: {exc}") from exc
        logger.info(
            "Odds API credits used %s, remaining %s",
            response.headers.get("x-requests-used"),
            response.headers.get("x-requests-remaining"),
        )
        payload: list[dict[str, Any]] = response.json()
        return OddsFetch(games=parse_odds(payload), payload=payload)


def parse_odds(payload: list[dict[str, Any]]) -> list[GameOdds]:
    return [_parse_event(event) for event in payload]


def _parse_event(event: dict[str, Any]) -> GameOdds:
    home, away = event["home_team"], event["away_team"]
    home_points: list[Decimal] = []
    home_prices: list[int] = []
    away_prices: list[int] = []
    for bookmaker in event.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            outcomes = {o["name"]: o for o in market.get("outcomes", [])}
            if home not in outcomes or away not in outcomes:
                continue
            if market["key"] == "spreads" and "point" in outcomes[home]:
                home_points.append(Decimal(str(outcomes[home]["point"])))
            elif market["key"] == "h2h":
                home_prices.append(int(outcomes[home]["price"]))
                away_prices.append(int(outcomes[away]["price"]))
    return GameOdds(
        home_team=home,
        away_team=away,
        commence_time=datetime.fromisoformat(event["commence_time"]),
        home_points=tuple(home_points),
        home_is_moneyline_favorite=_home_favored(home_prices, away_prices),
    )


def _home_favored(home_prices: list[int], away_prices: list[int]) -> bool | None:
    if not home_prices:
        return None
    home, away = median_low(home_prices), median_low(away_prices)
    if home == away:
        return None
    return home < away


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
