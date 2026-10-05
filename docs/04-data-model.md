# 04 — Data Model

## 1. Entity diagram

```mermaid
erDiagram
    USER ||--o{ MEMBERSHIP : has
    LEAGUE ||--o{ MEMBERSHIP : has
    LEAGUE ||--o{ LEAGUE_SEASON : runs
    SEASON ||--o{ LEAGUE_SEASON : "is played as"
    SEASON ||--o{ WEEK : contains
    WEEK ||--o{ GAME : contains
    TEAM ||--o{ GAME : "home/away"
    LEAGUE_SEASON ||--o{ LEAGUE_WEEK : has
    WEEK ||--o{ LEAGUE_WEEK : "is played as"
    LEAGUE_SEASON ||--o{ SPREAD : locks
    GAME ||--o{ SPREAD : "line for"
    MEMBERSHIP ||--o{ PICK : makes
    GAME ||--o{ PICK : "picked in"
    MEMBERSHIP ||--o{ WEEKLY_ENTRY : submits
    LEAGUE_WEEK ||--o{ WEEKLY_ENTRY : "tiebreaker for"
    USER ||--o{ AUDIT_EVENT : performs

    USER {
        int id
        string email
        string display_name
    }
    LEAGUE {
        int id
        string name
        string slug
        string timezone
    }
    MEMBERSHIP {
        int id
        int user_id
        int league_id
        string role
        bool is_active
    }
    SEASON {
        int id
        int year
    }
    LEAGUE_SEASON {
        int id
        int league_id
        int season_id
        int spread_lock_weekday
        time spread_lock_time
        int picks_lock_weekday
        time picks_lock_time
        json rules
    }
    WEEK {
        int id
        int season_id
        int number
        date sunday
    }
    LEAGUE_WEEK {
        int id
        int league_season_id
        int week_id
        datetime spreads_lock_at
        datetime picks_lock_at
        int tiebreaker_game_id
        string status
    }
    TEAM {
        int id
        string abbr
        string name
        string external_id
    }
    GAME {
        int id
        int week_id
        int home_team_id
        int away_team_id
        datetime kickoff_at
        datetime postponed_from
        string status
        int home_score
        int away_score
        string external_id
    }
    SPREAD {
        int id
        int league_season_id
        int game_id
        decimal home_line
        decimal feed_line
        int book_count
        string source
        datetime locked_at
        bool overridden
    }
    PICK {
        int id
        int membership_id
        int game_id
        int week_id
        int team_id
        bool is_best_bet
        datetime updated_at
    }
    WEEKLY_ENTRY {
        int id
        int membership_id
        int league_week_id
        int mnf_total_guess
    }
    AUDIT_EVENT {
        int id
        int user_id
        string action
        json before
        json after
        datetime at
    }
```

**Global NFL data** (`Season`, `Week`, `Team`, `Game`) is shared by all leagues and filled in by the
feed sync jobs.

**League-specific data** (`LeagueSeason`, `LeagueWeek`, `Spread`) hangs off the league, because the
spread lock time is configurable per league. Two leagues that lock at different times would lock
different lines.

## 2. Key fields and constraints

### LeagueSeason — lock configuration
| Field | Default | Meaning |
|-------|---------|---------|
| `spread_lock_weekday` / `spread_lock_time` | Tuesday / 12:00 | When the week's lines are snapshotted |
| `picks_lock_weekday` / `picks_lock_time` | Sunday / 10:00 | When all not-yet-started games lock |
| `league.timezone` | `America/Los_Angeles` | Timezone the above are interpreted in (DST-aware) |

### LeagueWeek — the concrete schedule for one week
- `spreads_lock_at`, `picks_lock_at` — UTC datetimes **computed** from the `LeagueSeason` config
  when the week is created (e.g., the Tuesday before `week.sunday` at 12:00 PT, and `week.sunday`
  at 10:00 PT). Stored, so the commissioner can **override a single week** (holiday weeks, etc.)
  without changing the season defaults.
- `tiebreaker_game` — the game whose total points decide weekly ties: the **last game of the week
  by kickoff** (the later game on a Monday doubleheader). Set automatically when the week is
  published and re-checked by `sync_schedule` if kickoff times change, **until `picks_lock_at`**.
  After that it is frozen: if a game is postponed later, it must not become (or stop being) the
  tiebreaker game. The commissioner can override it (audited).
- `status` — `scheduled → published → in_progress → final`. A week becomes `final` only when
  **every** game in it is final, so a postponed game holds the week (and its weekly prize) open.
  The UI shows such a week as "provisional".

### Game
- `kickoff_at` — timezone-aware UTC datetime.
- `status` — `scheduled | in_progress | final | postponed | cancelled`.
- A postponed game keeps its `week` and gets a new `kickoff_at` when it's rescheduled. Its
  **lock time does not move**. When `sync_schedule` first sees a game postponed, it saves the
  previous kickoff in `postponed_from`, and the lock uses that. Ordinary schedule changes before
  lock (flexing, a Saturday game added) don't set `postponed_from`, so they move the lock normally.
- `external_id` — ID in the schedule/score feed, for idempotent upserts.

**Lock time (derived, never stored):**
```python
def lock_at(game, league_week) -> datetime:
    kickoff = game.postponed_from or game.kickoff_at   # postponement never reopens picks
    return min(kickoff, league_week.picks_lock_at)
```

### Spread
- Unique `(league_season, game)`.
- `home_line` — the locked line from the **home team's perspective** (e.g., `-3.5` = home favored by 3.5).
  The away line is always `-home_line`. Storing one number avoids inconsistent pairs.
- **Half-point only:** DB check constraint `abs(home_line * 2) % 2 = 1` (i.e., the value ends in `.5`).
  Pushes are therefore impossible.
- `feed_line` — the raw value from the feed before half-point normalization (may be whole), kept for transparency.
- `source` — `the-odds-api:median`, or `manual`. `book_count` — how many sportsbooks went into the median.
- `overridden` — true if the commissioner changed it; the before/after is recorded in `AuditEvent`.

### Pick
- Unique `(membership, game)` — one pick per member per game.
- **One best bet per member per week**: partial unique index
  `UNIQUE (membership_id, week_id) WHERE is_best_bet`. (`week_id` is denormalized from `Game` so the
  DB can enforce this.)
- `team` must be one of the game's two teams.
- Create/update/delete allowed only while the league week is `published` and `now < lock_at(game)`.
  Moving the best bet requires **both** the old and new games to be unlocked.
- A missing pick is simply **no row**. It earns 0 points and has no effect on prize eligibility.
  Never create placeholder picks for missed games.

### WeeklyEntry
- Unique `(membership, league_week)`.
- `mnf_total_guess` — non-negative integer, nullable (missed guess); editable until `league_week.picks_lock_at`.

### LeagueSeason.rules (JSON)
Remaining rule knobs, so future rule changes are config rather than code:
```json
{
  "pick_points": 1,
  "best_bet_points": 3,
  "weekly_winner_metric": "points",
  "weekly_tiebreakers": ["last_game_total_closest"],
  "weekly_unresolved_tie": "split",
  "season_points_tie": "split",
  "best_bet_tie": "split",
  "spread_source": "median_us_books",
  "half_point_rounding": "favorite_gives_more"
}
```

## 3. Scoring — computed, not stored

Results are derived from `Pick + Game final score + Spread`, never typed in.

```python
def ats_result(pick, spread) -> Literal["win", "loss", "pending"]:
    game = pick.game
    if game.status != "final":
        return "pending"
    margin = game.home_score - game.away_score + spread.home_line   # home team ATS margin
    if pick.team_id == game.away_team_id:
        margin = -margin
    return "win" if margin > 0 else "loss"   # never 0: lines are always x.5

def points(pick, spread, rules) -> int:
    if ats_result(pick, spread) != "win":
        return 0
    return rules["best_bet_points"] if pick.is_best_bet else rules["pick_points"]
```

**Weekly winner(s)** — returns a *list*, because the prize can be split:

```python
def weekly_winners(league_week) -> list[Membership]:
    totals = {m: week_points(m, league_week) for m in active_members}   # 0 if no picks at all
    best = max(totals.values())
    leaders = [m for m, pts in totals.items() if pts == best]
    if len(leaders) == 1:
        return leaders

    actual = tiebreaker_game.home_score + tiebreaker_game.away_score
    def distance(m):                       # missed guess = infinitely far
        guess = entry_for(m, league_week).mnf_total_guess
        return abs(guess - actual) if guess is not None else math.inf

    closest = min(distance(m) for m in leaders)
    return [m for m in leaders if distance(m) == closest]   # 2+ → split the prize
```

Members who missed picks are included like everyone else; missed games just contribute 0.
`weekly_winners` is only final once the league week is `final` (every game played, including any
postponed game). Until then, the same function gives the *provisional* leaders.

**Season prizes** (points champion, best bet champion) work the same way: everyone tied for first
is a winner and they split the prize. There is no tiebreaker.
The weekly results page shows every winner, and a "split N ways" label when there's more than one.

Leaderboards are aggregate SQL queries over picks joined to final games (annotated with a
`CASE` expression for the result). At ~50 members × 272 games ≈ 14k picks per season, this is
trivially fast; no materialized standings table needed. If it ever becomes slow, add a
`WeeklyResult(membership, league_week, correct, best_bet_correct, points)` cache table rebuilt
whenever a game goes final.

## 4. Visibility rule

A member may see another member's pick for a game only if `now >= lock_at(game)`. Likewise,
other members' MNF guesses are visible only after `picks_lock_at`. Implemented in single queryset
methods (`Pick.objects.visible_to(user)`, etc.) used by every view, so no template can
accidentally leak picks.
