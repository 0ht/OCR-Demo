import os
import time
from typing import Any

import httpx


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def _analyze_with_document_intelligence(file_bytes: bytes) -> dict[str, Any]:
    endpoint = _required_env("DOCUMENT_INTELLIGENCE_ENDPOINT").rstrip("/")
    key = _required_env("DOCUMENT_INTELLIGENCE_KEY")
    model_id = os.getenv("DOCUMENT_INTELLIGENCE_MODEL_ID", "prebuilt-read")
    api_version = os.getenv("DOCUMENT_INTELLIGENCE_API_VERSION", "2024-11-30")

    analyze_url = (
        f"{endpoint}/documentintelligence/documentModels/{model_id}:analyze"
        f"?api-version={api_version}"
    )

    with httpx.Client(timeout=60.0) as client:
        analyze_response = client.post(
            analyze_url,
            headers={
                "Ocp-Apim-Subscription-Key": key,
                "Content-Type": "application/octet-stream",
            },
            content=file_bytes,
        )
        analyze_response.raise_for_status()

        operation_location = analyze_response.headers.get("operation-location")
        if not operation_location:
            raise RuntimeError("Document Intelligence operation-location header is missing")

        for _ in range(30):
            poll_response = client.get(
                operation_location,
                headers={"Ocp-Apim-Subscription-Key": key},
            )
            poll_response.raise_for_status()
            payload = poll_response.json()
            status = payload.get("status")
            if status == "succeeded":
                return payload.get("analyzeResult", {})
            if status in {"failed", "canceled"}:
                raise RuntimeError(f"Document Intelligence failed: {payload}")
            time.sleep(2)

    raise RuntimeError("Document Intelligence polling timed out")


def _analyze_with_content_understanding(text: str) -> dict[str, Any] | None:
    endpoint = os.getenv("CONTENT_UNDERSTANDING_ENDPOINT")
    key = os.getenv("CONTENT_UNDERSTANDING_KEY")
    project = os.getenv("CONTENT_UNDERSTANDING_PROJECT")

    if not endpoint or not key or not project:
        return None

    api_version = os.getenv("CONTENT_UNDERSTANDING_API_VERSION", "2024-12-01-preview")
    analyze_url = (
        f"{endpoint.rstrip('/')}/contentunderstanding/projects/{project}:analyze"
        f"?api-version={api_version}"
    )

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            analyze_url,
            headers={"Ocp-Apim-Subscription-Key": key},
            json={
                "source": {
                    "kind": "inline",
                    "text": text,
                }
            },
        )

    if response.is_error:
        return {
            "status": "error",
            "code": response.status_code,
            "message": response.text,
        }

    return response.json()


def run_ocr(file_bytes: bytes) -> dict[str, Any]:
    document_result = _analyze_with_document_intelligence(file_bytes)
    extracted_text = document_result.get("content", "")
    content_understanding_result = _analyze_with_content_understanding(extracted_text)

    return {
        "documentIntelligence": document_result,
        "contentUnderstanding": content_understanding_result,
    }
