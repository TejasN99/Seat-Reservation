import json
import hashlib
import uuid
from typing import List, Optional
import psycopg
from fastapi import HTTPException, status
from modules.reservations.models import (
    ReserveSeatsRequest,
    ReservationResponse,
    CancelReservationResponse
)
from modules.reservations import queries
from modules.health_metrics import service as metrics_service


def generate_request_hash(show_id: str, seats: List[str]) -> str:
    """Generates SHA-256 hash of the normalized reservation request payload."""
    normalized = f"{show_id}:{','.join(sorted(seats))}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def reserve_seats(
    conn: psycopg.AsyncConnection,
    show_id: str,
    user_id: str,
    request: ReserveSeatsRequest,
    header_idempotency_key: Optional[str] = None
) -> dict:
    """
    Atomically reserves requested seats for an authenticated user with:
    1. Exact-once idempotency semantics (replay vs 409 payload conflict).
    2. Deterministic row locking (deadlock prevention).
    3. All-or-nothing seat validation (409 conflict if any seat taken).
    4. Strict per-user booking limit enforcement.
    """
    idempotency_key = header_idempotency_key or request.idempotency_key
    sorted_seats = sorted(list(dict.fromkeys(request.seats)))
    
    if not sorted_seats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one seat must be specified."
        )

    req_hash = generate_request_hash(show_id, sorted_seats)

    # 1. Idempotency pre-check
    if idempotency_key:
        async with conn.cursor() as cur:
            await cur.execute(queries.GET_IDEMPOTENCY_RECORD, (idempotency_key,))
            existing_record = await cur.fetchone()
            if existing_record:
                if existing_record["request_hash"] == req_hash and existing_record["user_id"] == user_id:
                    return json.loads(existing_record["response_body"])
                else:
                    metrics_service.record_reservation_declined(show_id, "idempotent_payload_conflict")
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency key was already used with a different request payload or user."
                    )

    # 2. Atomic Transaction Scope
    async with conn.transaction():
        async with conn.cursor() as cur:
            # A. Fetch Show details & per_user_limit
            await cur.execute(queries.GET_SHOW_FOR_RESERVATION, (show_id,))
            show_row = await cur.fetchone()
            if not show_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Show '{show_id}' not found."
                )

            price_paise = show_row["price_paise"]
            per_user_limit = show_row["per_user_limit"]

            # B. Deterministic Row-Locking on requested seats
            await cur.execute(queries.LOCK_SEATS_FOR_UPDATE, (show_id, sorted_seats))
            locked_seats = await cur.fetchall()

            # Check if all requested seats actually exist in this show
            if len(locked_seats) != len(sorted_seats):
                found_numbers = {row["seat_number"] for row in locked_seats}
                missing_seats = [s for s in sorted_seats if s not in found_numbers]
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Seats not found in show: {missing_seats}"
                )

            # C. All-or-nothing check: ensure every seat is 'AVAILABLE'
            unavailable_seats = [
                row["seat_number"] for row in locked_seats if row["status"] != "AVAILABLE"
            ]
            if unavailable_seats:
                metrics_service.record_reservation_declined(show_id, "seat_taken")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Seats already taken: {unavailable_seats}"
                )

            # D. Per-user booking limit check under lock
            await cur.execute(queries.COUNT_USER_HELD_SEATS, (show_id, user_id))
            user_count_row = await cur.fetchone()
            current_held = user_count_row["held_count"] if user_count_row else 0

            if current_held + len(sorted_seats) > per_user_limit:
                metrics_service.record_reservation_declined(show_id, "per_user_limit")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Per-user limit exceeded. You currently hold {current_held} seats. Max limit is {per_user_limit}."
                )

            # E. Perform State Transition
            seat_ids = [row["id"] for row in locked_seats]
            await cur.execute(queries.UPDATE_SEATS_STATUS, ("CONFIRMED", seat_ids))

            # F. Create Reservation
            reservation_id = str(uuid.uuid4())
            total_amount_paise = price_paise * len(sorted_seats)
            await cur.execute(
                queries.INSERT_RESERVATION,
                (reservation_id, show_id, user_id, total_amount_paise)
            )

            # G. Insert Reservation Seats Mapping
            res_seat_tuples = [
                (reservation_id, row["id"], row["seat_number"], price_paise)
                for row in locked_seats
            ]
            await cur.executemany(queries.BATCH_INSERT_RESERVATION_SEATS, res_seat_tuples)

            response_data = {
                "reservation_id": reservation_id,
                "show_id": show_id,
                "user_id": user_id,
                "seats": sorted_seats,
                "amount_paise": total_amount_paise,
                "status": "confirmed"
            }

            # H. Persist Idempotency Record
            if idempotency_key:
                await cur.execute(
                    queries.INSERT_IDEMPOTENCY_RECORD,
                    (
                        idempotency_key,
                        user_id,
                        show_id,
                        req_hash,
                        status.HTTP_201_CREATED,
                        json.dumps(response_data)
                    )
                )

            # Record metrics
            metrics_service.record_reservation_confirmed(show_id, len(sorted_seats))

    return response_data


async def cancel_reservation(
    conn: psycopg.AsyncConnection,
    reservation_id: str,
    user_id: str
) -> CancelReservationResponse:
    async with conn.transaction():
        async with conn.cursor() as cur:
            # 1. Lock and verify reservation
            await cur.execute(queries.GET_RESERVATION_FOR_CANCEL, (reservation_id,))
            res_row = await cur.fetchone()
            if not res_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Reservation '{reservation_id}' not found."
                )

            if res_row["user_id"] != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not authorized to cancel this reservation."
                )

            if res_row["status"] == "CANCELLED":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Reservation is already cancelled."
                )

            # 2. Fetch associated seats
            await cur.execute(queries.GET_RESERVATION_SEATS, (reservation_id,))
            res_seats = await cur.fetchall()
            seat_ids = [row["seat_id"] for row in res_seats]

            # 3. Release seats back to 'AVAILABLE'
            if seat_ids:
                await cur.execute(queries.UPDATE_SEATS_STATUS, ("AVAILABLE", seat_ids))

            # 4. Update reservation status to 'CANCELLED'
            await cur.execute(queries.UPDATE_RESERVATION_STATUS, ("CANCELLED", reservation_id))

    return CancelReservationResponse(
        reservation_id=reservation_id,
        status="cancelled",
        message="Reservation successfully cancelled and seats released."
    )
