# 12 — Roadmap

Build order. Each milestone ends with working, tested software committed to `main`.

| # | Milestone | Scope | Outcome | Status |
|---|-----------|-------|---------|--------|
| 0 | **Skeleton** | `uv` project, Django 5.2 with split settings, custom email `User` model, allauth login (signup closed), Ruff / mypy / djLint / pytest / pre-commit / no-emoji check, GitHub Actions CI with Postgres, health endpoint, setup docs | `runserver` works; every commit is checked | Done (2026-10-06) |
| 1 | **NFL data** | `Team`, `Season`, `Week`, `Game`; ESPN schedule client; `sync_schedule` command | Real 2026 schedule in the database | Done (2026-10-06) |
| 2 | **Leagues and members** | `League`, `LeagueSeason`, `LeagueSettings`, `LeagueWeek`, `Membership`, `Invite` and invite signup; `ActivityEvent` and `record_event()`; MFA for commissioners | A commissioner can invite people who sign up | Done (2026-10-06) |
| 3 | **Lines** | Odds API client, median line, half-point normalization, `lock_spreads`, OFF / void handling, commissioner line review and override | Locked lines every Tuesday at 3 AM PT | Next |
| 4 | **Picks** | Pick sheet (HTMX), best bet, tiebreaker guess, per-game and weekly locks, visibility rules | Members can play a week | |
| 5 | **Scoring and standings** | `sync_scores`, grading, weekly winners with splits, season standings, best bet standings, postponed games | Full league loop | |
| 6 | **Launch prep** | Reminders and email provider, commissioner screens, activity log views, Render deployment, backups and monitoring | Soft launch alongside OfficePoolStop | |
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
