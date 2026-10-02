from typing import Optional
import psycopg
from fastapi import APIRouter, Depends, Header, status
from utils.db import get_db
from modules.auth.service import get_current_user
from modules.auth.models import User
from modules.reservations.models import (
    ReserveSeatsRequest,
    ReservationResponse,
    CancelReservationResponse
)
from modules.reservations import service

router = APIRouter(tags=["Reservations"])


@router.post(
    "/shows/{id}/reserve",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED
)
async def reserve_show_seats(
    id: str,
    request: ReserveSeatsRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    conn: psycopg.AsyncConnection = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    effective_idempotency_key = idempotency_key or x_idempotency_key or request.idempotency_key
    return await service.reserve_seats(
        conn=conn,
        show_id=id,
        user_id=current_user.user_id,
        request=request,
        header_idempotency_key=effective_idempotency_key
    )


@router.post(
    "/reservations/{id}/cancel",
    response_model=CancelReservationResponse,
    status_code=status.HTTP_200_OK
)
async def cancel_user_reservation(
    id: str,
    conn: psycopg.AsyncConnection = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cancels an active reservation and releases seats back to 'AVAILABLE'.
    Only the owner of the reservation can cancel it.
    """
    return await service.cancel_reservation(
        conn=conn,
        reservation_id=id,
        user_id=current_user.user_id
    )
