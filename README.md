# ats

A self-hosted NFL against-the-spread pick'em league. Design docs live in [docs/](docs/README.md).

## Local setup (Windows)

1. **Install uv** (manages Python and dependencies):
   `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
2. **Install PostgreSQL 17** from an elevated PowerShell:
   `winget install --id PostgreSQL.PostgreSQL.17`
   Remember the `postgres` superuser password you choose; keep port 5432.
3. **Create `.env`**: copy `.env.example` to `.env`, set a random `DJANGO_SECRET_KEY`, and choose a
   password inside `DATABASE_URL`.
4. **Create the database**: `powershell -File scripts/setup_local_db.ps1`
5. **Install dependencies and migrate**:
   ```
   uv sync
   uv run python manage.py migrate
   uv run python manage.py createsuperuser
   uv run pre-commit install
   ```
6. **Run**: `uv run python manage.py runserver`, then open http://localhost:8000.

Public signup is closed; accounts come from league invites (a later milestone). Use
`createsuperuser` for a local login.

## PyCharm
- Interpreter: *Add Interpreter > Add Local Interpreter > Select existing*, pointing at
  `.venv\Scripts\python.exe` (created by `uv sync`).
- Enable Django support with settings module `config.settings.dev`.
- Install the **Ruff** plugin and enable format on save. Enable the **Mypy** plugin.

## Checks
All of these run in CI on every push and pull request; `pre-commit` runs most of them before each commit.
```
uv run ruff format --check .
uv run ruff check .
uv run mypy .
uv run djlint --check --lint templates
uv run pytest
```

Coding standards: [docs/11-coding-standards.md](docs/11-coding-standards.md).

## Creating a league locally
```
uv run python manage.py sync_schedule --season 2026
uv run python manage.py create_league --name "Office ATS" --slug office --season 2026 --commissioner-email you@example.com
```
Commissioner pages require two-factor authentication; set `COMMISSIONER_MFA_REQUIRED=false` in
`.env` to skip it during local development.
