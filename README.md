# Seat Reservation System

A backend service for handling high-concurrency seat reservations, built with **FastAPI**, **AsyncPG / Psycopg 3**, and **PostgreSQL**.

The main goal of this project is to handle "stampede" scenarios (like 500 people trying to book the exact same seat at the exact same second) without any double-booking, deadlocks, or server crashes.

---

## How It Works

1. **Row-Level Locking**:
   Instead of trying to check availability in Python, I pushed the concurrency logic down to Postgres. Multi-seat requests sort their seat IDs alphabetically and then run a `SELECT ... FOR UPDATE`. Sorting the IDs prevents deadlocks, and the DB-level lock ensures no two requests can modify the same seat at once.
2. **Atomic Updates**:
   Everything happens in one transaction. We check if the seat exists, if it's available, and if the user is under their booking limit. If anything fails, we roll back and return a `409 Conflict`. If it succeeds, exactly one person gets a `201 Created`. No 5xx errors.
3. **Idempotency**:
   To handle retries safely, the app saves a SHA-256 hash of the request payload in an `idempotency_records` table. If the same key comes in again with the same payload, it just returns the saved response. If the payload is different, it rejects it.
4. **Metrics & Health**:
   - Built-in Prometheus metrics at `/metrics` (tracks confirmed bookings, declines, and available seats).
   - `/health/live` and `/health/ready` endpoints to ensure the DB is actually reachable before taking traffic.

---

## Project Structure

```text
├── db/
│   └── schema.sql                 # Table definitions and constraints
├── utils/
│   ├── config.py                  # Environment variables
│   └── db.py                      # psycopg3 connection pool setup
├── modules/
│   ├── auth/                      # Basic HTTPBearer token auth
│   ├── shows/                     # Show creation and status endpoints
│   ├── reservations/              # Core booking/canceling logic
│   └── health_metrics/            # Probes and Prometheus exporter
├── main.py                        # FastAPI entrypoint
├── burst.py                       # Load testing script
├── Dockerfile                     
├── docker-compose.yml             # Local DB setup
└── WRITEUP.md                     # Detailed architecture notes
```

---

## Live Demo

- **API URL**: `https://seat-reservation-production-0196.up.railway.app`
- **Swagger Docs**: `https://seat-reservation-production-0196.up.railway.app/docs`
- **Metrics**: `https://seat-reservation-production-0196.up.railway.app/metrics`

---

## Running the Load Test

I wrote a script to simulate a bunch of concurrent users trying to book the same seats to prove the concurrency logic works. You can run it against the live URL:

```bash
python burst.py https://seat-reservation-production-0196.up.railway.app
```

The script runs 4 scenarios:
1. **Hot-Seat Storm**: 500 users fighting for one seat. (Exactly 1 wins, 499 get declined).
2. **Multi-Seat Contention**: 500 users booking 2 random seats each.
3. **Idempotency Storm**: 100 identical retries at the same time.
4. **Idempotency Conflict**: Trying to reuse a key for different seats.

---

## API Endpoints

| Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/shows` | Admin Bearer Token | Create a show (price in paise) |
| `GET` | `/shows/{id}` | Public | Check seat availability |
| `POST` | `/shows/{id}/reserve` | User Bearer Token | Book seats (pass `Idempotency-Key` header) |
| `POST` | `/reservations/{id}/cancel` | User Bearer Token | Cancel a booking |
| `GET` | `/health/ready` | Public | Check DB connectivity |
| `GET` | `/metrics` | Public | View Prometheus metrics |
