import psycopg
from fastapi import APIRouter, Depends, Response, status
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from utils.db import get_db
from modules.health_metrics import service

router = APIRouter(tags=["Health & Metrics"])


@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_probe():
    return {"status": "alive"}


@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_probe(conn: psycopg.AsyncConnection = Depends(get_db)):
    """
    Readiness probe: actively tests DB connectivity.
    Fails closed with 503 if the database is unreachable.
    """
    is_healthy = await service.check_db_health(conn)
    if not is_healthy:
        return Response(
            content='{"status": "unhealthy", "reason": "database connection failed"}',
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json"
        )
    return {"status": "ready", "database": "connected"}


@router.get("/metrics")
async def metrics():
    """Exposes Prometheus-formatted metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
