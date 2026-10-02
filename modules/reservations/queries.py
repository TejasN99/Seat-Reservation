# Raw SQL Queries for Reservations and Atomic Seat Locking

GET_IDEMPOTENCY_RECORD = """
SELECT idempotency_key, user_id, show_id, request_hash, response_status_code, response_body
FROM idempotency_records
WHERE idempotency_key = %s;
"""

INSERT_IDEMPOTENCY_RECORD = """
INSERT INTO idempotency_records (idempotency_key, user_id, show_id, request_hash, response_status_code, response_body)
VALUES (%s, %s, %s, %s, %s, %s);
"""

GET_SHOW_FOR_RESERVATION = """
SELECT id, price_paise, per_user_limit
FROM shows
WHERE id = %s;
"""

# Deterministic ordered row locking to eliminate deadlocks
LOCK_SEATS_FOR_UPDATE = """
SELECT id, seat_number, status
FROM seats
WHERE show_id = %s AND seat_number = ANY(%s)
ORDER BY seat_number ASC
FOR UPDATE;
"""

COUNT_USER_HELD_SEATS = """
SELECT COALESCE(COUNT(rs.id), 0) AS held_count
FROM reservation_seats rs
JOIN reservations r ON rs.reservation_id = r.id
WHERE r.show_id = %s AND r.user_id = %s AND r.status = 'CONFIRMED';
"""

UPDATE_SEATS_STATUS = """
UPDATE seats
SET status = %s, updated_on = NOW()
WHERE id = ANY(%s);
"""

INSERT_RESERVATION = """
INSERT INTO reservations (id, show_id, user_id, amount_paise, status)
VALUES (%s, %s, %s, %s, 'CONFIRMED')
RETURNING id, show_id, user_id, amount_paise, status, created_on;
"""

BATCH_INSERT_RESERVATION_SEATS = """
INSERT INTO reservation_seats (reservation_id, seat_id, seat_number, price_paise)
VALUES (%s, %s, %s, %s);
"""

GET_RESERVATION_FOR_CANCEL = """
SELECT id, show_id, user_id, status
FROM reservations
WHERE id = %s
FOR UPDATE;
"""

GET_RESERVATION_SEATS = """
SELECT seat_id, seat_number
FROM reservation_seats
WHERE reservation_id = %s;
"""

UPDATE_RESERVATION_STATUS = """
UPDATE reservations
SET status = %s, updated_on = NOW()
WHERE id = %s;
"""
