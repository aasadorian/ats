# 02 — Tech Stack

## Recommendation (summary)

| Layer | Choice |
|-------|--------|
| Language | Python 3.13 |
| Web framework | Django 5.2 LTS |
| Frontend | Django templates + **HTMX** + Alpine.js (small sprinkles) |
| Styling | Tailwind CSS (via `django-tailwind-cli`, no Node required) |
| Database | PostgreSQL 16+ |
| Auth | `django-allauth` (email/password, magic links, optional Google) |
| Scheduled jobs | Django management commands run by platform cron |
| Email | Transactional provider (Postmark, Resend, or SES) via `django-anymail` |
| HTTP client | `httpx` |
| Static files | WhiteNoise |
| App server | Gunicorn |
| Dependency mgmt | `uv` |
| Lint/format | Ruff |
| Tests | pytest + pytest-django, `factory_boy`, `time-machine` for clock control |
| Errors/monitoring | Sentry (free tier) + an uptime ping |
| CI | GitHub Actions (lint + tests on PR, deploy on merge to `main`) |

## Development environment

- **IDE:** PyCharm (it has first-class Django support: run configs, template debugging, `uv` interpreters).
- **Python:** installed and pinned by `uv` (`.python-version` in the repo), so the version is the
  same in PyCharm, the terminal, CI and production. Point PyCharm's interpreter at the project's
  `.venv` created by `uv sync`.
- **Local Postgres:** Docker container (or a native Windows install if Docker isn't wanted).
- **OS:** Windows for development; production runs Linux containers. Avoid OS-specific paths in code.

## Why Django

This app is a classic CRUD-plus-business-rules site: users, a schedule, picks, a scoring
function, leaderboards, and a commissioner back office. Django fits that shape nearly perfectly:

- **Django admin** gives the commissioner/developer a full back office for free on day one
  (fix a score, edit a spread, deactivate a member) before custom screens exist.
- **ORM + migrations + auth + forms + email + timezone support** are built in. Timezone-aware
  datetimes matter a lot here (locks at kickoff).
- Python is your strongest language, so velocity and long-term maintainability are highest.
- Mature, boring, LTS releases — appropriate for something that should run unattended each season.

### Alternatives considered

| Option | Verdict |
|--------|---------|
| **FastAPI + React/Next.js** | Two codebases, an API layer, and auth plumbing for no real benefit at this scale. More to maintain. |
| **Next.js / full-stack TypeScript** | Great for highly interactive UIs; not your strongest language, and we'd rebuild auth/admin by hand. |
| **Flask** | Viable, but we'd assemble admin, auth, migrations ourselves — Django already includes them. |
| **Rails / Laravel** | Same category as Django; no reason to leave Python. |
| **No-code (Airtable/Sheets + forms)** | Can't enforce per-game locks or hide picks reliably. |

## Why HTMX instead of a SPA

The interactive parts are small: tapping a pick, toggling a best bet, refreshing scores.
HTMX lets a button POST a pick and swap in the updated row without writing a JavaScript app.
Everything stays server-rendered, so all lock/validation logic lives in one place (Python).
Live scores can poll with `hx-trigger="every 60s"` during game windows — no websockets needed.

## Why PostgreSQL

Managed Postgres is cheap and universally available on PaaS hosts, supports the constraints we
need (e.g., partial unique index for "one best bet per member per week"), and handles window
functions for leaderboard ranking. SQLite would technically work at this scale, but concurrent
writes at Sunday kickoff and PaaS ephemeral disks make Postgres the safer default.

## Background / scheduled work

No Celery/Redis. The workload is a handful of periodic jobs (fetch spreads weekly, poll scores
every few minutes on game days, send reminders). These are plain management commands:

```
python manage.py sync_schedule --season 2027
python manage.py lock_spreads --week current
python manage.py sync_scores
python manage.py send_reminders
```

Triggered by the host's cron feature (see [03](03-architecture-and-hosting.md)). Each command
is idempotent so a retry or double-run is harmless. If we ever outgrow this, `django-q2` or
Celery can be added without restructuring.

## Project layout (proposed)

```
ats/
├── docs/
├── pyproject.toml
├── manage.py
├── config/                # settings (base/dev/prod), urls, wsgi
├── apps/
│   ├── accounts/          # custom user, profile, invites, allauth config (see 09)
│   ├── leagues/           # league, season, membership, rules config
│   ├── nfl/               # team, week, game, spread; feed clients
│   ├── picks/             # pick model, pick-making views, lock logic
│   ├── standings/         # scoring + leaderboard queries/views
│   ├── commissioner/      # override screens, activity log views
│   └── activity/          # ActivityEvent model, record_event(), feeds (see 10)
├── templates/
├── static/
└── tests/
```
