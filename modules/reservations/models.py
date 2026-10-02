from typing import List, Optional
from pydantic import BaseModel, Field


class ReserveSeatsRequest(BaseModel):
    seats: List[str] = Field(..., min_items=1, example=["A12"])
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Unique key to guarantee exactly-once reservation semantics. Can also be passed as 'Idempotency-Key' HTTP header."
    )


class ReservationResponse(BaseModel):
    reservation_id: str
    show_id: str
    user_id: str
    seats: List[str]
    amount_paise: int
    status: str  # 'confirmed' | 'cancelled'


class CancelReservationResponse(BaseModel):
    reservation_id: str
    status: str
    message: str
