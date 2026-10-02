import time
import uuid
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from utils.db import init_db_pool, close_db_pool
from modules.shows.router import router as shows_router
from modules.reservations.router import router as reservations_router
from modules.health_metrics.router import router as health_metrics_router

# Configure Structured Logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s", "level":"%(levelname)s", "message":"%(message)s"}'
)
logger = logging.getLogger("paytm_seat_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for database connection pool."""
    logger.info("Initializing database connection pool and applying schema...")
    await init_db_pool()
    yield
    logger.info("Closing database connection pool...")
    await close_db_pool()


app = FastAPI(
    title="Paytm Seat Reservation System",
    version="1.0.0",
    description="High-concurrency, race-free seat reservation backend with exact-once idempotency semantics.",
    lifespan=lifespan
)

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start_time = time.perf_counter()
    
    response = await call_next(request)
    
    process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = str(process_time_ms)
    
    logger.info(
        f"request_id={request_id} method={request.method} path={request.url.path} "
        f"status={response.status_code} latency_ms={process_time_ms}"
    )
    return response


# Global Exception Handlers ensuring zero unhandled 5xx for domain outcomes
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status_code": exc.status_code,
            "detail": exc.detail,
            "request_id": request.headers.get("X-Request-ID")
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": True,
            "status_code": status.HTTP_400_BAD_REQUEST,
            "detail": "Invalid request parameters",
            "errors": exc.errors(),
            "request_id": request.headers.get("X-Request-ID")
        }
    )


# Include Routers
app.include_router(shows_router)
app.include_router(reservations_router)
app.include_router(health_metrics_router)


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "Paytm Seat Reservation API",
        "status": "online",
        "docs_url": "/docs"
    }
