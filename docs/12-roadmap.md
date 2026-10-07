# 12 — Roadmap

Build order. Each milestone ends with working, tested software committed to `main`.

| # | Milestone | Scope | Outcome | Status |
|---|-----------|-------|---------|--------|
| 0 | **Skeleton** | `uv` project, Django 5.2 with split settings, custom email `User` model, allauth login (signup closed), Ruff / mypy / djLint / pytest / pre-commit / no-emoji check, GitHub Actions CI with Postgres, health endpoint, setup docs | `runserver` works; every commit is checked | Done (2026-10-06) |
| 1 | **NFL data** | `Team`, `Season`, `Week`, `Game`; ESPN schedule client; `sync_schedule` command | Real 2026 schedule in the database | Done (2026-10-06) |
| 2 | **Leagues and members** | `League`, `LeagueSeason`, `LeagueSettings`, `LeagueWeek`, `Membership`, `Invite` and invite signup; `ActivityEvent` and `record_event()`; MFA for commissioners | A commissioner can invite people who sign up | Done (2026-10-06) |
| 3 | **Lines** | Odds API client, median line, half-point normalization, `lock_spreads`, OFF / void handling, commissioner line review and override | Locked lines every Tuesday at 3 AM PT | Done (2026-10-06); live feed untested until an API key is added |
| 4 | **Picks** | Pick sheet (HTMX), best bet, tiebreaker guess, per-game and weekly locks, visibility rules | Members can play a week | Done (2026-10-07) |
| 5 | **Scoring and standings** | `sync_scores`, grading, weekly winners with splits, season standings, best bet standings, postponed games | Full league loop | Done (2026-10-07) |
| 6 | **Launch prep** | Reminders and email provider, commissioner screens, activity log views, Render deployment, backups and monitoring | Soft launch alongside OfficePoolStop | Next |
| Later | Settings marked *Later* in [08](08-league-settings.md), history import, PWA, stats | | | |

## Milestone 0 notes
- **Local database:** native PostgreSQL 17 on Windows (chosen over Docker Desktop and SQLite).
- **Signup** is closed in the allauth adapter until invites are built in milestone 2. Use
  `createsuperuser` for local logins.
- **The Have I Been Pwned password check** ([09 §2.3](09-user-management.md)) comes with milestone 2,
  alongside the other account work.
- **The admin URL** comes from the `DJANGO_ADMIN_URL` environment variable, so production can use a
  non-default path ([09 §8](09-user-management.md)).

## Milestone 1 notes
- `uv run python manage.py sync_schedule --season 2026` loads all 18 weeks (272 games, 32 teams);
  `--week N` (repeatable) limits it. Re-running is safe: it only updates what changed.
- Postponement rule from [01 §2.4.1](01-product-requirements.md) is implemented in the sync: the
  first time a game is seen as postponed, its previous kickoff is saved in `postponed_from` and the
  game stays in its original week; flexed kickoffs move normally.
- The sync records game status; `home_score` / `away_score` exist on `Game` but are filled by
  `sync_scores` in milestone 5.
- Activity events (`game.rescheduled`, `game.postponed`) are written once the activity log exists
  (milestone 2); until then the sync logs them.

## Milestone 2 notes
- **Bootstrapping a league:** `create_league --name ... --slug ... --season 2026 --commissioner-email ...`
  (the commissioner's account must exist; use `createsuperuser` locally). It creates the commissioner
  membership, the season's settings with our defaults, and all 18 league weeks with lock times and
  tiebreaker games. `sync_schedule` keeps league weeks and tiebreaker games up to date afterwards.
- **Invites** work end to end: the commissioner's members page sends invites; new people sign up
  through the invite (email locked to the invite, verified by accepting it); existing users accept
  while signed in. Commissioners can resend, revoke, change roles, deactivate and reactivate, and a
  league always keeps at least one commissioner.
- **Two-factor login is required for commissioner pages** (`COMMISSIONER_MFA_REQUIRED`, on by
  default; can be turned off in a local `.env` for development).
- **Activity log** is live: league, invite, membership, tiebreaker-game, game reschedule/postponement
  and security events. On PostgreSQL a trigger makes the table append-only.
- **Deferred to milestone 6 (commissioner screens / launch prep):** in-app settings page with the
  mid-season change rules of [08 §3](08-league-settings.md) (settings are edited in Django admin
  until then), leaving a league, account deletion, notification preferences, security notification
  emails, the optional join link, and client-IP handling behind Render's proxy.

## Milestone 3 notes
- `uv run python manage.py lock_spreads` (run every 15 minutes in production) locks every league
  week whose spread lock time has passed and whose picks haven't locked, publishes it, and handles
  OFF games: posts their line when it appears (feed checked at most every 2 hours) and voids them at
  the first kickoff of the week. Weeks already past their pick deadline are never locked, so a league
  created mid-season starts with the current week.
- Commissioner **Review lines** page (`/leagues/<slug>/lines/`): each game's locked line, the raw feed
  median, book count (flagged under 3), status, and an override form (half-point lines only, reason
  required, recorded in the activity log). With `off_line_handling = hold_week`, the week publishes
  once the commissioner has entered every missing line.
- **Not yet verified against the live Odds API**: there is no `ODDS_API_KEY` yet. The client is
  built to the documented v4 format and tested with feed-shaped data; run `lock_spreads` once a key
  is in `.env` to confirm.
- **Known limitation:** the `favorite_minus_half` OFF fallback (not our default; ours is `void`)
  gives -0.5 to the home team, because a game with no spread usually has no moneyline either.
- Line-locked emails to the commissioner and "week open" emails to members come with notifications
  in milestone 6; until then the activity log and the review page show this.

## Milestone 4 notes
- **Pick sheet** (`/leagues/<slug>/picks/`): every game with both teams' lines; tap a team to pick,
  toggle best bet, clear a pick, and enter the tiebreaker guess. HTMX swaps the sheet in place; every
  action also works as a plain form post without JavaScript. Times show in the member's timezone.
- **Rules enforced in `apps/picks/services.py`:** week must be published; game must have a posted
  line; nothing changes after a game's lock (`min(kickoff, Sunday 10 AM PT)`, with the postponement
  rule); best bets limited per settings. With one best bet per week, starring another game
  **moves** the best bet, unless the current one is already locked. Clearing a pick clears its best
  bet. Attempts after lock are recorded (`pick.rejected_locked`).
- **Everyone's picks** grid (`/leagues/<slug>/picks/grid/`): picks are revealed per game as it locks
  (or all at the weekly deadline, per `pick_visibility`). Before that, a cell shows only *whether*
  the member has picked. Hidden picks are never sent to the browser: the selector drops them
  before the template sees them. Tiebreaker guesses are revealed at the weekly deadline.
- HTMX 2.0.4 is served from `static/vendor/` rather than a CDN.
- **Deferred to milestone 6:** commissioner entering picks for a member (the services already accept
  an `actor` and log it as a commissioner action), and the activity feed views. Pick events in the
  activity log include the team, so those views must apply the same visibility rule.

## Milestone 5 notes
- **Scores:** the ESPN parser now reads scores for games in progress or final. `sync_scores`
  (every 5 minutes) asks the feed only for weeks that have a game kicked off and not yet final, so
  it makes no requests outside game windows. A postponed game is fetched from the feed week that
  contains its new kickoff. It reuses the stored calendar instead of refetching it.
- **Grading** (`apps/standings/grading.py`): win/loss/push against the scoring line (fixed-at-lock
  line; the line at pick time in `variable` mode; no line for straight-up); best bet adds the bonus;
  push points per `push_scoring`; cancelled games and void lines score 0 for everyone. Closing-line
  mode scores like fixed-at-lock until it is built.
- **Weeks** move to *in progress* at first kickoff and *final* when every game is final or
  cancelled; a postponed game holds the week open. Going final records the weekly winners in the
  activity log.
- **Weekly winners:** highest points (or correct picks, per `weekly_prize_metric`), then closest
  tiebreaker guess, then split. While the tiebreaker game is unfinished, tied leaders are shown
  together as provisional. Members who were deactivated keep the weeks they played.
- **Pages:** *Standings* (season points with ranks that share ties, W-L-P, best bet record, weeks
  won, current points and best bet leaders, weekly winners) and *Week results* (each member's points,
  record, decided best bet, tiebreaker guesses after the deadline, and every game's line, score and
  cover). The pick sheet and picks grid now show scores and win/loss/push.
- **Deferred to milestone 6:** commissioner score corrections. These need a "score overridden" flag
  so the next feed sync doesn't overwrite them. Also deferred: dropping the worst week and the
  scoring extras (later-phase settings).
