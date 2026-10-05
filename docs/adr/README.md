# Architecture Decision Records

Significant, hard-to-reverse technical decisions, recorded with their context, the options that
were considered, and the reasons for the choice. Smaller decisions live in the decision log in
[docs/README.md](../README.md).

| # | Decision | Status | Date |
|---|----------|--------|------|
| [0001](0001-web-framework-django.md) | Use Django as the web framework | Accepted | 2026-10-05 |

## Writing a new ADR
Copy the structure of 0001: **Context → Decision drivers → Options considered → Evaluation →
Decision → Consequences → Revisit if**. Number ADRs sequentially and never delete one; if a
decision changes, mark the old ADR "Superseded by NNNN" and write a new one.
