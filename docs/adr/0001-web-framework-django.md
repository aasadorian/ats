# ADR 0001 — Use Django as the web framework

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-05 |
| **Deciders** | Andrew Asadorian (project owner), with design support from Claude |
| **Related** | [02 Tech Stack](../02-tech-stack.md), [04 Data Model](../04-data-model.md), [09 User Management](../09-user-management.md), [10 Activity Log](../10-activity-log.md) |

## Context

We're building a private replacement for OfficePoolStop's NFL against-the-spread pick'em pool
([01](../01-product-requirements.md)). The shape of the system is now well understood:

- **Mostly CRUD plus business rules:** users, leagues, a schedule, picks, locked lines, a scoring
  function and leaderboards.
- **Strict server-side rules:** per-game and weekly locks, pick secrecy until lock, best-bet limits.
  All of these must be enforced on the server, using timezone-correct datetimes.
- **A back office:** commissioner screens to override lines and scores, manage members, and change
  ~40 league settings ([08](../08-league-settings.md)).
- **Serious account handling:** invite-only signup, password reset, magic links, MFA for
  commissioners, rate limiting ([09](../09-user-management.md)).
- **An append-only activity log** written in the same transaction as every change ([10](../10-activity-log.md)).
- **Periodic jobs** (line lock, score sync, reminders), but no real-time requirements beyond refreshing
  scores every minute or so.
- **Small scale:** one league, 10–50 users, ~15k picks per season.
- **Small team:** one developer whose strongest language is **Python**, using PyCharm, maintaining
  this in spare time. It must run unattended for a whole season.

The question: **which framework (and overall application shape) should we build on?**

## Decision drivers

Weighted by how much each matters for this project:

| # | Driver | Weight |
|---|--------|--------|
| D1 | Developer productivity and long-term maintainability for a solo Python developer | 5 |
| D2 | Mature, secure **authentication** out of the box (invites, reset, MFA, rate limits) | 5 |
| D3 | **Back office** for commissioner and admin with little custom code | 4 |
| D4 | ORM, migrations, transactions and timezone handling for correct locks and the activity log | 4 |
| D5 | Few moving parts: one codebase, one deployable, cheap hosting | 4 |
| D6 | Stability: long-term support releases, a large ecosystem, low churn | 3 |
| D7 | Rich client-side interactivity | 1 |
| D8 | Raw performance and async throughput | 1 |

D7 and D8 are weighted low on purpose. The interactive surface is "tap a pick, star a best bet,
refresh scores", and the load is a few dozen users.

## Options considered

1. **Django** (+ server-rendered templates + HTMX)
2. **FastAPI** (+ a separate React/Next.js frontend, or FastAPI + Jinja/HTMX)
3. **Flask** (+ extensions: Flask-Login, Flask-Migrate, Flask-Admin, …)
4. **Litestar** (modern async Python framework)
5. **Next.js / full-stack TypeScript** (e.g., Next.js + Prisma + Auth.js)
6. **Ruby on Rails** / **Laravel** (batteries-included frameworks in other languages)
7. **No-code / low-code** (Google Sheets + Forms, Airtable, Retool)

## Evaluation

### Scoring
Scores are 1 (poor) to 5 (excellent), multiplied by each driver's weight. They're judgments, not
measurements; the reasoning behind each is below.

| Driver (weight) | Django | FastAPI + SPA | Flask | Litestar | Next.js (TS) | Rails / Laravel | No-code |
|-----------------|:------:|:-------------:|:-----:|:--------:|:------------:|:---------------:|:-------:|
| D1 Productivity, Python dev (5) | 5 | 3 | 4 | 3 | 2 | 2 | 3 |
| D2 Auth out of the box (5) | 5 | 2 | 3 | 2 | 3 | 5 | 1 |
| D3 Back office (4) | 5 | 1 | 3 | 1 | 1 | 3 | 3 |
| D4 ORM, migrations, time zones (4) | 5 | 3 | 4 | 3 | 4 | 5 | 1 |
| D5 Few moving parts (4) | 5 | 2 | 5 | 4 | 4 | 5 | 5 |
| D6 Stability / LTS (3) | 5 | 3 | 4 | 2 | 2 | 5 | 3 |
| D7 Client interactivity (1) | 3 | 5 | 3 | 3 | 5 | 3 | 1 |
| D8 Performance / async (1) | 3 | 5 | 3 | 5 | 4 | 3 | 1 |
| **Weighted total (max 135)** | **131** | **68** | **101** | **71** | **76** | **108** | **67** |

### Option notes

**1. Django — chosen**
- **Auth:** Django's auth plus `django-allauth` covers everything in [09](../09-user-management.md):
  email login, magic-link codes, password reset, email verification, TOTP/passkey MFA, rate
  limiting and social login. All of it is maintained and security-reviewed by others.
- **Back office:** the Django admin gives a working back office on day one (fix a score, edit a
  line, deactivate a member). We'll build friendlier commissioner screens later, but we're never blocked.
- **Data:** one ORM with migrations, `transaction.atomic()` for writing the activity log alongside
  each change, timezone-aware datetimes (`USE_TZ`), and Postgres features (partial indexes,
  check constraints, window functions for rankings).
- **Forms and settings:** `ModelForm` turns the typed `LeagueSettings` model into a validated settings page.
- **Jobs:** management commands are a natural fit for platform cron, so no extra worker
  infrastructure is needed.
- **Stability:** Django 5.2 is an LTS release with security support into 2028, and the project has
  ~20 years of track record.
- **Tooling:** first-class PyCharm support (run configs, template debugging, `manage.py` integration).
- **Trade-offs we accept:** heavier than micro-frameworks; its async support is partial (irrelevant
  at our scale); server-rendered UI is less slick than a single-page app (HTMX closes most of that gap).

**2. FastAPI (+ SPA)**
- Excellent for typed JSON APIs, with great performance and automatic OpenAPI docs.
- But we don't need a public API, and FastAPI has **no built-in auth, admin, migrations or ORM**.
  We'd assemble SQLAlchemy + Alembic + an auth library + an admin package, and write
  invites/reset/MFA largely ourselves. That is exactly the security-sensitive code we want to avoid
  owning.
- With an SPA it means **two codebases** (Python + TypeScript), an API contract to keep in sync,
  CORS/token handling, and two deployables.
- FastAPI + Jinja/HTMX removes the SPA but still leaves the auth/admin/migrations gap.

**3. Flask**
- Simple, flexible, and Python. A viable runner-up among the Python options.
- Everything Django bundles is an extension of uneven maturity (Flask-Login, Flask-Migrate,
  Flask-Admin, Flask-Security-Too). We'd be the integrator and maintainer of that combination.
- For a project this size, that's work with no benefit over Django.

**4. Litestar**
- Modern, fast and well designed, but a younger ecosystem with a smaller community, and the same
  "bring your own auth and admin" gap as FastAPI. Too much risk for something that must run
  unattended.

**5. Next.js / full-stack TypeScript**
- Strongest option for rich interactive UIs, and deploys easily to Vercel.
- But it isn't the developer's strongest language, the framework changes quickly (App Router,
  server actions, caching semantics), auth (Auth.js) needs more custom work for invites and MFA,
  and there's no admin. Background jobs need a separate service or vendor.

**6. Rails / Laravel**
- Same "batteries included" category as Django, and they score similarly on features. Rails
  especially has comparable auth (Devise / Rails 8 auth generator) and admin (ActiveAdmin).
- They lose only on D1: they mean learning a new language and ecosystem for no functional gain.
  If the developer were a Ruby or PHP expert, these would be equally good choices.

**7. No-code / low-code**
- Fast to start, but it **can't reliably enforce per-game locks, hide picks before kickoff, or keep
  an append-only log**. These are the core requirements, so it's ruled out.

## Decision

**Build a single Django 5.2 LTS application** with server-rendered templates, **HTMX** (plus a little
Alpine.js) for interactivity, PostgreSQL, `django-allauth` for accounts, and management commands run
by platform cron for scheduled jobs. Details are in [02 Tech Stack](../02-tech-stack.md).

## Consequences

**Positive**
- One language, one codebase, one deployable. Cheap to host (~$15–20/month) and easy to reason about.
- Security-critical pieces (passwords, sessions, CSRF, MFA, reset tokens) come from widely used,
  maintained libraries.
- The admin and `ModelForm` make the commissioner tooling and the ~40 league settings cheap to build.
- All lock and visibility rules live in Python on the server, enforced in one place.

**Negative / risks, and mitigations**
- *Server-rendered UI could feel less app-like.* → HTMX partial updates, a mobile-first layout,
  optional installable PWA. Revisit if users complain.
- *A future native mobile app would need an API.* → Add Django REST Framework or Django Ninja on top
  of the same service layer; business logic stays in services, not views, so it can be reused.
- *Django's async story is partial.* → Not needed: no websockets; live scores poll every ~60 s.
- *Django upgrades.* → Stay on LTS releases (5.2 → 6.2 in 2028) and keep dependencies few.

## Revisit if
- We need a public API or native mobile apps (add DRF/Ninja first; a framework change is unlikely to be needed).
- Real-time features (live chat, push score streaming) become core (Django Channels, or a small
  separate service).
- Scale grows to thousands of concurrent users across many leagues.
