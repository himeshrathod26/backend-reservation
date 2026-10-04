# Seat Reservation at Scale

Backend take-home for an assigned-seat reservation service. The design deliberately keeps PostgreSQL as the system of record: concurrency, idempotency, and ownership decisions are committed transactionally in one database.

## Stack

- Python 3.12 / FastAPI
- PostgreSQL 16
- SQLAlchemy 2
- Prometheus client
- Docker / Docker Compose

## Semantics

- Reservation requests are **all-or-nothing**.
- Seats transition directly from `available` to `confirmed`; this implementation chooses explicit cancellation rather than time-boxed holds.
- A reservation is owned by the bearer-token user.
- Idempotency is scoped to `(show_id, user_id, idempotency_key)` and the stored request hash prevents same-key/different-body reuse.
- Requested seat rows are locked in lexical order with `SELECT ... FOR UPDATE` inside a transaction.
- The show row is also locked, serializing reservation decisions for a show and making the per-user limit check safe under concurrency. This intentionally favors correctness over maximum write parallelism for this exercise.
- Money is integer paise (`BIGINT`); no floating point is used.

## API

### Create show

```bash
curl -X POST http://localhost:8000/shows \
  -H 'Content-Type: application/json' \
  -d '{"name":"friday-night","seats":["A1","A2","A3"],"price_paise":25000,"per_user_limit":4}'
```

### Reserve

```bash
curl -X POST http://localhost:8000/shows/<SHOW_ID>/reserve \
  -H 'Authorization: Bearer user-123' \
  -H 'Content-Type: application/json' \
  -d '{"seats":["A1"],"idempotency_key":"order-123"}'
```

### Show state

```bash
curl http://localhost:8000/shows/<SHOW_ID>
```

### Cancel

```bash
curl -X POST http://localhost:8000/reservations/<RESERVATION_ID>/cancel \
  -H 'Authorization: Bearer user-123'
```

### Health

- `/health/live`: process liveness only.
- `/health/ready`: runs `SELECT 1`; returns 503 if PostgreSQL is unavailable.

### Metrics

`/metrics` exposes Prometheus text format. Important metrics:

- `reservations_confirmed_total`
- `reservations_declined_total{reason="seat_taken"}`
- `reservations_declined_total{reason="per_user_limit"}`
- `reservations_declined_total{reason="idempotent_replay"}`
- `seats_available{show_id="..."}`
- `http_requests_total`
- `http_request_duration_seconds`

## Local run

```bash
make up
```

Then:

```bash
make health
make burst
```

For a larger run:

```bash
./burst.sh http://localhost:8000 20000 300
```

The burst script creates a fresh show, sends a hot-seat-heavy concurrent workload, prints outcome distribution, and checks the final reconciliation invariant.

## Deployment

`render.yaml` is included as a starting point for a Render Blueprint deployment. Set `DATABASE_URL` to the managed PostgreSQL connection string if deploying manually. Any equivalent Docker-capable platform is fine.

After deployment:

```bash
./burst.sh https://YOUR-LIVE-URL 20000 300
```

## Clean checkout

```bash
git clone <repo>
cd <repo>
docker compose up --build
```

No local Python environment or separately installed PostgreSQL is required.

## Expected hot-seat result

For a fresh show and one request per distinct user targeting the same seat:

```text
201 confirmed: 1
409 seat_taken: N-1
5xx: 0
```

The final API state must satisfy:

```text
available + held + confirmed == total_seats
```

This implementation has no active `held` state because it uses explicit cancellation rather than expiring holds.

## Git history

Commit incrementally. See `GIT_COMMITS.md` for the suggested sequence.
