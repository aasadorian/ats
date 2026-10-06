# 12 — Roadmap

Build order. Each milestone ends with working, tested software committed to `main`.

| # | Milestone | Scope | Outcome | Status |
|---|-----------|-------|---------|--------|
| 0 | **Skeleton** | `uv` project, Django 5.2 with split settings, custom email `User` model, allauth login (signup closed), Ruff / mypy / djLint / pytest / pre-commit / no-emoji check, GitHub Actions CI with Postgres, health endpoint, setup docs | `runserver` works; every commit is checked | Done (2026-10-06) |
| 1 | **NFL data** | `Team`, `Season`, `Week`, `Game`; ESPN schedule client; `sync_schedule` command | Real 2026 schedule in the database | Next |
| 2 | **Leagues and members** | `League`, `LeagueSeason`, `LeagueSettings`, `LeagueWeek`, `Membership`, `Invite` and invite signup; `ActivityEvent` and `record_event()`; MFA for commissioners | A commissioner can invite people who sign up | |
| 3 | **Lines** | Odds API client, median line, half-point normalization, `lock_spreads`, OFF / void handling, commissioner line review and override | Locked lines every Tuesday at 3 AM PT | |
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
