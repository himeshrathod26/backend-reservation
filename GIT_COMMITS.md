# Suggested incremental Git history

The assignment explicitly says the commit history will be reviewed. Do not create one giant commit.

1. `chore: initialize FastAPI project and Docker setup`
2. `feat: add PostgreSQL schema and show creation API`
3. `feat: add reservation transaction with row locking`
4. `feat: add database-backed idempotency`
5. `feat: enforce per-user reservation limit`
6. `feat: add reservation cancellation and ownership checks`
7. `feat: add health readiness and Prometheus metrics`
8. `test: add concurrency and reconciliation tests`
9. `feat: add production burst runner`
10. `docs: add architecture writeup and deployment instructions`
11. `chore: harden deployment and clean checkout`

After each meaningful change, run the relevant tests and commit. Avoid fake commits or commits that merely rearrange generated files to make the history look longer.
