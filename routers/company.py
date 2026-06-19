"""
routers/company.py — Company data extraction service

Routes:
  POST /service/company-extract  → upload CSV, returns extracted CSV
"""

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse, Response

from services import company_extractor

router = APIRouter(tags=["Company Extractor"], prefix="/service")


@router.post("/company-extract")
async def company_extract(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        return JSONResponse(status_code=400, content={"error": "Only CSV files are accepted"})

    try:
        csv_bytes   = await file.read()
        output_csv  = company_extractor.run(csv_bytes)
        return Response(
            content=output_csv,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=company_extraction_output.csv"},
        )
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
