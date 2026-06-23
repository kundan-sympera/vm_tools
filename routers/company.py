"""
routers/company.py — Company data extraction service

Routes:
  POST /service/company-extract  → CSV upload or JSON array, returns extracted CSV/JSON

Input (one of):
  file           — multipart CSV with columns: pool_id, pool_id_link, validated_name, validated_address, details
  companies_json — JSON array of objects with the same columns (n8n-friendly alternative)
"""

import io
import json
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response

from services import company_extractor

router = APIRouter(tags=["Company Extractor"], prefix="/service")

_REQUIRED = {"pool_id", "pool_id_link", "validated_name", "validated_address", "details"}


@router.post("/company-extract")
async def company_extract(
    file:           Optional[UploadFile] = File(default=None),
    companies_json: Optional[str]        = Form(default=None, description='JSON array: [{"pool_id":…,"pool_id_link":…,"validated_name":…,"validated_address":…,"details":…}]'),
    output_format:  str                  = Form(default="csv"),
):
    if companies_json and companies_json.strip():
        try:
            rows = json.loads(companies_json)
            if not isinstance(rows, list):
                raise ValueError("Expected a JSON array")
        except Exception as exc:
            return JSONResponse(status_code=400, content={"error": f"Invalid companies_json: {exc}"})
        if rows:
            missing = _REQUIRED - set(rows[0].keys())
            if missing:
                return JSONResponse(status_code=400, content={"error": f"companies_json missing keys: {', '.join(sorted(missing))}"})
        buf = io.BytesIO()
        pd.DataFrame(rows).to_csv(buf, index=False)
        csv_bytes = buf.getvalue()
    elif file is not None:
        if not file.filename.endswith(".csv"):
            return JSONResponse(status_code=400, content={"error": "Only CSV files are accepted"})
        csv_bytes = await file.read()
    else:
        return JSONResponse(status_code=400, content={"error": "Provide either file or companies_json"})

    try:
        output_csv = company_extractor.run(csv_bytes)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    if output_format.lower() == "json":
        df = pd.read_csv(io.BytesIO(output_csv))
        return JSONResponse(content={"total": len(df), "results": df.to_dict(orient="records")})

    return Response(
        content=output_csv,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=company_extraction_output.csv"},
    )
