# ats

Self-hosted NFL against-the-spread pick'em league (Django). Design docs live in `docs/`; start at `docs/README.md`.

## Rules
- Follow `docs/11-coding-standards.md` for all code.
- Keep code comments to a minimum: only explain non-obvious "why". No commented-out code.
- Never use emojis in code, comments, strings, templates, tests, logs or commit messages.
- Record every product or technical decision in the relevant `docs/` file and add a row to the decision log in `docs/README.md`.
- Keep `docs/13-implementation-reference.md` current with every behavior change (models, rules, URLs, jobs, bugs and lessons). The docs must be enough to rebuild the app without the source.
- Never commit secrets; `Projectscreds.txt` and `.env` files are git-ignored.
