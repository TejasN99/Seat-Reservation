from prometheus_client import Counter, Gauge
import psycopg

# Prometheus Metrics
RESERVATIONS_CONFIRMED = Counter(
    "reservations_confirmed_total",
    "Total number of confirmed reservations",
    ["show_id"]
)

RESERVATIONS_DECLINED = Counter(
    "reservations_declined_total",
    "Total number of declined reservations by reason",
    ["show_id", "reason"]
)

SEATS_AVAILABLE_GAUGE = Gauge(
    "seats_available",
    "Current number of available seats per show",
    ["show_id"]
)

SEATS_CONFIRMED_GAUGE = Gauge(
    "seats_confirmed",
    "Current number of confirmed seats per show",
    ["show_id"]
)


def record_reservation_confirmed(show_id: str, seats_count: int = 1):
    RESERVATIONS_CONFIRMED.labels(show_id=show_id).inc(seats_count)


def record_reservation_declined(show_id: str, reason: str):
    RESERVATIONS_DECLINED.labels(show_id=show_id, reason=reason).inc()


def update_seat_gauges(show_id: str, available: int, confirmed: int):
    SEATS_AVAILABLE_GAUGE.labels(show_id=show_id).set(available)
    SEATS_CONFIRMED_GAUGE.labels(show_id=show_id).set(confirmed)


async def check_db_health(conn: psycopg.AsyncConnection) -> bool:
    """Executes a lightweight query to verify database connectivity."""
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1;")
            row = await cur.fetchone()
            return row is not None
    except Exception:
        return False
