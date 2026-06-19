"""
routers/explore.py — Company information database explorer

Routes:
  GET /explore/companies           → list rows (optional search on pool_id)
  GET /explore/companies/{id}      → single full row
"""

import os

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter(tags=["Explore"], prefix="/explore")


def _connect():
    url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/vm_tools_cache")
    return psycopg2.connect(url)


@router.get("/companies")
def list_companies(search: str = Query("", description="Filter pool_id (case-insensitive)")):
    try:
        conn = _connect()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if search.strip():
                cur.execute(
                    """
                    SELECT id, pool_id, pool_id_link, name_check, website, created_at
                    FROM company_information
                    WHERE pool_id ILIKE %s
                    ORDER BY created_at DESC
                    LIMIT 500
                    """,
                    (f"%{search.strip()}%",),
                )
            else:
                cur.execute(
                    """
                    SELECT id, pool_id, pool_id_link, name_check, website, created_at
                    FROM company_information
                    ORDER BY created_at DESC
                    LIMIT 500
                    """
                )
            rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except psycopg2.Error as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/companies/{company_id}")
def get_company(company_id: int):
    try:
        conn = _connect()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, pool_id, pool_id_link, name_check, website,
                       founded_year, revenue, ownership, employees, details, created_at
                FROM company_information
                WHERE id = %s
                """,
                (company_id,),
            )
            row = cur.fetchone()
        conn.close()
        if row is None:
            return JSONResponse(status_code=404, content={"error": "Company not found"})
        return dict(row)
    except psycopg2.Error as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
