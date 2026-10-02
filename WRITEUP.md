# Technical Design & Concurrency Write-Up

## 1. The Atomic Decision Mechanism

### Why Read-Then-Write Fails
A naive `SELECT status FROM seats WHERE ...` followed by an application-level `if status == 'AVAILABLE': UPDATE seats ...` produces double-sells under load because multiple concurrent transactions read the same `"AVAILABLE"` state before either commits.

### Our Solution: Deterministic Row Locking (`SELECT ... FOR UPDATE`)
We push the concurrency decision directly into PostgreSQL's ACID transaction engine using **pessimistic row-level locking**:
1. **Sorted Lock Acquisition (Deadlock Prevention)**:
   When reserving multiple seats (e.g. `["B2", "A1"]`), the service sorts the seat identifiers alphabetically (`["A1", "B2"]`) before issuing:
   ```sql
   SELECT id, seat_number, status
   FROM seats
   WHERE show_id = $1 AND seat_number = ANY($2)
   ORDER BY seat_number ASC
   FOR UPDATE;
   ```
   Because all concurrent transactions acquire row locks in the exact same global order, cyclic wait conditions (**deadlocks**) are mathematically impossible.
2. **All-or-Nothing Evaluation**:
   If any requested seat is missing or its locked status is not `'AVAILABLE'`, or if the user's active seat count exceeds `per_user_limit`, the transaction immediately aborts and returns a clean `409 Conflict`.
3. **Atomic State Transition**:
   If all conditions pass, `UPDATE seats SET status = 'CONFIRMED' WHERE id = ANY(...)` is executed and committed atomically in the same transaction.

---

## 2. Idempotency & Exactly-Once Semantics

- **Storage**: Stored in the `idempotency_records` table with a unique primary key `idempotency_key`.
- **Payload Integrity**: Every request computes a deterministic SHA-256 hash of the normalized payload (`show_id` + sorted seats).
- **Execution Flow**:
  1. **Replay (Success)**: If `idempotency_key` exists and `request_hash` matches $\to$ return stored `201 Created` response immediately with zero extra database modifications.
  2. **Conflict (Mismatch)**: If `idempotency_key` exists but `request_hash` or `user_id` differs $\to$ reject immediately with `409 Conflict`.
  3. **First-Time Execution**: Executed inside the atomic transaction and saved alongside the reservation.

---

## 3. Consistency vs. Availability Under Network Partitions (CAP Theorem)

- **Choice**: **Consistency over Availability (CP)**.
- **Rationale**: In seat reservations and ticketing, selling the same physical seat twice (overbooking) causes irreparable business and customer harm. If a network partition occurs between database replicas or shards, we reject/fail-closed rather than risk split-brain double confirmations.

---

## 4. Observability & 2 AM Alerting

### Prometheus Metrics Exposed (`/metrics`)
- `reservations_confirmed_total{show_id}`: Total successful bookings.
- `reservations_declined_total{show_id, reason}`: Rejections categorized by `seat_taken`, `per_user_limit`, or `idempotent_payload_conflict`.
- `seats_available{show_id}` & `seats_confirmed{show_id}`: Real-time gauges reconciling total capacity.

### What We Get Paged For at 2 AM
1. **Database Connectivity Failure (`/health/ready` returning 503)**: Immediate page — service cannot process ACID transactions.
2. **5xx Error Rate > 0.1%**: System errors indicate unhandled edge cases or connection pool exhaustion (declines must be 4xx).
3. **Reconciliation Invariant Breach**: If `available + confirmed != total_seats` for any show, trigger high-severity alert.

---

## 5. AI Usage Disclosure

- **Directed vs. Decided**: AI was used for rapid scaffolding of boilerplate (FastAPI routers, Pydantic schemas, Prometheus metrics setup). Architectural decisions — namely PostgreSQL pessimistic row-level locking with deterministic alphabetical sorting, the idempotency ledger design, all-or-nothing rollback semantics, and connection pool sizing — were deliberately designed to meet the exact correctness bar.

---

## 6. What We Would Do Next (Future Improvements)

1. **Temporary Time-Boxed Holds (TTL)**: Implement a 5-minute hold mechanism using Postgres `held_until TIMESTAMPTZ` with lightweight conditional updates.
2. **Tiered & Dynamic Seat Pricing**: Store category/tier pricing in `seats` and `reservation_seats`.
3. **Database Read Replicas**: Route read-only show queries (`GET /shows/{id}`) to read replicas while keeping transactional reservations on the primary writer.
