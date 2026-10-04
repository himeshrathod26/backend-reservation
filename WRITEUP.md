# WRITEUP — Seat Reservation at Scale

## 1. Atomic decision

The database is the source of truth. `POST /shows/{id}/reserve` runs in one PostgreSQL transaction.

The transaction first locks the show row with `SELECT ... FOR UPDATE`. It then locks all requested seat rows with `SELECT ... FOR UPDATE`, ordering by `seat_number`. Only after the locks are held does the service validate that every requested seat is `available` and that the user's existing confirmed-seat count plus the requested seats does not exceed `per_user_limit`.

The reservation row and reservation-seat rows are inserted and the seat rows are changed to `confirmed` before the transaction commits.

The show-row lock deliberately serializes reservation decisions within a show. This makes the per-user limit check race-free without relying on an application-level mutex, and it makes the correctness argument simple: there is one database transaction deciding whether a reservation can exist.

For multiple seats, requested rows are always locked in deterministic lexical order. This avoids the classic deadlock pattern where transaction A locks A12 then waits for A13 while transaction B locks A13 then waits for A12.

## 2. No double-sell

A seat can only be changed after its row lock is acquired and its current status is checked. If two transactions target A12, one obtains the row lock first. It can confirm A12 and commit. The other transaction then sees the committed `confirmed` state and returns HTTP 409. There is no read-then-write gap.

The database also has `UNIQUE(show_id, seat_number)` as a structural invariant ensuring a show cannot contain duplicate seat identities.

## 3. Idempotency

Idempotency is stored in PostgreSQL using `UNIQUE(show_id, user_id, idempotency_key)`.

The request hash contains the normalized requested seats and idempotency key. If the same key is retried with the same body, the existing reservation is returned. If the same key is reused with different seats, the API returns HTTP 409.

The key is not stored in process memory, so it remains effective across multiple API workers and restarts.

## 4. Holds / release model

This implementation chooses explicit cancellation rather than time-boxed holds. A successful reservation is immediately `confirmed`. The owner can call `/reservations/{id}/cancel`; the transaction locks the reservation and its seats, verifies ownership, changes the seats back to `available`, and marks the reservation `cancelled` atomically.

A cancellation cannot resurrect a seat belonging to another reservation because the seat's `reservation_id` is checked through the row lock and only seats belonging to the cancelling reservation are modified.

## 5. Reconciliation invariant

The show endpoint counts every seat by state. Since every seat row has exactly one status and the status is constrained to `available`, `held`, or `confirmed`, the counts sum to the total seat rows.

This implementation does not create `held` rows, so the normal state is:

`available + 0 held + confirmed = total`.

## 6. Consistency vs availability under a partition

The reservation path chooses consistency. If PostgreSQL is unavailable, readiness fails and reservation requests do not fabricate success. A 503 may be returned for a database availability failure rather than risking a double sale.

In a partition, the service should not accept reservations from an isolated component that cannot reach the authoritative database. Availability is therefore intentionally sacrificed to preserve seat uniqueness and exactly-once reservation semantics.

## 7. Observability

The service exposes Prometheus metrics for confirmed reservations, decline reasons, HTTP request counts/latency, and available seats.

Structured request logs include a correlation/request ID, method, path, status, and latency.

At 2am, useful alerts would include:

- sustained 5xx rate above the agreed SLO;
- readiness failures / database connectivity failures;
- reservation latency p95/p99 above the booking SLO;
- unexpected growth in `conflict` or database-error outcomes;
- mismatch between reservation counters and independently queried seat state;
- available-seat gauge behaving unexpectedly for an active show.

## 8. AI usage

AI tools were used as an engineering copilot for scaffolding, API shape suggestions, test-case generation, documentation structure, and reviewing concurrency edge cases. The final design decisions were made around the assignment's explicit correctness requirements: PostgreSQL transactions, row locks, deterministic lock ordering, database-backed idempotency, and token-derived identity.

Before submission, every generated component should be run locally, exercised under concurrency, and understood well enough to explain or modify live during the interview.

## 9. What I would do next

For production scale, I would consider:

- reducing contention from a show-wide lock by using more granular transactional invariants while retaining a safe per-user-limit mechanism;
- connection-pool sizing and PgBouncer where appropriate;
- a real identity provider/JWT verification instead of the exercise's bearer-token convention;
- rate limiting and abuse protection;
- distributed tracing;
- load testing at realistic traffic patterns;
- database partitioning/index review for very large event catalogs;
- a dedicated expiry worker if the product changes from confirmed reservations to temporary holds;
- payment authorization integration with an outbox/event pattern so payment retries cannot double-charge.
