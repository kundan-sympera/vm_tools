"""
routers/cache.py — Cache management endpoints

Routes:
  GET    /cache              → stats for every cache table
  DELETE /cache              → wipe all scraper cache tables
  DELETE /cache/{table}      → wipe one specific table
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from utils.db import get_conn, cache_stats, cache_clear, ALL_CACHE_TABLES

router = APIRouter(tags=["Cache"], prefix="/cache")


@router.get("")
def get_cache_stats():
    conn = get_conn()
    stats = cache_stats(conn)
    conn.close()
    return stats


@router.delete("")
def clear_all_caches():
    conn = get_conn()
    deleted = {}
    for table in ALL_CACHE_TABLES:
        try:
            deleted[table] = cache_clear(conn, table)
        except Exception as exc:
            deleted[table] = f"error: {exc}"
    conn.close()
    return {"cleared": deleted}


@router.delete("/{table}")
def clear_one_cache(table: str):
    if table not in ALL_CACHE_TABLES:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unknown table '{table}'. Valid: {ALL_CACHE_TABLES}"},
        )
    conn = get_conn()
    deleted = cache_clear(conn, table)
    conn.close()
    return {"table": table, "deleted": deleted}
