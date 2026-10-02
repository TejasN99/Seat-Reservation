from datetime import datetime
from typing import List
from pydantic import BaseModel, Field


class CreateShowRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, example="friday-night")
    seats: List[str] = Field(..., min_items=1, example=["A1", "A2", "A3", "A4", "A5"])
    price_paise: int = Field(..., gt=0, example=25000, description="Price in paise (integer minor units)")
    per_user_limit: int = Field(default=4, gt=0, example=4, description="Max seats a single user can hold/confirm")


class SeatDetail(BaseModel):
    seat_number: str
    status: str  # 'AVAILABLE' | 'CONFIRMED'


class ShowResponse(BaseModel):
    id: str
    name: str
    price_paise: int
    per_user_limit: int
    total_seats: int
    created_on: datetime


class ShowStateResponse(BaseModel):
    id: str
    name: str
    price_paise: int
    per_user_limit: int
    total_seats: int
    available_count: int
    confirmed_count: int
    seats: List[SeatDetail]
