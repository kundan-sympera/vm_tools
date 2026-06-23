"""
routers/explore.py — Company information database explorer

Routes:
  GET /explore/companies           → list rows (optional search on pool_id)
  GET /explore/companies/{id}      → single full row
"""

import psycopg2.extras
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from utils.db import get_conn

router = APIRouter(tags=["Explore"], prefix="/explore")


@router.get("/companies")
def list_companies(search: str = Query("", description="Filter pool_id (case-insensitive)")):
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if search.strip():
                cur.execute(
                    """
                    SELECT id, pool_id, pool_id_link, name_check, website, created_at
                    FROM company_information
                    WHERE pool_id::text ILIKE %s
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
        conn = get_conn()
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
