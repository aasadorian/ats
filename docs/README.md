# ATS Pick'em — Design Docs

Design documentation for a self-hosted replacement for officepoolstop.com: a season-long
NFL pick'em league where every member picks **every regular-season game against the spread**,
with one weekly **best bet** worth 3 points.

## Documents

| # | Doc | What it covers |
|---|-----|----------------|
| 01 | [Product Requirements](01-product-requirements.md) | League rules, scoring, prizes, user roles, feature list, MVP vs. later |
| 02 | [Tech Stack](02-tech-stack.md) | Language/framework choices and why |
| 03 | [Architecture & Hosting](03-architecture-and-hosting.md) | System components, weekly lifecycle, scheduled jobs, deployment, cost |
| 04 | [Data Model](04-data-model.md) | Entities, relationships, constraints, scoring computation |
| 05 | [External Data Sources](05-data-sources.md) | Where schedules, spreads and scores come from; fallbacks |
| 06 | [Open Questions](06-open-questions.md) | Rule and product decisions still to be made |
| 07 | [OfficePoolStop Comparison](07-officepoolstop-comparison.md) | Where our rules and features differ from the site we're replacing |
| 08 | [League Settings](08-league-settings.md) | Every commissioner-configurable rule, defaults, MVP vs. Later, mid-season change rules |
| 09 | [User Management](09-user-management.md) | Accounts, login, invites, roles and permissions, member lifecycle, account security |
| 10 | [Activity Log](10-activity-log.md) | Append-only log of lines, picks, scores, settings, membership and security events; who sees what |
| 11 | [Coding Standards](11-coding-standards.md) | PEP 8 + Django style + Google guide as reference; Ruff/mypy enforcement; minimal comments; no emojis |
| 12 | [Roadmap](12-roadmap.md) | Build milestones and status |
| ADR | [Architecture Decision Records](adr/README.md) | Major technical decisions with options considered (e.g., [0001 Django](adr/0001-web-framework-django.md)) |

## Decision log

Short record of decisions made so far. Add a row whenever something is settled.

| Date | Decision | Doc |
|------|----------|-----|
| 2026-10-05 | Python / Django monolith with server-rendered templates + HTMX (no SPA) | [02](02-tech-stack.md), [ADR 0001](adr/0001-web-framework-django.md) |
| 2026-10-05 | PostgreSQL as the database | [02](02-tech-stack.md) |
| 2026-10-05 | Spreads snapshotted once per week at a configured lock time; commissioner can override | [01](01-product-requirements.md), [05](05-data-sources.md) |
| 2026-10-05 | Standings are computed from picks + final scores, never hand-edited | [04](04-data-model.md) |
| 2026-10-05 | Host on a managed PaaS (Render recommended) with managed Postgres and cron jobs | [03](03-architecture-and-hosting.md) |
| 2026-10-05 | League timezone is Pacific (`America/Los_Angeles`); storage in UTC | [01](01-product-requirements.md) |
| 2026-10-05 | Pick lock: games before Sunday 10:00 AM PT lock at their own kickoff; all others lock Sunday 10:00 AM PT (configurable) | [01](01-product-requirements.md), [04](04-data-model.md) |
| 2026-10-05 | Spread lock is configurable per league season; default Tuesday 12:00 PM PT (superseded below) | [01](01-product-requirements.md), [03](03-architecture-and-hosting.md), [04](04-data-model.md) |
| 2026-10-05 | All lines are half points, so pushes are impossible (enforced by a DB constraint) | [01](01-product-requirements.md), [04](04-data-model.md), [05](05-data-sources.md) |
| 2026-10-05 | Weekly winner = most points (best bet = 3); tiebreaker = closest guess of Monday night game total points | [01](01-product-requirements.md), [04](04-data-model.md) |
| 2026-10-05 | Lock settings and locked spreads are per league (`LeagueSeason`/`LeagueWeek`), with per-week overrides | [04](04-data-model.md) |
| 2026-10-05 | Development in PyCharm; Python toolchain managed with `uv` | [02](02-tech-stack.md) |
| 2026-10-05 | Whole-number lines: the favorite gives the half point (`-3 → -3.5`); pick'em → moneyline favorite `-0.5` | [01](01-product-requirements.md), [05](05-data-sources.md) |
| 2026-10-05 | Weekly tiebreaker game = last game of the week by kickoff (later game of a Monday doubleheader) | [01](01-product-requirements.md), [04](04-data-model.md) |
| 2026-10-05 | Members equally close on the tiebreaker split the weekly prize | [01](01-product-requirements.md), [04](04-data-model.md) |
| 2026-10-05 | Missed picks earn 0 with no auto-pick and don't affect prize eligibility; a missed best bet is forfeited; a missed guess loses the tiebreak | [01](01-product-requirements.md), [04](04-data-model.md) |
| 2026-10-05 | Season points and best bet prize ties are split among everyone tied | [01](01-product-requirements.md), [04](04-data-model.md) |
| 2026-10-05 | Postponed games stay in their week and are scored (best bets included) when played; picks don't reopen; the weekly prize waits for them | [01](01-product-requirements.md), [04](04-data-model.md), [05](05-data-sources.md) |
| 2026-10-05 | Canonical spread = median line across US sportsbooks at lock time | [05](05-data-sources.md) |
| 2026-10-05 | Rules are commissioner-configurable, modeled on OfficePoolStop's manager settings; our league's rules are the defaults; typed `LeagueSettings` model replaces the `rules` JSON | [08](08-league-settings.md), [04](04-data-model.md) |
| 2026-10-05 | Ties left after the tiebreaker guess are always split (weekly and season); not configurable | [08](08-league-settings.md) |
| 2026-10-05 | Default spread lock changed to Tuesday 3:00 AM PT to match OfficePoolStop's opening-line capture | [01](01-product-requirements.md), [08](08-league-settings.md) |
| 2026-10-05 | OFF lines: game unpickable until a line appears; void for the week if no line by the first kickoff of the week (normally Thursday night) | [01](01-product-requirements.md), [04](04-data-model.md), [08](08-league-settings.md) |
| 2026-10-05 | User management on django-allauth: invite-only, custom email-based User model, Argon2 passwords with breached-password checks, MFA required for commissioners, league-scoped roles, soft-delete members | [09](09-user-management.md) |
| 2026-10-05 | Activity log: one append-only `ActivityEvent` table (replaces `AuditEvent`) for lines, picks, scores, settings, membership and security events; written in the same transaction as each change; pick events hidden from everyone, including the commissioner, until the game locks | [10](10-activity-log.md) |
| 2026-10-05 | Coding standards: PEP 8 / 257 / 484 enforced by Ruff and mypy (strict), Django coding style, Google Python Style Guide as tie-breaker and docstring format; minimal comments; no emojis anywhere in code | [11](11-coding-standards.md) |
| 2026-10-06 | Local development uses native PostgreSQL 17 on Windows; Python 3.13 managed by uv | [12](12-roadmap.md), [README](../README.md) |
| 2026-10-06 | Build order: skeleton, NFL data, leagues and members, lines, picks, scoring, launch prep | [12](12-roadmap.md) |
| 2026-10-06 | NFL weeks come from ESPN's season calendar; `Week.sunday` = last Sunday (Pacific) in the week window; type-checked admin via django-stubs-ext | [05](05-data-sources.md), [12](12-roadmap.md) |
| 2026-10-06 | Display names are unique across the whole site (case-insensitive), stricter than per-league | [09](09-user-management.md) |
| 2026-10-06 | Security events are recorded from auth-library signals (the one exception to service-layer logging) | [10](10-activity-log.md) |
| 2026-10-06 | Commissioner two-factor requirement is on by default and can be disabled only via the `COMMISSIONER_MFA_REQUIRED` environment setting | [12](12-roadmap.md) |
| 2026-10-06 | League settings are edited in Django admin until the commissioner settings page in milestone 6 | [12](12-roadmap.md) |
| 2026-10-06 | One `lock_spreads` job (every 15 min) handles weekly locks and OFF lines; OFF-line feed checks throttled to every 2 hours to stay within the Odds API free tier (2 credits per request) | [03](03-architecture-and-hosting.md), [05](05-data-sources.md) |
| 2026-10-06 | Raw Odds API responses are stored (`OddsSnapshot`) as evidence for every locked line | [05](05-data-sources.md) |
| 2026-10-05 | `.gitignore` added; local credential files (`Projectscreds.txt`, `.env`) are never committed | — |

## Status

Milestones 0-3 complete (skeleton, NFL data, leagues and members, lines); see [12 Roadmap](12-roadmap.md).
