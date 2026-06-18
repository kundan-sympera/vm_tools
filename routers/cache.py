"""
routers/cache.py — Cache management endpoints

Routes:
  GET    /cache          → stats (entry count, DB size)
  DELETE /cache          → wipe every entry
  DELETE /cache/entry    → delete one entry by key (URL or stocks hash)
"""

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from shared import _Cache

router = APIRouter(tags=["Cache"], prefix="/cache")


@router.get("")
def cache_stats():
    """Return the number of cached entries and SQLite DB size."""
    return _Cache.stats()


@router.delete("")
def cache_clear_all():
    """Delete every cached entry."""
    deleted = _Cache.clear_all()
    return {"deleted": deleted, "message": f"Cleared {deleted} cache entries"}


@router.delete("/entry")
def cache_delete_entry(key: str = Query(..., description="Exact URL or cache key to remove")):
    """Delete a single cache entry by its key (URL or stocks hash)."""
    found = _Cache.delete(key)
    if not found:
        return JSONResponse(status_code=404, content={"error": "Key not found in cache"})
    return {"deleted": True, "key": key}
