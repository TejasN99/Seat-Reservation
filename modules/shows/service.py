import uuid
from typing import List
import psycopg
from fastapi import HTTPException, status
from modules.shows.models import CreateShowRequest, ShowStateResponse, SeatDetail
from modules.shows import queries


async def create_show(conn: psycopg.AsyncConnection, request: CreateShowRequest) -> dict:
    show_id = str(uuid.uuid4())
    unique_seats = list(dict.fromkeys(request.seats))

    async with conn.transaction():
        async with conn.cursor() as cur:
            await cur.execute(
                queries.INSERT_SHOW,
                (show_id, request.name, request.price_paise, request.per_user_limit)
            )
            show_row = await cur.fetchone()

            seat_tuples = [(show_id, seat_num) for seat_num in unique_seats]
            await cur.executemany(queries.BATCH_INSERT_SEATS, seat_tuples)

    return {
        "id": show_row["id"],
        "name": show_row["name"],
        "price_paise": show_row["price_paise"],
        "per_user_limit": show_row["per_user_limit"],
        "total_seats": len(unique_seats),
        "created_on": show_row["created_on"]
    }


async def get_show_state(conn: psycopg.AsyncConnection, show_id: str) -> ShowStateResponse:
    async with conn.cursor() as cur:
        # 1. Get Show Details
        await cur.execute(queries.GET_SHOW_BY_ID, (show_id,))
        show_row = await cur.fetchone()
        if not show_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Show with id '{show_id}' not found"
            )

        # 2. Get Seat Counts
        await cur.execute(queries.GET_SHOW_SEAT_COUNTS, (show_id,))
        counts = await cur.fetchone()
        total_seats = counts["total_seats"]
        available_count = counts["available_count"]
        confirmed_count = counts["confirmed_count"]

        # Invariant check: available + confirmed == total_seats
        if available_count + confirmed_count != total_seats:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Reconciliation invariant violation detected in seat counts"
            )

        # 3. Get Individual Seats
        await cur.execute(queries.GET_SEATS_BY_SHOW_ID, (show_id,))
        seat_rows = await cur.fetchall()
        seats_list = [
            SeatDetail(seat_number=row["seat_number"], status=row["status"])
            for row in seat_rows
        ]

    return ShowStateResponse(
        id=show_row["id"],
        name=show_row["name"],
        price_paise=show_row["price_paise"],
        per_user_limit=show_row["per_user_limit"],
        total_seats=total_seats,
        available_count=available_count,
        confirmed_count=confirmed_count,
        seats=seats_list
    )
