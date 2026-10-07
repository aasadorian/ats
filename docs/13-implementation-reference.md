# 13 — Implementation Reference

This document describes the application **as built**, in enough detail that a new developer (or
a new Claude session) could rebuild it from the docs alone, or build a better version. The design
docs (01–12) explain *what* and *why*; this one explains *exactly how*: models, rules, algorithms,
commands, URLs, tooling, tests, and every bug found along the way.

Keep it current: every change to behavior updates this file in the same commit.

**Rebuild order:** follow the milestones in [12 Roadmap](12-roadmap.md). Each section below notes
the milestone that introduced it.

---

## 1. Stack and repository layout

| Layer | Choice (see [02](02-tech-stack.md), [ADR 0001](adr/0001-web-framework-django.md)) |
|-------|------|
| Runtime | Python 3.13, managed by `uv` (`.python-version` = `3.13`, `uv.lock` committed) |
| Framework | Django 5.2 LTS, server-rendered templates, HTMX 2.0.4 (vendored) |
| Database | PostgreSQL 17 (production, CI); tests also run on SQLite locally |
| Auth | django-allauth 65.x with `account`, `mfa`, `usersessions` |
| Other runtime deps | `psycopg[binary]`, `django-environ`, `whitenoise`, `argon2-cffi`, `django-htmx`, `httpx`, `django-stubs-ext`, `gunicorn` (non-Windows only) |
| Dev deps | `ruff`, `mypy`, `django-stubs[compatible-mypy]`, `pytest`, `pytest-django`, `factory-boy`, `time-machine`, `pre-commit`, `djlint` |

```
ats/
├── apps/
│   ├── accounts/    custom User, invite-aware allauth adapter, signup/profile/delete forms,
│   │                Pwned Passwords validator, security-event signals, request_user helper
│   ├── activity/    ActivityEvent, record_event(), request context, append-only trigger,
│   │                privacy maintenance (scrub, IP prune), activity pages
│   ├── core/        home page (your leagues), /health/
│   ├── leagues/     League, LeagueSeason, LeagueSettings, LeagueWeek, Membership, Invite;
│   │                lock-time math, invites, roles, settings changes, permission decorators
│   ├── lines/       Spread, OddsSnapshot; The Odds API client; half-point normalization;
│   │                weekly lock, OFF lines, commissioner review/override
│   ├── nfl/         Team, Season, Week, Game; ESPN client; schedule and score sync
│   ├── picks/       Pick, WeeklyEntry; pick rules; pick sheet and grid; commissioner entry
│   └── standings/   grading, week results, season standings, week status, score corrections
├── config/          settings (base, dev, test, prod), urls.py, wsgi.py
├── docs/            these documents
├── scripts/         check_no_emoji.py, setup_local_db.ps1
├── static/          css/base.css, vendor/htmx-2.0.4.min.js
├── templates/       base.html and per-app templates; email/*.txt
├── tests/           pytest suite, factories, fixtures (recorded ESPN JSON)
├── manage.py, pyproject.toml, uv.lock, .pre-commit-config.yaml, .github/workflows/ci.yml
├── .env.example     (real .env is git-ignored)
└── CLAUDE.md        rules for AI-assisted work
```

Each app follows the same layering ([11 §6](11-coding-standards.md)): `models.py`; `services.py`
(state changes, rules, transactions, activity events); `selectors.py` (read models, including
visibility); `views.py` (parse input, call a service/selector, render); `forms.py`; `urls.py`
(namespaced); `admin.py`; `management/commands/`.

---

## 2. Configuration

### 2.1 Environment variables (`.env`, read by django-environ; real env vars win)
| Variable | Default | Purpose |
|----------|---------|---------|
| `DJANGO_SECRET_KEY` | required | Django secret |
| `DATABASE_URL` | required | e.g. `postgres://ats:pw@localhost:5432/ats` |
| `DJANGO_ALLOWED_HOSTS` | `[]` (dev: localhost, 127.0.0.1) | comma list |
| `DJANGO_ADMIN_URL` | `admin/` | non-default admin path in production |
| `SITE_URL` | `http://localhost:8000` | absolute links in emails |
| `ODDS_API_KEY` | empty | The Odds API key; jobs fail cleanly without it |
| `COMMISSIONER_MFA_REQUIRED` | `true` | set false only for local development |
| `DB_CONN_MAX_AGE` | 60 | persistent DB connections |
| `DJANGO_CSRF_TRUSTED_ORIGINS`, `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL` | prod only | |

### 2.2 Settings modules
- `config/settings/base.py`: everything shared. Calls `django_stubs_ext.monkeypatch()` first so
  generic classes such as `admin.ModelAdmin[Team]` work at runtime.
- `dev.py`: `DEBUG=True`, console email backend.
- `test.py`: MD5 hasher (speed), locmem email, plain static storage, `WHITENOISE_AUTOREFRESH=True`
  (avoids the "No directory at staticfiles" warning), and **removes `PwnedPasswordValidator`** (no
  network in tests).
- `prod.py`: SSL redirect, HSTS 1 year with subdomains and preload, secure cookies, proxy SSL header.
- `manage.py` defaults to `config.settings.dev`; `wsgi.py` to `config.settings.prod`.

### 2.3 Key Django and allauth settings (base)
- `AUTH_USER_MODEL = "accounts.User"`; `TIME_ZONE = "America/Los_Angeles"`; `USE_TZ = True`.
- Password hashers: Argon2 first. Validators: user-attribute similarity on `email` and
  `display_name`, minimum length 10, common, numeric, `apps.accounts.validators.PwnedPasswordValidator`.
- allauth: `ACCOUNT_LOGIN_METHODS={"email"}`, `ACCOUNT_SIGNUP_FIELDS=["email*","password1*","password2*"]`,
  `ACCOUNT_USER_MODEL_USERNAME_FIELD=None`, `ACCOUNT_EMAIL_VERIFICATION="mandatory"`,
  `ACCOUNT_LOGIN_BY_CODE_ENABLED=True` (emailed one-time login codes), `ACCOUNT_PREVENT_ENUMERATION=True`,
  `ACCOUNT_SESSION_REMEMBER=None` (user chooses), `ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE=True`,
  `ACCOUNT_ADAPTER="apps.accounts.adapters.InviteOnlyAccountAdapter"`,
  `ACCOUNT_SIGNUP_FORM_CLASS="apps.accounts.forms.SignupDetailsForm"`,
  `MFA_SUPPORTED_TYPES=["totp","recovery_codes"]`.
- Sessions: 30-day cookie age, HttpOnly, SameSite Lax.
- Middleware order: Security, WhiteNoise, Session, Common, CSRF, Auth, Messages, Clickjacking,
  allauth `AccountMiddleware`, allauth `UserSessionsMiddleware`, `HtmxMiddleware`,
  `apps.activity.middleware.EventContextMiddleware`.
- Installed apps order matters only for migrations: allauth apps, `django_htmx`, then `accounts`,
  `core`, `nfl`, `activity`, `leagues`, `lines`, `picks`, `standings`.

---

## 3. Data model (exact)

Generated from the models; `null` means nullable, `->` is a foreign key. All datetimes are UTC.

### accounts.User (extends `AbstractUser`; `username`, `first_name`, `last_name` removed)
- `email` unique; **stored lowercase** (`save()` lowercases); DB constraint
  `accounts_user_email_ci_unique` = `UniqueConstraint(Lower("email"))`. `USERNAME_FIELD="email"`.
- `display_name` (40, blank allowed; unique case-insensitive across the site, enforced in forms).
- `timezone` (default `America/Los_Angeles`; validated against `zoneinfo.available_timezones()`).
- `__str__` returns `display_name or email`.
- Manager `EmailUserManager`: `create_user(email, password)`, `create_superuser(...)`.

### nfl
- **Team**: `external_id` unique (ESPN id), `abbreviation`, `location`, `name`;
  `display_name` property = `"{location} {name}"` (matches The Odds API names for all 32 teams).
- **Season**: `year` unique.
- **Week**: `season` ->, `number`, `starts_at`, `ends_at` (ESPN calendar window), `sunday` (date);
  unique (`season`, `number`).
- **Game**: `external_id` unique, `week` ->, `home_team` ->, `away_team` ->, `kickoff_at`,
  `kickoff_is_tbd`, `postponed_from` null, `status` (`scheduled|in_progress|final|postponed|cancelled`),
  `neutral_site`, `home_score` null, `away_score` null, `score_overridden` (commissioner
  correction; feed sync leaves score and status alone). Check constraint: home != away. Index
  (`week`, `kickoff_at`).

### leagues
- **League**: `name`, `slug` unique, `timezone` (default Pacific), `created_at`.
- **LeagueSeason**: `league` ->, `season` ->; unique pair.
- **LeagueSettings**: one-to-one with LeagueSeason. Every field, default and meaning is in
  [08](08-league-settings.md); exact list: `pick_type`, `game_selection`, `points_per_win`(1),
  `best_bets_per_week`(1, max 5), `best_bet_bonus`(2), `best_bet_required`, `best_bet_team_once_per_season`,
  `line_mode`(fixed_at_lock), `spread_lock_weekday`(Tue=1), `spread_lock_time`(03:00), `line_source`,
  `half_point_lines`(true), `half_point_rounding`(favorite_gives), `push_scoring`(half_points),
  `off_line_handling`(unpickable_until_posted), `off_line_cutoff`(first_kickoff_of_week),
  `off_line_fallback`(void), `picks_lock_weekday`(Sun=6), `picks_lock_time`(10:00),
  `game_lock_offset_minutes`(0), `grace_period_hours` null, `pick_visibility`(at_game_lock),
  `future_week_picks`, `autopick`(off), `autopick_max_weeks`(0), `autopick_tiebreaker_guess`(40),
  `tiebreaker_game`(last_game_of_week), `tiebreaker_type`(total_points), `underdog_outright_bonus`,
  `tiebreaker_exact_bonus`, `over_under_points`, `drop_worst_week`, `weekly_prize_enabled`,
  `weekly_prize_metric`(points), `season_points_prize_enabled`, `season_points_prize_places`(1),
  `best_bet_prize_enabled`, `best_bet_prize_places`(1), `prize_amounts`(JSON {}),
  `reminder_times` (JSON list of `{"weekday": int, "time": "HH:MM"}`; default Thu 12:00, Sun 08:00),
  `season_type`. Weekdays use Python numbering (Monday=0).
  `clean()` rejects settings where the spread lock would fall at or after the picks deadline
  (checked against a reference Sunday in UTC).
- **LeagueWeek**: `league_season` ->, `week` ->, `spreads_lock_at`, `picks_lock_at`,
  `tiebreaker_game` -> Game null, `status` (`scheduled|published|in_progress|final`); unique pair.
- **Membership**: `user` ->, `league` ->, `role` (`member|commissioner`), `is_active`, `joined_at`,
  `deactivated_at` null; unique (`user`, `league`). `is_commissioner` = active and commissioner.
- **Invite**: `league` ->, `email` (lowercase), `role`, `token_hash` unique (SHA-256 hex of the
  token), `invited_by` ->, `created_at`, `expires_at`, `accepted_at` null, `accepted_by` null,
  `revoked_at` null; check constraint: not both accepted and revoked. `InviteQuerySet.pending()` =
  not accepted, not revoked, not expired. `is_usable` property mirrors it.

### lines
- **Spread**: `league_season` ->, `game` ->, `kind` (`locked|closing`), `status` (`posted|off|void`),
  `home_line` Decimal(4,1) null (home team's perspective; away = -home), `feed_line` Decimal(5,2) null
  (raw median before normalization), `book_count`, `source` (`the-odds-api:median`, `the-odds-api`
  for OFF, `manual`, `fallback:<option>`), `locked_at` null, `overridden`. Unique
  (`league_season`, `game`, `kind`); check: status posted requires a line.
- **OddsSnapshot**: `fetched_at` (default now, but set to the job's clock), `source`, `payload` JSON
  (raw feed response; evidence for every locked line).

### picks
- **Pick**: `membership` ->, `game` ->, `week` -> (denormalized from game for fast per-week
  queries), `team` ->, `is_best_bet`, `home_line_at_pick` (the posted home line when saved; used
  for scoring only in `variable` mode), `created_at`, `updated_at`; unique (`membership`, `game`).
  A missed pick is **no row**.
- **WeeklyEntry**: `membership` ->, `league_week` ->, `tiebreaker_guess` null (0–200), `updated_at`;
  unique pair. Its row is also the **lock row** that serializes a member's pick changes per week.

### activity
- **ActivityEvent**: `occurred_at` (auto), `league` null, `league_week` null, `category`
  (`lines|picks|games|standings|settings|membership|security|notifications`), `event_type`,
  `actor_type` (`member|commissioner|admin|system`), `actor` null, `subject_user` null,
  `object_type`, `object_id`, `before` JSON null, `after` JSON null, `summary` (255),
  `source` (`web`, `job:<name>`, `command:<name>`, `shell`), `request_id` (32 hex), `ip_address`
  null (security events only). Indexes per [10](10-activity-log.md). Append-only (section 6.2).

---

## 4. Domain rules and algorithms

### 4.1 Lock times (`apps/leagues/schedule.py`)
```
spreads_lock_date(sunday, weekday) = the configured weekday in the 6 days before Sunday:
    d = sunday - 1 day;  d - ((d.weekday() - weekday) mod 7) days
picks_lock_date(sunday, weekday)  = the configured weekday from the Thursday before to the
    Wednesday after Sunday:  t = sunday - 3 days;  t + ((weekday - t.weekday()) mod 7) days
lock_times(...) = combine those dates with the configured times in the league timezone (zoneinfo,
    DST-aware) -> (spreads_lock_at, picks_lock_at)
game_lock_at(kickoff_at, postponed_from, picks_lock_at, offset) =
    min((postponed_from or kickoff_at) - offset minutes, picks_lock_at)
```
Defaults give Tue 03:00 PT and Sun 10:00 PT (2026-09-13 week: 10:00Z and 17:00Z; after DST ends,
11:00Z and 18:00Z). `Week.sunday` = the last Sunday (Pacific) inside ESPN's week window.

### 4.2 Schedule and score sync (`apps/nfl`)
- **ESPN request:** `GET https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard`
  with `seasontype=2&week=N&dates=YEAR`; httpx timeout 15 s, 2 retries. Errors raise `EspnFeedError`.
- **Weeks:** from `leagues[0].calendar`, the entry with `value == "2"` (regular season), its
  `entries` with numeric `value`; `startDate`/`endDate` parsed with `datetime.fromisoformat`
  (rejects naive timestamps).
- **Games:** `events[*]`: id, `date` (kickoff), competitors by `homeAway`, team `id`,
  `abbreviation`, `location`, `name`; `competitions[0].neutralSite`; TBD when `status.isTBDFlex` or
  `timeValid` is false.
- **Status map:** `STATUS_POSTPONED`→postponed, `STATUS_CANCELED`→cancelled, state `in`→in_progress,
  state `post` and `completed`→final, else scheduled.
- **Scores:** competitor `score` is a string; stored only when status is in_progress or final
  (ESPN reports `"0"` for scheduled games).
- **`sync_schedule(provider, season_year, weeks=None)`:** if specific weeks are requested and the
  season's weeks already exist, the calendar request is skipped and weeks come from the database.
  In one transaction: upsert season, weeks, teams (cached per run), games by `external_id`.
  For an existing game:
  1. If `score_overridden`, drop `status`, `home_score`, `away_score` from the update.
  2. **Postponement rule:** the first time the feed says postponed and `postponed_from` is empty,
     set `postponed_from = current kickoff_at` and record `game.postponed`. The game keeps its
     original week forever after; otherwise its week follows the feed.
  3. A kickoff change records `game.rescheduled`; a transition to final records `game.final`
     (unless overridden).
  4. Save only if something changed.
- **`weeks_with_live_games(season, now)`:** games with `kickoff_at <= now` and status scheduled,
  in_progress or postponed, mapped to the feed week whose window contains the kickoff (so a
  made-up postponed game is fetched from the week ESPN lists it in).
- **`sync_scores`:** returns `None` with zero requests if no week is live; otherwise
  `sync_schedule` for those weeks only.

### 4.3 Leagues, invites, roles (`apps/leagues/services.py`)
- `create_league(name, slug, commissioner, season_year)`: league, commissioner membership,
  `league.created` event, then `start_league_season`.
- `start_league_season(league, season)`: copies the most recent previous season's settings (clone
  with `pk=None`, `_state.adding=True`) or creates defaults; then `ensure_league_weeks`.
- `ensure_league_weeks`: creates missing LeagueWeeks with computed lock times, then
  `refresh_tiebreaker_games`.
- `refresh_tiebreaker_games(league_season, now)`: only for `last_game_of_week`. For weeks whose
  picks haven't locked **or that have no tiebreaker game yet**, set it to the last non-cancelled
  game by (`kickoff_at`, `external_id`) descending; record `tiebreaker_game.set/changed`.
- `refresh_league_weeks(season)`: called by `sync_schedule` command after every sync.
- Invites: token `secrets.token_urlsafe(32)`, only `sha256(token)` stored, 14-day expiry; inviting
  an email with a pending invite revokes the old one (event "replaced by a new invite"); inviting
  an active member raises `AlreadyMemberError`. Email sent with `transaction.on_commit`.
  `accept_invite` locks the invite row (`select_for_update`), requires usable and matching email,
  creates or reactivates the membership with the invite's role.
- `change_role`, `deactivate_membership`, `leave_league` refuse to remove the last active
  commissioner (`LastCommissionerError`, checked with `select_for_update`).
- **Settings changes** (`update_settings(settings, changes, actor, apply_to_season)`):
  scoring fields (`pick_type`, `points_per_win`, `best_bets_per_week`, `best_bet_bonus`,
  `push_scoring`, `weekly_prize_metric`) changed after any week left `scheduled` require
  `apply_to_season=True` (else `RetroactiveChangeError`); schedule fields recompute lock times for
  every still-`scheduled` week; `full_clean()`; `settings.changed` event with before/after.
- **Permissions** (`apps/leagues/permissions.py`): `@league_member_required` and
  `@commissioner_required` wrap views as `view(request, league, membership, **kwargs)`; non-members
  and non-commissioners get **404**; commissioners without MFA (when required) are redirected to
  `mfa_activate_totp`. Every object lookup is filtered by league.

### 4.4 Lines (`apps/lines`)
- **The Odds API:** `GET https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds` with
  `apiKey`, `regions=us`, `markets=spreads,h2h`, `oddsFormat=american`, `commenceTimeFrom/To`
  (the week window, UTC `YYYY-MM-DDTHH:MM:SSZ`). 2 credits per request. Logs the
  `x-requests-used/remaining` headers.
- **Parse:** per event, the home team's spread `point` from every bookmaker (Decimal from str);
  moneyline favorite = lower `median_low` American price (ties → unknown).
- **Normalization** (`normalize.py`): `median_line` = statistics median (can give quarters);
  `round_to_half` = nearest 0.5 with exact quarters away from zero; if half-point lines are on and
  the result is whole: 0 → -0.5 to the moneyline favorite (home if unknown), otherwise move half a
  point away from zero (`favorite_gives`) or toward zero (`favorite_gets`).
- **Matching:** by lowercase full name (`Team.display_name`); if the feed lists the teams reversed,
  negate the line and flip the favorite.
- **`lock_spreads(provider, now)`:** for each LeagueWeek with status scheduled, `spreads_lock_at <= now`
  and `picks_lock_at > now` (past weeks are never locked, so mid-season leagues start with the
  current week): one feed request per NFL week per run (`OddsCache`, which stores an
  `OddsSnapshot` with `fetched_at = now`); for each non-cancelled game without a locked spread,
  create posted (`line.locked`) or OFF (`line.off`); flag fewer than 3 books; then publish
  (`week.published`) unless `hold_week` and any game is OFF.
- **OFF lines** (`refresh_off_lines`, same job): cutoff = first non-cancelled kickoff of the week
  (or the game's own lock if configured). Past the cutoff apply the fallback: `void` (status void),
  `favorite_minus_half` (**home** -0.5; known limitation), `pickem_straight_up` (line 0). Before
  the cutoff, fetch at most every **2 hours** (`OFF_LINE_REFRESH_INTERVAL`, measured from the
  latest snapshot) and post a matched line (`line.posted_late`).
- **Override:** half-point required when `half_point_lines`; sets posted, `overridden`, `source=manual`;
  `line.overridden` with reason; may publish a held week.

### 4.5 Picks (`apps/picks`)
- `WeekContext.load(league_week)`: settings plus locked spreads by game; `lock_at(game)`,
  `is_locked`, `is_revealed` (at game lock, or at the weekly deadline per `pick_visibility`).
- **Guard order** (`_ensure_pickable`): membership active → game belongs to this league week →
  week status published or in_progress → not locked (else record `pick.rejected_locked` and raise
  `PickLockedError`) → posted spread exists (else "has no line yet").
- `save_pick`: team must be one of the two; under the entry lock create (`pick.made`) or change
  team (`pick.changed`) and store `home_line_at_pick`.
- `clear_pick`: deletes the row (and its best bet) → `pick.cleared`.
- `set_best_bet(on)`: limit 0 → error; requires an existing pick; under limit → set; at limit 1 →
  **move** from the previous game unless that game is locked; limit > 1 → "remove one first".
- `set_tiebreaker`: week open, before `picks_lock_at`, 0–200 or blank.
- Events name the actor; when a commissioner acts for a member the actor type is commissioner and
  the summary says "for <member>".
- **Selectors:** row state precedence `void` → `locked` → `not_open` → `off` → `open`. The grid
  never passes an unrevealed pick to templates (cell has only `has_pick`); own picks always
  visible; tiebreaker guesses revealed at the weekly deadline. Outcomes shown once graded.
- **Views:** POST endpoints return the `_sheet.html` partial when `HX-Request: true`, otherwise
  redirect to the sheet (no-JS fallback). Errors show inline in the partial.
- **Commissioner entry** (`member_picks`): reason required; normal lock rules apply; wraps the
  service calls and a `pick.entered_for_member` event in one transaction and emails the member on
  commit.

### 4.6 Grading and standings (`apps/standings`)
- `grade(pick, game, spread, settings)`: void if game cancelled or spread void; pending unless
  final with both scores; scoring line = 0 (straight up) / `home_line_at_pick` (variable) / locked
  `home_line`; `margin = home - away + line`, negated for the away pick; >0 win, <0 loss, 0 push.
- `points_for`: base = `points_per_win` (+ `best_bet_bonus` for a best bet); push per
  `push_scoring` (half points / win / 0). Points are `Decimal`.
- `week_results(league_week)`: participants = active members plus anyone with picks that week;
  ordered by the weekly metric (points, or wins where a best bet counts once). **Winners:** none if
  the top value is 0; single leader wins; tied leaders → closest tiebreaker guess
  (`abs(guess - actual)`, missing guess = infinity) once the tiebreaker game is final, equal
  distances split; if the tiebreaker game isn't final, all tied leaders are returned (provisional).
  `actual` = total points, or `abs(margin)` for margin-of-victory.
- `season_standings`: sums week results for weeks published/in progress/final; ranks by points with
  shared ranks ("1, 1, 3"); best-bet table by wins then fewest losses; a split week counts as a week
  won for each sharer; `is_complete` when every league week is final.
- `update_week_statuses(now)`: published → in_progress at first non-cancelled kickoff;
  in_progress → final when no game is outside final/cancelled (a postponed game holds the week);
  on final record `week.final` and `standings.weekly_winners`.
- **Score corrections:** `correct_score` sets scores, final, `score_overridden=True`
  (`game.score_corrected` with reason), then week statuses are re-evaluated; `restore_feed_score`
  clears the flag. Corrections apply to the global game, so every league sees them.

### 4.7 Activity (`apps/activity`)
- `EventContextMiddleware` and `event_context(source, ip)` set a context variable with a new
  `request_id`; outside any context, source is `shell`.
- `record_event(...)` derives the category from the event-type prefix (unknown prefixes raise),
  stores IP only for security events, and must be called inside the change's transaction.
- **Visibility** (`selectors.visible`): another member's `picks`-category event is redacted
  ("<member> updated their picks", no before/after) until that week's `picks_lock_at`, unless the
  viewer is the subject or the actor. Applied to the commissioner log and CSV too.
- **Pages:** league feed (lines, games, standings, settings categories plus joins and departures),
  "my activity" (my league events plus my security events), commissioner log with filters
  (member, week, category, event type, date range) and CSV export; 50 per page.
- **Privacy maintenance:** `maintenance()` opens a transaction and sets
  `SET LOCAL ats.activity_maintenance = 'on'` on PostgreSQL; `scrub_identity({old: new})` rewrites
  summaries and JSON snapshots with word-boundary, case-insensitive replacement;
  `prune_ip_addresses(now)` nulls IPs older than 90 days.

### 4.8 Accounts (`apps/accounts`)
- **Invite-only signup** (adapter): open only when the session holds a usable invite token
  (`invite_token`); `clean_email` requires the invited address; `save_user` accepts the invite and
  clears the token. The invite page stashes the email as verified
  (`adapter.stash_verified_email`), so allauth skips the verification email.
  `InviteSignupView` (mounted at `accounts/signup/` before allauth's URLs) pre-fills the email.
- `SignupDetailsForm` adds `display_name` (site-wide unique, case-insensitive).
- `PwnedPasswordValidator`: SHA-1 the password, send only the first 5 hex characters to
  `https://api.pwnedpasswords.com/range/{prefix}` (`Add-Padding: true`, 3 s timeout), reject if
  the suffix appears with a count > 0; network failure allows the password.
- Security events via signals (`signals.py`): login, failed login (email masked as `ab***@domain`),
  password changed/reset, email changed, MFA added/removed.
- Profile page: display name and timezone, links to allauth email, password, MFA and
  `usersessions` (sign out other devices). `delete_account`: records `account.deleted`, replaces
  email with `deleted-<id>@invalid.example` and name with `Former member #<id>`, unusable password,
  deactivates, deletes email addresses, authenticators and user sessions, deactivates memberships,
  then scrubs the old email and name from the activity log. Picks are kept. The form requires the
  password only if the account has one, plus typing `DELETE`.

---

## 5. URL map

| Path | Name | Access |
|------|------|--------|
| `/` | `core:home` | login |
| `/health/` | `core:health` | public (runs `SELECT 1`) |
| `/accounts/...` | allauth (login, logout, signup, password reset, email, `2fa/...`, sessions) | mixed |
| `/accounts/signup/` | `account_signup` (InviteSignupView) | invite in session |
| `/account/profile/`, `/account/delete/` | `accounts:profile`, `accounts:delete` | login |
| `/invites/<token>/` | `leagues:invite` | public |
| `/leagues/<slug>/` | `leagues:home` | member |
| `/leagues/<slug>/leave/` | `leagues:leave` | member |
| `/leagues/<slug>/members/` (+ `invites/<pk>/resend|revoke/`, `members/<pk>/role|deactivate|reactivate/`) | `leagues:members` etc. | commissioner |
| `/leagues/<slug>/settings/` | `leagues:settings` | commissioner |
| `/leagues/<slug>/lines/`, `/lines/<pk>/override/` | `lines:review`, `lines:override` | commissioner |
| `/leagues/<slug>/picks/` (+ `pick/`, `clear/`, `best-bet/`, `tiebreaker/`) | `picks:sheet` etc. | member |
| `/leagues/<slug>/picks/grid/` | `picks:grid` | member |
| `/leagues/<slug>/members/<pk>/picks/` | `picks:member_picks` | commissioner |
| `/leagues/<slug>/standings/`, `/standings/week/` | `standings:season`, `standings:week` | member |
| `/leagues/<slug>/scores/`, `/scores/<pk>/` | `standings:scores`, `standings:correct` | commissioner |
| `/leagues/<slug>/activity/`, `/activity/mine/` | `activity:feed`, `activity:mine` | member |
| `/leagues/<slug>/activity/log/` | `activity:log` (`?format=csv`) | commissioner |
| `/<DJANGO_ADMIN_URL>` | Django admin | superuser |

Weeks are selected with `?week=N` (or a `week` POST field); the default is the first week whose
window hasn't ended.

---

## 6. Jobs, database objects, operations

### 6.1 Management commands
| Command | Schedule (production) | What it does |
|---------|----------------------|--------------|
| `sync_schedule [--season Y] [--week N ...]` | daily | ESPN schedule sync, then league weeks and tiebreaker games refresh |
| `lock_spreads` | every 15 min | weekly line locks plus OFF-line posting/voiding |
| `sync_scores` | every 5 min | live-week score sync (no requests when idle), week statuses, weekly winners |
| `prune_activity_ips` | daily | null IPs older than 90 days |
| `create_league --name --slug --season --commissioner-email` | manual | bootstrap a league |

All jobs run inside `event_context("job:<name>")` and are idempotent. The current season is the
current year from March onward, otherwise the previous year.

### 6.2 Append-only trigger (migration `activity/0003_append_only.py`, PostgreSQL only)
```sql
CREATE OR REPLACE FUNCTION activity_event_append_only() RETURNS trigger AS $$
BEGIN
    IF current_setting('ats.activity_maintenance', true) = 'on' THEN
        RETURN COALESCE(NEW, OLD);
    END IF;
    RAISE EXCEPTION 'activity_activityevent is append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER activity_event_append_only BEFORE UPDATE OR DELETE ON activity_activityevent
FOR EACH ROW EXECUTE FUNCTION activity_event_append_only();
```
Installed with `RunPython` that checks `connection.vendor == "postgresql"` so SQLite test runs work.

### 6.3 Local setup
See `README.md`: install `uv`, PostgreSQL 17 (`winget install --id PostgreSQL.PostgreSQL.17` from an
elevated shell), copy `.env.example` to `.env`, run `scripts/setup_local_db.ps1` (creates the role
with `CREATEDB`, needed for the test database, and the database from `DATABASE_URL`), then
`uv sync`, `migrate`, `createsuperuser`, `pre-commit install`, `runserver`.

---

## 7. UI conventions
- `templates/base.html`: header with brand, Account link, sign-out POST form; messages list;
  loads `css/base.css` and `vendor/htmx-2.0.4.min.js` (deferred); `hx-headers` on `<body>` sends
  the CSRF token.
- Mobile-first CSS: game cards, two large team buttons per game (`.team`, `.selected`), best bet
  pill, outcome borders (win green, loss red, push grey), horizontally scrollable tables
  (`.table-wrap`).
- Times are rendered in the viewer's timezone (`{% timezone user.timezone %}`); lock times on
  commissioner pages in the league timezone.
- Shared partial `picks/_week_nav.html` (week select, auto-submits, `<noscript>` button).
- Template filter `line` (`apps/lines/templatetags/lines.py`): `-3.5`, `+7.5`, `PK`, `OFF`.
- No emojis anywhere; plain text markers ("BB" for a best bet in the grid).

---

## 8. Tooling and quality gates
- `pyproject.toml`: Ruff line length 88, target py313, excludes `**/migrations/*` and `docs`;
  rule sets `E W F I N UP B SIM DJ DTZ S PT T20 ERA RUF`; tests may use `assert` and literal
  passwords (`S101`, `S106`). mypy strict with the django-stubs plugin
  (`django_settings_module = config.settings.test`); `ignore_missing_imports` for allauth, environ,
  factory; `disallow_subclassing_any = false` for `apps.accounts.adapters` only (allauth is
  untyped). pytest uses `config.settings.test`. djLint profile django, indent 2.
- `.pre-commit-config.yaml`: standard hygiene hooks plus local `uv run` hooks for ruff format,
  ruff check, mypy, djLint and `scripts/check_no_emoji.py` (excludes `docs/`).
- `scripts/check_no_emoji.py`: scans files for code points in U+1F000–1FAFF, U+2600–27BF,
  U+2B00–2BFF, U+FE0F and U+200D.
- CI (`.github/workflows/ci.yml`, ubuntu with a `postgres:17` service): `uv sync --locked`,
  ruff format check, ruff check, mypy, djLint, emoji check over `git ls-files`,
  `makemigrations --check`, `check --deploy` with prod settings, pytest.

---

## 9. Tests
- Helpers: `tests/factories.py` (users, teams with real names, a two-week season with three games
  per week: SEA-NE Thursday, KC-BUF Sunday 17:00Z, DAL-NYG Sunday night, and `make_league`);
  `tests/world.py` (`build()` creates a league with locked week-1 lines and two members, plus time
  constants `LOCK_RUN`, `OPEN`, `THURSDAY_NIGHT`, `SUNDAY_LOCKED`, and `finish(game, home, away)`);
  `tests/odds.py` (`odds_event()` builds Odds-API-shaped events; `FakeOddsProvider` counts calls);
  `tests/conftest.py` (`user` fixture with a verified email; `world` fixture).
- Recorded ESPN JSON fixtures (trimmed real responses) in `tests/fixtures/espn/`.
- Time is controlled by passing `now=` to services and by `time_machine.travel` in view tests.
- Coverage by file: accounts, activity, lock schedule, leagues services and views, lines
  normalization/services/views, NFL feed and sync, picks, standings, commissioner tools.
  The append-only test is skipped on SQLite and runs in CI.

---

## 10. Bugs found and lessons learned

| # | Problem | Cause | Fix / lesson |
|---|---------|-------|--------------|
| 1 | `makemigrations` hung locally | No PostgreSQL installed; Django tried to connect | Generate migrations with `DATABASE_URL=sqlite:///...` (migrations are DB-agnostic) |
| 2 | Ruff reformatted Python snippets inside the docs | Ruff formats code blocks in Markdown | Exclude `docs` in `[tool.ruff]` |
| 3 | mypy: "class cannot subclass DefaultAccountAdapter (Any)" | allauth ships no type hints | Per-module `disallow_subclassing_any = false` in `pyproject.toml` instead of inline ignores |
| 4 | `TypeError: 'ModelAdmin' is not subscriptable` | Generic admin classes need runtime support | `django-stubs-ext` and `monkeypatch()` in base settings |
| 5 | `record_event` crashed without an object | Operator precedence in a conditional expression | Compute `object_type`/`object_id` in separate statements |
| 6 | League created mid-season had no tiebreaker games for past weeks | Refresh skipped weeks after their pick deadline | Also refresh any week whose tiebreaker game is still empty |
| 7 | Login test produced no login event | Mandatory email verification blocks unverified users | Test fixture creates a verified `EmailAddress` |
| 8 | OFF-line refresh would burn ~480 of 500 monthly Odds API credits | 15-minute job fetched every run while a game was OFF | Throttle OFF-line fetches to every 2 hours |
| 9 | Throttle never allowed a fetch in tests | Snapshot `fetched_at` used the real clock while services used a simulated `now` | Snapshots record the job's `now`; never mix clocks in one rule |
| 10 | Template looped over characters | `{% for side in "away home" %}` iterates a string | Use explicit includes |
| 11 | Template used a nonexistent `get_item` filter | Assumed a filter that Django lacks | Build view-model objects (`GridColumn`) in selectors |
| 12 | Best-bet limit test passed the wrong limit | Settings were cached on a previously loaded `LeagueWeek` | Services read settings from the week passed in; views load fresh per request; tests refresh |
| 13 | `assert` in application code | Ruff S101 (asserts vanish under `-O`) | `request_user()` helper raising `PermissionDenied` |
| 14 | Settings form saved nothing | `ModelForm.is_valid()` copies values onto the instance before the service compares | Reload the instance (`refresh_from_db()`) before calling the service |
| 15 | Shell smoke tests got 400 responses | Django test client outside pytest needs `testserver` in `ALLOWED_HOSTS` | Set `DJANGO_ALLOWED_HOSTS=testserver` for those scripts |
| 16 | Activity redaction could not be per game | Cleared picks no longer exist to look up their game | Redact per week until `picks_lock_at` (conservative) |
| 17 | Over-broad test assertion (`"BUF" not in page`) | Team names appear legitimately in line events | Assert on the specific leak (`"picked BUF"`) |
| 18 | ESPN scheduled games report score `"0"` | Feed quirk | Store scores only when in progress or final |
| 19 | Windows environment | PostgreSQL install needs an elevated prompt the agent can't show; the `python` on PATH is a Microsoft Store stub; bash heredocs with apostrophes broke | User installs PostgreSQL; use `uv` for Python; write files with the editor tool rather than shell heredocs |
| 20 | CI status checking | `gh` CLI not installed | Poll the public GitHub Actions API for the latest run |

---

## 11. Not built yet
Tracked in [12 Roadmap](12-roadmap.md) and [06 Open Questions](06-open-questions.md): email
notifications (reminders, week open, weekly results, security alerts) and preferences; Render
deployment, backups, monitoring and client-IP handling behind the proxy; later-phase settings
(variable/closing lines, auto-pick, bonuses, drop worst week, commissioner-selected tiebreaker
game, game slates, grace period); history import; PWA.
