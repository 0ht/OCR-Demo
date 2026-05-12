import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from .ocr_service import run_ocr

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

app = FastAPI(title="OCR Demo API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ocr")
async def ocr(
    file: UploadFile = File(...),
    di_model_id: str | None = Form(default=None),
    cu_analyzer_id: str | None = Form(default=None),
) -> dict:
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )

    file_bytes = await file.read()

    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        result = run_ocr(
            file_bytes,
            di_model_id=di_model_id,
            cu_analyzer_id=cu_analyzer_id,
        )
        return {
            "fileName": file.filename,
            "contentType": file.content_type,
            **result,
        }
    except RuntimeError as exc:
        logger.exception("OCR processing failed")
        raise HTTPException(status_code=500, detail="OCR processing failed") from exc
