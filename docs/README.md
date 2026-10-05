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

## Decision log

Short record of decisions made so far. Add a row whenever something is settled.

| Date | Decision | Doc |
|------|----------|-----|
| 2026-10-05 | Python / Django monolith with server-rendered templates + HTMX (no SPA) | [02](02-tech-stack.md) |
| 2026-10-05 | PostgreSQL as the database | [02](02-tech-stack.md) |
| 2026-10-05 | Spreads snapshotted once per week at a configured lock time; commissioner can override | [01](01-product-requirements.md), [05](05-data-sources.md) |
| 2026-10-05 | Standings are computed from picks + final scores, never hand-edited | [04](04-data-model.md) |
| 2026-10-05 | Host on a managed PaaS (Render recommended) with managed Postgres and cron jobs | [03](03-architecture-and-hosting.md) |
| 2026-10-05 | League timezone is Pacific (`America/Los_Angeles`); storage in UTC | [01](01-product-requirements.md) |
| 2026-10-05 | Pick lock: games before Sunday 10:00 AM PT lock at their own kickoff; all others lock Sunday 10:00 AM PT (configurable) | [01](01-product-requirements.md), [04](04-data-model.md) |
| 2026-10-05 | Spread lock is configurable per league season; default Tuesday 12:00 PM PT | [01](01-product-requirements.md), [03](03-architecture-and-hosting.md), [04](04-data-model.md) |
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
| 2026-10-05 | `.gitignore` added; local credential files (`Projectscreds.txt`, `.env`) are never committed | — |

## Status

Design phase. No application code yet.
