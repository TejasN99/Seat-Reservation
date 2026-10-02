from pathlib import Path
from typing import AsyncGenerator
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from utils.config import settings

pool: AsyncConnectionPool | None = None


def get_conn_string() -> str:
    url = settings.DATABASE_URL
    if url.startswith("postgresql+"):
        url = "postgresql" + url[url.index(":"):]
    return url


async def init_db_pool() -> None:
    global pool
    conn_str = get_conn_string()
    pool = AsyncConnectionPool(
        conninfo=conn_str,
        min_size=10,
        max_size=80,
        timeout=10.0,
        kwargs={"row_factory": dict_row, "autocommit": False}
    )
    await pool.open()

    schema_path = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
    if schema_path.exists():
        schema_sql = schema_path.read_text(encoding="utf-8")
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(schema_sql)
            await conn.commit()


async def close_db_pool() -> None:
    global pool
    if pool:
        await pool.close()
        pool = None


async def get_db() -> AsyncGenerator[psycopg.AsyncConnection, None]:
    if pool is None:
        raise RuntimeError("Database connection pool is not initialized.")
    
    async with pool.connection() as conn:
        try:
            yield conn
        finally:
            if conn.pgconn.transaction_status != psycopg.pq.TransactionStatus.IDLE:
                await conn.rollback()