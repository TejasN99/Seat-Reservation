import os
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    APP_NAME: str = "Paytm Seat Reservation Service"
    DATABASE_URL: str = Field(
        default="postgresql://postgres:postgrespassword@localhost:5432/seat_reservation",
        alias="DATABASE_URL"
    )
    DEFAULT_PER_USER_LIMIT: int = 4
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
