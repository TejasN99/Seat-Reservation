# Seat Reservation at Scale

High-concurrency, race-free seat reservation backend built with **FastAPI**, **AsyncPG / Psycopg 3**, and **PostgreSQL**.

The service enforces strict ACID concurrency guarantees under on-sale stampedes (e.g. 500 buyers fighting for the same seat at t=0), exact-once idempotency semantics, deadlock-free multi-seat locking, per-user limits, and real-time Prometheus observability with **zero 5xx server errors**.

---

## Technical Correctness Highlights

1. **Deterministic Row-Level Locking (`SELECT ... FOR UPDATE`)**:
   Multi-seat requests sort seat identifiers alphabetically (e.g. `["A1", "B2"]`) before acquiring locks in PostgreSQL, eliminating circular wait conditions and preventing deadlocks.
2. **Atomic State Transition**:
   Evaluation (existence, availability, per-user limit) and seat updates occur inside a single atomic ACID transaction. Races for the same seat produce exactly **one 201 Created**; all other contenders receive a clean **409 Conflict** (never 5xx).
3. **Exact-Once Idempotency**:
   The `idempotency_records` ledger stores request payload hashes (SHA-256) and response bodies:
   - Retries with the same key and payload return the cached `201` response with zero extra database modifications.
   - Retries with the same key but different payloads are rejected with `409 Conflict`.
4. **Reconciliation Invariant Guarantee**:
   $$\text{available\_count} + \text{confirmed\_count} == \text{total\_seats}$$
   is strictly preserved at all times.
5. **Observability**:
   - Liveness (`/health/live`) and Readiness (`/health/ready` verifying live DB connectivity).
   - Prometheus metrics (`/metrics`) exposing `reservations_confirmed_total`, `reservations_declined_total(reason=...)`, and `seats_available`.
   - Structured JSON logs with correlation IDs (`X-Request-ID`).

---

## Architecture & Project Structure

```text
├── db/
│   └── schema.sql                 # Table definitions, constraints (ON DELETE RESTRICT), indexes
├── utils/
│   ├── config.py                  # App configuration & settings
│   └── db.py                      # psycopg 3 AsyncConnectionPool & get_db dependency
├── modules/
│   ├── auth/                      # Token-derived identity & security (HTTPBearer)
│   ├── shows/                     # POST /shows, GET /shows/{id}
│   ├── reservations/              # POST /shows/{id}/reserve, POST /reservations/{id}/cancel
│   └── health_metrics/            # /health/live, /health/ready, /metrics
├── main.py                        # FastAPI application, correlation middleware
├── burst.py                       # One-command concurrency stampede benchmark script
├── Dockerfile                     # Production container image
├── docker-compose.yml             # Local PostgreSQL container
├── WRITEUP.md                     # Technical architecture documentation
└── requirements.txt
```

---

## Live Deployment Links

- **Live Application URL**: `https://seat-reservation-production-0196.up.railway.app`
- **Swagger Documentation**: `https://seat-reservation-production-0196.up.railway.app/docs`
- **Readiness Probe**: `https://seat-reservation-production-0196.up.railway.app/health/ready`
- **Prometheus Metrics**: `https://seat-reservation-production-0196.up.railway.app/metrics`

---

## Running the Concurrency Burst Benchmark

Run the automated stampede benchmark against the live deployed URL:

```bash
python burst.py https://seat-reservation-production-0196.up.railway.app
```

### Benchmark Output Format:
```text
===============================================================
SEAT RESERVATION - CONCURRENCY & RECONCILIATION BENCHMARK
Target URL: https://seat-reservation-production-0196.up.railway.app
===============================================================

[INFO] Server readiness probe passed (/health/ready -> 200 OK).
[INFO] Created show 'burst-show-1790968100' (ID: ...) with 100 seats.

[EXEC] Scenario A: Hot-Seat Storm (500 concurrent buyers competing for seat 'A1')...

   +-------------------------------------------------------------
   | Scenario: Scenario A (Hot-Seat Contention on A1)
   | Total Requests Fired : 500
   |   201 Created (Winner/Replay)        : 1 (0.2%)
   |   409 Conflict (Clean Decline)       : 499 (99.8%)
   |   5xx Server Errors                  : 0
   | Status: [PASS] Exactly 1 buyer won seat 'A1'; remaining 499 declined with 409 Conflict. Zero 5xx.
   +-------------------------------------------------------------

[EXEC] Scenario B: Multi-Seat Contention (500 concurrent buyers booking 2 seats each)...

   +-------------------------------------------------------------
   | Scenario: Scenario B (Multi-Seat Random Contention)
   | Total Requests Fired : 500
   |   201 Created (Winner/Replay)        : 24 (4.8%)
   |   409 Conflict (Clean Decline)       : 476 (95.2%)
   |   5xx Server Errors                  : 0
   | Status: [PASS] Handled multi-seat reservations with zero deadlocks and zero 5xx.
   +-------------------------------------------------------------

[EXEC] Scenario C: Idempotency Storm (100 parallel retries with identical key on seat 'A99')...

   +-------------------------------------------------------------
   | Scenario: Scenario C (100 Idempotent Retries on seat A99)
   | Total Requests Fired : 100
   |   201 Created (Winner/Replay)        : 100 (100.0%)
   |   5xx Server Errors                  : 0
   | Status: [PASS] All 100 retries returned the original 201 response with exact-once execution.
   +-------------------------------------------------------------

[EXEC] Scenario D: Idempotency Key Conflict Test (Same key with modified payload)...

   +-------------------------------------------------------------
   | Scenario: Scenario D (Key Conflict on Modified Payload)
   | Total Requests Fired : 1
   |   409 Conflict (Clean Decline)       : 1 (100.0%)
   |   5xx Server Errors                  : 0
   | Status: [PASS] Correctly rejected with 409 Conflict when key was reused with modified seat payload.
   +-------------------------------------------------------------

===============================================================
FINAL INVARIANT RECONCILIATION REPORT
===============================================================
Total Seats Registered : 100
Available Seats        : 51
Confirmed Seats        : 49
Reconciliation Balance : 51 + 49 = 100 (Expected: 100)
RECONCILIATION INVARIANT: [PASS] Strict balance holds to the unit (100% Correct).

===============================================================
OVERALL OUTCOME DISTRIBUTION
===============================================================
Total Requests Fired : 1101
  201 Created (Success / Replay)         : 125 (11.4%)
  409 Conflict (Clean Domain Decline)    : 976 (88.6%)
  5xx Server Errors                      : 0 (0.0%)
===============================================================
```

---

## API Reference

| Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/shows` | Admin Bearer Token | Create a show with seats and price in paise |
| `GET` | `/shows/{id}` | Public / Any | Retrieve seat statuses and reconciliation counts |
| `POST` | `/shows/{id}/reserve` | User Bearer Token | Reserve seats atomically (supports `Idempotency-Key`) |
| `POST` | `/reservations/{id}/cancel` | Owner Bearer Token | Release seats back to available |
| `GET` | `/health/live` | Public | Liveness probe |
| `GET` | `/health/ready` | Public | Readiness probe (validates database connectivity) |
| `GET` | `/metrics` | Public | Prometheus metrics exporter |
