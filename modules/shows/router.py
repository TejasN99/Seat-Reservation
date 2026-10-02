import psycopg
from fastapi import APIRouter, Depends, status
from utils.db import get_db
from modules.auth.service import get_admin_user
from modules.auth.models import User
from modules.shows.models import CreateShowRequest, ShowResponse, ShowStateResponse
from modules.shows import service

router = APIRouter(prefix="/shows", tags=["Shows"])


@router.post("", response_model=ShowResponse, status_code=status.HTTP_201_CREATED)
async def create_new_show(
    request: CreateShowRequest,
    conn: psycopg.AsyncConnection = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    return await service.create_show(conn, request)


@router.get("/{id}", response_model=ShowStateResponse, status_code=status.HTTP_200_OK)
async def get_show(
    id: str,
    conn: psycopg.AsyncConnection = Depends(get_db),
):
    return await service.get_show_state(conn, id)
