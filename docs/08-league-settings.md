# 08 — League Settings

The goal is to make as much as practical **configurable by the commissioner**, modeled on
OfficePoolStop's manager settings (see [07](07-officepoolstop-comparison.md)). Each setting's
default is the rule our league actually plays, so a new league season works with no setup.

**Deliberately not configurable:** tie handling. Ties for any prize go to the tiebreaker guess (weekly
prize only) and then **split** among everyone still tied. There's no strength-of-victory or
win-percentage chain like OPS has.

## 1. Settings catalog

**Phase:** *MVP* = built for launch. *Later* = the data model supports it now, but the UI and logic
come after launch.

### 1.1 Picks and games
| Setting | Options | Default | Phase |
|---------|---------|---------|-------|
| `pick_type` | `against_spread`, `straight_up` | `against_spread` | MVP |
| `game_selection` | `all_games`, `commissioner_slate` (commissioner chooses the week's games) | `all_games` | Later |
| `points_per_win` | integer ≥ 1 | 1 | MVP |
| `missed_pick_points` | always 0; there is no setting | 0 | — |

### 1.2 Best bet (OPS "key games")
| Setting | Options | Default | Phase |
|---------|---------|---------|-------|
| `best_bets_per_week` | 0–5 (0 disables) | 1 | MVP |
| `best_bet_bonus` | extra points on top of `points_per_win` | 2 (so a win = 3) | MVP |
| `best_bet_required` | yes / no (UI nags if missing; missing is still forfeited) | no | MVP |
| `best_bet_team_once_per_season` | each team can be a best bet only once per season (OPS 2026 "season-limited key games") | off | Later |

### 1.3 Lines
| Setting | Options | Default | Phase |
|---------|---------|---------|-------|
| `line_mode` | `fixed_at_lock` (snapshot at spread lock), `variable` (each pick keeps the line when it was made), `closing` (line at kickoff) | `fixed_at_lock` | MVP: fixed; Later: variable, closing |
| `spread_lock_weekday` / `spread_lock_time` | any weekday/time | Tue 12:00 | MVP |
| `line_source` | `median_us_books`, or a specific sportsbook | `median_us_books` | MVP |
| `half_point_lines` | on: every line forced to x.5, so no pushes; off: lines as published, pushes possible | on | MVP |
| `half_point_rounding` | `favorite_gives` (`-3 → -3.5`), `favorite_gets` (`-3 → -2.5`) | `favorite_gives` | MVP |
| `push_scoring` | used only when `half_point_lines` is off: `half_points`, `loss`, `win` | `half_points` | MVP |
| `off_line_handling` | when a game has no line at spread lock: `unpickable_until_posted`, `hold_week` (week waits for commissioner) | `unpickable_until_posted` | MVP |
| `off_line_fallback` | if still no line at the game's lock: `favorite_minus_half`, `pickem_straight_up`, `void` | `favorite_minus_half` | MVP |

### 1.4 Deadlines and locks
| Setting | Options | Default | Phase |
|---------|---------|---------|-------|
| `picks_lock_weekday` / `picks_lock_time` | weekly hard deadline | Sun 10:00 | MVP |
| `game_lock_offset_minutes` | lock each game N minutes before kickoff | 0 | MVP |
| `grace_period_hours` | edits allowed only for N hours after a member first submits; blank = off | off | Later |
| `pick_visibility` | `at_game_lock` (each game revealed when it locks), `at_weekly_deadline` | `at_game_lock` | MVP |
| `future_week_picks` | allow picks for weeks whose lines are already locked ahead of time | off | Later |

A game's lock is always `min(kickoff − offset, weekly deadline)`. A pick can never be made after
kickoff, whatever the settings.

### 1.5 Missed picks
| Setting | Options | Default | Phase |
|---------|---------|---------|-------|
| `autopick` | `off`, `random`, `home`, `favorite`, `underdog` | `off` | Later |
| `autopick_max_weeks` | weeks per season a member can be auto-picked | 0 | Later |
| `autopick_tiebreaker_guess` | guess used for auto-picked weeks | 40 | Later |

### 1.6 Tiebreaker
| Setting | Options | Default | Phase |
|---------|---------|---------|-------|
| `tiebreaker_game` | `last_game_of_week`, `commissioner_selects` | `last_game_of_week` | MVP |
| `tiebreaker_type` | `total_points`, `margin_of_victory` | `total_points` | MVP |
| *Unresolved ties* | **always split**; not a setting | split | — |

### 1.7 Scoring extras (OPS bonuses)
| Setting | Options | Default | Phase |
|---------|---------|---------|-------|
| `underdog_outright_bonus` | extra points when the picked underdog wins outright | 0 (off) | Later |
| `tiebreaker_exact_bonus` | extra points for guessing the tiebreaker exactly | 0 (off) | Later |
| `over_under_points` | points for an optional over/under pick per game (needs a totals feed) | 0 (off) | Later |
| `drop_worst_week` | season total excludes each member's lowest week (OPS "bye week") | off | Later |

### 1.8 Prizes (record-keeping only)
| Setting | Options | Default | Phase |
|---------|---------|---------|-------|
| `weekly_prize` | on/off; metric `points` or `wins` | on, `points` | MVP |
| `season_points_prize` | on/off; number of paid places | on, 1 | MVP |
| `best_bet_prize` | on/off; number of paid places | on, 1 | MVP |
| `prize_amounts` | dollar amount per prize/place, for display | blank | Later |

### 1.9 Schedule and notifications
| Setting | Options | Default | Phase |
|---------|---------|---------|-------|
| `timezone` | league timezone for settings and default display | `America/Los_Angeles` | MVP |
| `reminder_times` | list of (weekday, time) | Thu 12:00, Sun 08:00 | MVP |
| `season_type` | `regular_season`; `include_playoffs` later | `regular_season` | Later |

## 2. How settings are stored

- A typed **`LeagueSettings`** model, one-to-one with `LeagueSeason`, with a real column per setting
  (not a JSON blob), so Django validates them and the commissioner gets a generated settings form.
- Settings are copied forward when a new season is created.
- Every change is recorded in `AuditEvent`.

## 3. Changing settings mid-season

Standings are computed from picks and scores (see [04 §3](04-data-model.md)), so a scoring setting
would apply retroactively to every week if it were edited in place. To keep it predictable:

| Kind of setting | When a change takes effect |
|-----------------|-------------------------------|
| **Lock and schedule** (spread lock, weekly deadline, reminders) | Weeks not yet published. Already-created `LeagueWeek` rows keep their times unless edited individually. |
| **Line settings** (`line_mode`, source, half-point options) | Weeks whose spreads haven't locked yet. Each locked `Spread` records how it was produced. |
| **Scoring settings** (points, best bet bonus, push scoring, extras) | **Locked once week 1 is published.** Changing one requires an explicit "apply to the whole season" confirmation and recalculates standings. |
| **Prizes / display** | Immediately |

## 4. Impact on other docs
- [04 Data Model](04-data-model.md): `LeagueSettings` replaces the `rules` JSON; `Pick.line`; `Spread.kind`.
- [03 Architecture](03-architecture-and-hosting.md): line refresh job for `variable`/`closing` modes and OFF lines.
- [05 Data Sources](05-data-sources.md): per-book line selection and Odds API usage under the line modes.
