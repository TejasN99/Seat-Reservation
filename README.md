# Paytm Money — Seat Reservation at Scale

High-concurrency, race-free seat reservation backend built with **FastAPI**, **AsyncPG / Psycopg 3**, and **PostgreSQL**.

The service enforces strict ACID concurrency guarantees under on-sale stampedes (e.g. 500 buyers fighting for the same seat at $t=0$), exact-once idempotency semantics, deadlock-free multi-seat locking, per-user limits, and real-time Prometheus observability with **zero 5xx server errors**.

---

## Key Correctness Highlights

1. **Deterministic Row-Level Locking (`SELECT ... FOR UPDATE`)**:
   Multi-seat requests sort seat identifiers alphabetically (e.g. `["A1", "B2"]`) before acquiring locks in PostgreSQL, eliminating circular wait conditions and preventing deadlocks.
2. **Atomic State Transition**:
   Evaluation (existence, availability, per-user limit) and seat updates occur inside a single atomic ACID transaction. Races for the same seat produce exactly **one 201 Created**; all other contenders receive a clean **409 Conflict** (never 5xx).
3. **Exact-Once Idempotency**:
   The `idempotency_records` ledger stores request payload hashes (SHA-256) and response bodies:
   - Retries with the same key & payload return the cached `201` response with zero extra database modifications.
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

## Quick Start (Local)

### 1. Start PostgreSQL
```bash
docker compose up -d
```

### 2. Install Dependencies & Run
```bash
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Swagger UI is accessible at: **`http://localhost:8000/docs`**

---

## One-Command Concurrency Burst

Run the automated stampede benchmark against your local or live deployed URL:

```bash
python burst.py http://localhost:8000
```

### Example Benchmark Output:
```text
=======================================================
🔥 Starting On-Sale Concurrency Burst against http://localhost:8000
=======================================================

✅ Server readiness probe passed.
✅ Created show 'burst-show-1790968100' (ID: 1c94cb74-b939-4eda-9562-bf5153ff83fc) with 50 seats.

⚡ [Scenario A] Hot-Seat Storm: 500 concurrent buyers stampeding seat 'A1'...
   Completed 500 requests in 5.35s (93 req/s).

⚡ [Scenario B] Multi-Seat Contention: 500 concurrent buyers requesting 2 seats each...
   Completed 500 requests in 7.33s (68 req/s).

⚡ [Scenario C] Idempotency Storm: 100 parallel retries with the SAME key...

⚡ [Scenario D] Idempotency Key Conflict Test (Same key, different seats)...
   ✅ Correctly returned 409 Conflict for modified payload.

=======================================================
📊 Final Invariant Reconciliation Check
=======================================================
Total Seats:     50
Available Seats: 2
Confirmed Seats: 48
Reconciliation:  2 + 48 = 50 (Expected: 50)
🏆 RECONCILIATION INVARIANT: PERFECT MATCH (100% Correct)

=======================================================
📈 Outcome Distribution Summary
=======================================================
Total Requests Fired: 1101
  201 Created (Success)                  : 25 (2.3%)
  409 Conflict (Clean Domain Decline)    : 1076 (97.7%)
  5xx Server Errors                      : 0 (0.0%)
=======================================================
```

---

## API Reference

| Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/shows` | Admin Bearer Token | Create a show with seats & price in paise |
| `GET` | `/shows/{id}` | Public / Any | Retrieve seat statuses and reconciliation counts |
| `POST` | `/shows/{id}/reserve` | User Bearer Token | Reserve seats atomically (supports `Idempotency-Key`) |
| `POST` | `/reservations/{id}/cancel` | Owner Bearer Token | Release seats back to available |
| `GET` | `/health/live` | Public | Liveness probe |
| `GET` | `/health/ready` | Public | Readiness probe (validates database connectivity) |
| `GET` | `/metrics` | Public | Prometheus metrics exporter |
