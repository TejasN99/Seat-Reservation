# Write-up: Architecture & Decisions

## The Atomic Decision

To handle high concurrency and avoid double-selling seats, I went with database-level pessimistic locking rather than trying to handle it in the application layer. 

Doing a basic `SELECT` to check if a seat is free and then an `UPDATE` if it is will always fail under load because multiple concurrent requests will read the seat as available before any of them actually commit their updates. 

Instead, I used `SELECT ... FOR UPDATE` inside a single transaction block. 
For multi-seat bookings, there's a risk of deadlocks if two transactions try to lock the same seats in different orders (e.g., T1 locks A1 then B2, T2 locks B2 then A1). To prevent this, the code always sorts the seat IDs alphabetically before grabbing the locks. This guarantees everyone locks rows in the exact same order, which completely prevents deadlocks.

If any of the requested seats are already taken, or if the user goes over their booking limit, we just roll back the transaction and return a 409 Conflict. If everything looks good, we update the seats and commit.

## Idempotency

I created a separate `idempotency_records` table to handle this.
When a request comes in, I hash the payload (show ID + the sorted seats). 
If we see the idempotency key for the first time, we process the booking and save the key, the hash, and the JSON response in the same transaction as the reservation.

If we see a key again, we check the hash:
- If the hash matches, it's a valid retry, and we just return the saved JSON response from the DB without trying to book again.
- If the hash is different (meaning they used the same key for a different set of seats), we reject it with a 409 Conflict.

## Consistency vs. Availability (CAP)

For a ticketing system, Consistency is definitely more important than Availability (CP). Double-selling a seat is a huge customer service nightmare. If the database goes down or gets partitioned, it's better to fail the requests (fail closed) than to risk a split-brain scenario where two different nodes confirm the same seat to different people.

## Observability & Alerts

I added a `/metrics` endpoint for Prometheus. It tracks counters for confirmed reservations and declined ones (tagged by reason, like `seat_taken` or `limit_exceeded`), plus gauges for how many seats are left.

If I were on call, I'd want to be paged for:
- `/health/ready` failing (means the app can't talk to the database).
- Any sudden spike in 5xx errors (meaning the code crashed or the DB connection pool is exhausted, since normal domain declines should always be 4xx).
- The reconciliation invariant breaking (available + confirmed not equaling total seats).

## AI Usage

I used AI to help speed up the boilerplate work—stuff like generating the Pydantic schemas, and scaffolding the Prometheus metrics. I specifically designed the core logic myself, particularly the row-level locking, sorting for deadlock prevention, and the exact idempotency flow to ensure it meets the correctness requirements.

## Future Improvements

If I had more time, I'd add:
1. **Time-based Holds**: A way to hold a seat for 5 minutes while the user pays. I'd add a `held_until` timestamp column to handle this.
2. **Read Replicas**: Pushing the `GET /shows/{id}` traffic to a read replica to take load off the primary database, since reads will likely outnumber writes.
3. **Dynamic Pricing**: Support different pricing tiers for different seats (e.g., VIP vs regular).
