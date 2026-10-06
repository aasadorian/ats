# 05 — External Data Sources

We need three kinds of data: the **schedule** (once per season, with updates for flex games),
**spreads** (once per week at lock time), and **scores/status** (during games).

## 1. Spreads

### Primary: The Odds API (the-odds-api.com)
- Endpoint: `/v4/sports/americanfootball_nfl/odds?markets=spreads&regions=us`
- Free tier: 500 credits/month. A request costs 1 credit per market per region; we request
  `spreads,h2h` (moneyline, used only to pick the favorite on pick'em lines) for region `us`, so
  **2 credits per request**. One request returns every game in the week window.
  - Default fixed-at-lock mode: 1 request per week at lock (~8 credits/month), plus at most one
    request every 2 hours while a game is OFF (throttled; worst case ~60 credits for a line that
    stays OFF from Tuesday to Thursday).
  - `variable`/`closing` modes (later phase) would need more frequent requests; budget them then.
- **Implemented (milestone 3):** `apps/lines/feeds/odds_api.py`.
  - Games are matched by full team name (`Team.location + name`, which matches the feed's names
    for all 32 teams); if the feed lists home and away the other way round (neutral sites), the
    line is flipped.
  - Every response is stored as an `OddsSnapshot`, so the raw data behind any locked line can be
    checked later.
  - Requires `ODDS_API_KEY` in `.env` (free key from the-odds-api.com).
- Returns lines per bookmaker. **Canonical line ✅: the median home line across all US sportsbooks**
  the feed returns for that game at lock time (`line_source = "median_us_books"`). The
  `line_source` setting can instead name a single sportsbook.
  The number of books used is stored with the snapshot. If fewer than 3 books have a line,
  the commissioner is alerted to review it before publishing.

### Half-point normalization ✅
Every locked line must end in `.5`. Normalization after choosing the raw line:
1. Round the raw line to the nearest 0.5. A median can land on a quarter, like `-3.25`; exact
   quarters round away from zero (`-3.25 → -3.5`).
2. If the result is a whole number, **the favorite gives the extra half point**
   (`half_point_rounding = "favorite_gives"`, the default): `KC -3 / BUF +3 → KC -3.5 / BUF +3.5`.
   The setting can be flipped to `favorite_gets`, and `half_point_lines` can be turned off
   entirely to use whole-number lines with pushes.
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
- **Implemented (milestone 1):** `apps/nfl/feeds/espn.py`, behind the `ScheduleProvider` protocol.
  - **Weeks** come from the response's `leagues[0].calendar` (regular season = `value "2"`): each
    week's start/end window. `Week.sunday` is the last Sunday (Pacific) in that window.
  - **Status mapping:** `STATUS_POSTPONED` → postponed, `STATUS_CANCELED` → cancelled,
    state `in` → in progress, state `post` + completed → final, otherwise scheduled.
  - **TBD kickoffs** (`isTBDFlex`, or `timeValid` false) are flagged `Game.kickoff_is_tbd`.
  - 19 requests per full sync (calendar + 18 weeks), about 3 seconds.
  - Some weeks open on a **Wednesday** (2026: week 1 and week 12, Thanksgiving eve), which
    confirms the "first kickoff of the week" wording for the OFF-line cutoff.

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
- **Missing ("OFF") line at lock time** (e.g., QB injury takes a game off the board): handled by
  `off_line_handling` ✅. The week publishes with that game unpickable; `refresh_lines` fills the
  line once it's posted (normalized and locked the same way), or the commissioner enters one. If
  there's still no line at the **first kickoff of the week** (normally Thursday night), the game is
  **void for the week** (`off_line_fallback = void`).
- **Neutral-site / international games**: feed still names a nominal home team; nothing special needed.
- **Pick'em lines (0)**: converted to ±0.5 (see half-point normalization above).
