from fastapi import FastAPI, File, HTTPException, UploadFile

from .ocr_service import run_ocr

app = FastAPI(title="OCR Demo API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ocr")
async def ocr(file: UploadFile = File(...)) -> dict:
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        result = run_ocr(file_bytes)
        return {
            "fileName": file.filename,
            **result,
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
