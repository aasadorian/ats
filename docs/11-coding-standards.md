# 11 — Coding Standards

All code in this repository follows these standards. Where possible they are **enforced by tools**
(formatter, linter, type checker, pre-commit hooks and CI) rather than by memory or code review.

## 1. Which standards, and in what order

| Layer | Standard | Role |
|-------|----------|------|
| 1 | **[PEP 8](https://peps.python.org/pep-0008/)** — Python style guide | The baseline. Every Python project's common ground |
| 2 | **[PEP 257](https://peps.python.org/pep-0257/)** (docstrings) and **[PEP 484](https://peps.python.org/pep-0484/)** (type hints) | How to document and type code |
| 3 | **[Django coding style](https://docs.djangoproject.com/en/dev/internals/contributing/writing-code/coding-style/)** | Django-specific conventions (model field order, imports, templates) |
| 4 | **[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)** | Reference for questions PEP 8 doesn't answer (exceptions, default arguments, properties, docstring format) |
| — | **Our tool config (Ruff, mypy)** | Wins any conflict between the layers above |

**Why not the Google guide alone?** It's an excellent guide, but it's a superset of PEP 8 written for
Google's internal tooling. Some of its rules don't fit a modern Django project: 80-character lines,
its own formatter (`yapf`) and import style. The community standard is PEP 8 enforced by an
automatic formatter and linter. We use the Google guide as a tie-breaker and adopt its **docstring
format**.

## 2. Tooling (enforced)

| Tool | Purpose | Runs in |
|------|---------|---------|
| **Ruff format** | Code formatter (Black-compatible), line length **88** | pre-commit, CI, PyCharm on save |
| **Ruff check** | Linter + import sorting (replaces flake8, isort, pyupgrade, bandit) | pre-commit, CI, PyCharm |
| **mypy** + `django-stubs` | Static type checking | pre-commit, CI |
| **pytest** | Tests | CI |
| **pre-commit** | Runs the above, plus the no-emoji check (§4), before each commit | Local |
| **djLint** | Django template formatting and linting | pre-commit, CI |

Ruff rule sets to enable in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 88
target-version = "py313"

[tool.ruff.lint]
select = [
  "E", "W", "F",   # pycodestyle, pyflakes (PEP 8)
  "I",             # import sorting
  "N",             # PEP 8 naming
  "UP",            # modern Python syntax
  "B",             # bugbear: likely bugs
  "SIM",           # simplifications
  "DJ",            # Django-specific
  "DTZ",           # no naive datetimes (critical for pick locks)
  "S",             # security (bandit)
  "PT",            # pytest style
  "T20",           # no print()
  "ERA",           # no commented-out code
  "RUF",           # Ruff-specific, including ambiguous unicode
]

[tool.mypy]
strict = true
plugins = ["mypy_django_plugin.main"]
```

**CI fails on any formatting, lint, type or test error.** Rule exceptions (`# noqa`, `# type: ignore`)
need a specific rule code and a short reason, e.g. `# noqa: S311 - not security sensitive`.

## 3. Comments and docstrings

**Code should explain itself.** Keep comments to a minimum.

- **Do not** write comments that restate the code (`# increment counter`, `# get the user`).
  Rename the variable or extract a well-named function instead.
- **Do** comment the **why** when it isn't obvious from the code. Examples: a league rule, a feed
  quirk, a workaround with a link to the issue.
  - Good: `# Postponed games keep their original lock so picks never reopen.`
  - Bad: `# Check if game is postponed`
- **No commented-out code.** Delete it; git has the history. (Enforced by Ruff `ERA`.)
- **No `TODO` without an issue reference**: `# TODO(#42): ...`.
- **Docstrings** only where they add information the signature doesn't: public service functions
  with non-obvious behavior, rules or side effects. **Google docstring format**, kept short. No
  docstrings on simple models, views, tests or private helpers whose name and types say it all.

```python
def save_pick(member: Membership, game: Game, team: Team, *, best_bet: bool) -> Pick:
    """Create or update a member's pick and record the activity event.

    Raises:
        PickLockedError: The game's lock time has passed.
        BestBetLimitError: The member already has the maximum best bets this week.
    """
```

## 4. No emojis

**Never use emojis** anywhere in the codebase:

- Source code, identifiers, comments and docstrings
- String literals, log messages, error messages and email templates
- HTML templates and static files: use **SVG icons** (e.g., an inline icon set) for visual markers
- Test names and fixtures
- Commit messages, branch names and pull request titles

**Enforcement:** a pre-commit hook and CI step scans changed files (excluding `docs/`) for
characters in the Unicode emoji ranges and fails if any are found. Ruff `RUF001`–`RUF003` also
flag ambiguous unicode characters.

## 5. Python conventions

- **Python 3.13**, pinned with `uv` (`.python-version`); dependencies locked in `uv.lock`.
- **Type hints on all functions** in application code (mypy strict). Use built-in generics
  (`list[int]`, `X | None`).
- **Naming** (PEP 8): `snake_case` functions and variables, `PascalCase` classes, `UPPER_SNAKE`
  constants, `_leading_underscore` for private. Names describe intent: `lock_at`, not `dt2`.
- **Small functions** with one job. Prefer early returns over deep nesting.
- **Keyword-only arguments** (`*`) for booleans and optional parameters:
  `save_pick(..., best_bet=True)`, never `save_pick(..., True)`.
- **Imports** are absolute and sorted by Ruff. No wildcard imports.
- **Exceptions:** raise specific custom exceptions (`PickLockedError`), never bare `except:` or
  `except Exception: pass`. Catch only what you can handle.
- **Logging:** use the `logging` module (`logger = logging.getLogger(__name__)`), never `print`.
  Never log secrets, passwords, tokens or full email addresses.
- **Prefer the standard library and modern idioms:** f-strings, `pathlib`, `dataclasses`,
  `enum` / Django `TextChoices`, `zoneinfo`, `decimal.Decimal` for lines and points (never `float`).
- **Datetimes are always timezone-aware.** `django.utils.timezone.now()`, never `datetime.now()`.
  Store UTC; convert only for display.
- **No magic numbers:** league rules come from `LeagueSettings`; other constants are named.

## 6. Django conventions

- **Thin views, logic in services.** Each app has:
  - `services.py`: functions that change state (validation, rules, `transaction.atomic()`, activity log).
  - `selectors.py` or custom `QuerySet` methods: read queries, including visibility rules (`visible_to(user)`).
  - Views only parse input, call a service or selector, and render.
- **Templates contain no business logic.** Pass ready-to-render data from the view.
- **Models:** follow Django's field/Meta/method ordering; define `__str__`; use `TextChoices` for
  enumerations; put constraints in the database (`UniqueConstraint`, `CheckConstraint`) as well as in Python.
- **Queries:** avoid N+1 queries with `select_related` / `prefetch_related`. No raw SQL unless
  necessary, and then always parameterized.
- **Transactions:** any multi-row change plus its activity events goes in one `transaction.atomic()`.
- **Migrations:** generated with `makemigrations`, committed, reviewed; never edit a migration
  after it's merged. Data migrations are separate from schema migrations.
- **Settings:** split `base` / `dev` / `prod`; secrets and environment-specific values come from
  environment variables (`django-environ`), never committed (see `.gitignore`).
- **Security defaults stay on:** CSRF, template autoescaping, `SECURE_*` settings in production.
  Run `manage.py check --deploy` in CI.

## 7. Testing

- **pytest + pytest-django**, `factory_boy` for test data, `time-machine` to control the clock.
- Test behavior, not implementation. One behavior per test, named for it:
  `test_pick_rejected_after_game_lock`.
- **Rules code must be thoroughly tested:** scoring, half-point normalization, lock times,
  visibility, tiebreakers and splits, postponed and OFF games. Aim for **100% branch coverage**
  on these modules and **≥ 90%** overall.
- No network calls in tests: feed clients are tested against recorded JSON fixtures.

## 8. Git workflow

- Short-lived branches off `main`; merge via pull request once CI is green.
- Commit messages: imperative mood, short subject (≤ 72 characters), body explaining **why** when useful.
  No emojis.
- Keep commits focused; formatting-only changes go in their own commit.

## 9. Applying these standards

- New code must pass all checks before merge; there are no exceptions for "quick fixes".
- PyCharm: enable the Ruff plugin (format on save) and the mypy plugin, and set the project
  interpreter to the `uv` virtualenv.
- These standards also apply to AI-assisted code. `CLAUDE.md` at the repo root points here.
