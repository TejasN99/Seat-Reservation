# Raw SQL Queries for Shows & Seats

INSERT_SHOW = """
INSERT INTO shows (id, name, price_paise, per_user_limit)
VALUES (%s, %s, %s, %s)
RETURNING id, name, price_paise, per_user_limit, created_on;
"""

BATCH_INSERT_SEATS = """
INSERT INTO seats (show_id, seat_number, status)
VALUES (%s, %s, 'AVAILABLE');
"""

GET_SHOW_BY_ID = """
SELECT id, name, price_paise, per_user_limit, created_on
FROM shows
WHERE id = %s;
"""

GET_SEATS_BY_SHOW_ID = """
SELECT seat_number, status
FROM seats
WHERE show_id = %s
ORDER BY seat_number ASC;
"""

GET_SHOW_SEAT_COUNTS = """
SELECT 
    COUNT(*) AS total_seats,
    COUNT(*) FILTER (WHERE status = 'AVAILABLE') AS available_count,
    COUNT(*) FILTER (WHERE status = 'CONFIRMED') AS confirmed_count
FROM seats
WHERE show_id = %s;
"""
