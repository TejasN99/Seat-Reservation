import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    APP_NAME: str = "Paytm Seat Reservation Service"
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:admin@localhost:5432/postgres"
    )
    DEFAULT_PER_USER_LIMIT: int = int(os.getenv("DEFAULT_PER_USER_LIMIT", "4"))
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")

settings = Settings()
