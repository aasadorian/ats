# 05 — External Data Sources

We need three kinds of data: the **schedule** (once per season, with updates for flex games),
**spreads** (once per week at lock time), and **scores/status** (during games).

## 1. Spreads

### Primary: The Odds API (the-odds-api.com)
- Endpoint: `/v4/sports/americanfootball_nfl/odds?markets=spreads&regions=us`
- Free tier (~500 requests/month) is far more than we need: ~1–2 calls per week at lock time,
  plus a few during development.
- Returns lines per bookmaker. **Canonical line ✅: the median home line across all US sportsbooks**
  the feed returns for that game at lock time (`rules.spread_source = "median_us_books"`).
  The number of books used is stored with the snapshot. If fewer than 3 books have a line,
  the commissioner is alerted to review it before publishing.

### Half-point normalization ✅
Every locked line must end in `.5`. Normalization after choosing the raw line:
1. Round the raw line to the nearest 0.5. A median can land on a quarter, like `-3.25`; exact
   quarters round away from zero (`-3.25 → -3.5`).
2. If the result is a whole number, **the favorite gives the extra half point**
   (`rules.half_point_rounding = "favorite_gives_more"`): `KC -3 / BUF +3 → KC -3.5 / BUF +3.5`.
3. A pick'em (`0`) becomes `-0.5` for the team favored by the moneyline (or the home team if even).

The raw value is kept in `Spread.feed_line`, and the commissioner can override any result.
- Matching: odds feed uses team names + commence time; map to our `Game` by (home team, away team,
  kickoff date).

### Fallback: commissioner entry
The weekly "Review spreads" screen shows every game for the week with the fetched line (or blank)
and lets the commissioner type/adjust lines before publishing. If the feed fails at lock time,
the job alerts the commissioner and the week stays unpublished until lines are entered.

## 2. Schedule and scores

### Primary: ESPN public scoreboard JSON
- `https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?week={n}&seasontype=2&dates={year}`
- Free, no key, includes schedule, kickoff times, live status, and final scores.
- **Caveat:** undocumented/unofficial; could change without notice. Wrap it behind an interface
  so it can be swapped.

### Alternatives / backups
| Source | Notes |
|--------|-------|
| The Odds API `/scores` endpoint | Scores for recent games; costs credits but already integrated |
| nflverse (`nfl_data_py` / published CSVs) | Excellent for schedule and historical results; not real-time |
| SportsDataIO / MySportsFeeds | Official-ish paid APIs; overkill unless free sources break |
| Manual entry | Commissioner score-correction screen always available |

## 3. Integration design

```python
class ScheduleProvider(Protocol):
    def fetch_week(self, season: int, week: int) -> list[GameData]: ...

class OddsProvider(Protocol):
    def fetch_spreads(self, season: int, week: int) -> list[SpreadData]: ...

class ScoreProvider(Protocol):
    def fetch_scores(self, season: int, week: int) -> list[ScoreData]: ...
```

- Each provider is a small module in `apps/nfl/feeds/`, returning plain dataclasses.
- Sync commands upsert by `external_id`, so they're idempotent.
- Raw responses are logged (or stored briefly) to debug feed issues.
- Recorded fixtures (saved JSON responses) back the tests — no live API calls in CI.

## 4. Edge cases to handle
- **Flexed / rescheduled games**: kickoff times change → daily `sync_schedule` updates `kickoff_at`.
  If a game moves to before the Sunday 10 AM PT lock (e.g., a Saturday game late in the season), it
  locks at its own kickoff automatically, since locks read `min(kickoff_at, picks_lock_at)`.
- **Postponed games** ✅: stay in their original week, keep their locked spread, and are scored when
  played (see [01 §2.4.1](01-product-requirements.md)). `sync_scores` must keep polling any
  `postponed` game until it's final, even after the week has ended, which a weekly-only feed
  query would miss. `sync_schedule` records `postponed_from` the first time it sees the status change.
- **Cancelled outright** (e.g., 2022 BUF–CIN, never completed): assumed void, 0 points for everyone;
  commissioner marks it `cancelled` so the week can close. Still to confirm (06).
- **Missing line at lock time** (e.g., QB injury takes a game off the board): commissioner enters it
  manually or the game is excluded that week.
- **Neutral-site / international games**: feed still names a nominal home team; nothing special needed.
- **Pick'em lines (0)**: converted to ±0.5 (see half-point normalization above).
