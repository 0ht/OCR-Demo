import base64
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

_COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"

_credential: DefaultAzureCredential | None = None
_token_provider = None


def _get_token_provider():
    global _credential, _token_provider
    if _token_provider is None:
        _credential = DefaultAzureCredential()
        _token_provider = get_bearer_token_provider(_credential, _COGNITIVE_SERVICES_SCOPE)
    return _token_provider


def _auth_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {_get_token_provider()()}"}
    if extra:
        headers.update(extra)
    return headers


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def _poll_operation(client: httpx.Client, operation_location: str, max_attempts: int, interval: float) -> dict[str, Any]:
    for _ in range(max_attempts):
        poll_response = client.get(operation_location, headers=_auth_headers())
        poll_response.raise_for_status()
        payload = poll_response.json()
        status = (payload.get("status") or "").lower()
        if status == "succeeded":
            return payload
        if status in {"failed", "canceled"}:
            raise RuntimeError(f"Analyze operation failed: {payload}")
        time.sleep(interval)
    raise RuntimeError("Analyze operation polling timed out")


def _normalize_polygon(polygon: Any) -> list[list[float]]:
    """polygon を [[x,y], ...] 形式に正規化する。flat list / dict list 両対応。"""
    if not polygon:
        return []
    if isinstance(polygon[0], dict):
        return [[float(p.get("x", 0.0)), float(p.get("y", 0.0))] for p in polygon]
    flat = list(polygon)
    return [[float(flat[i]), float(flat[i + 1])] for i in range(0, len(flat) - 1, 2)]


def _parse_cu_source(source: str) -> tuple[int | None, list[list[float]]]:
    """CU の source 文字列をパースして (pageNumber, polygon) を返す。

    フォーマット:
      D(pageNumber,x1,y1,x2,y2,x3,y3,x4,y4)  -> 4頂点 polygon
      D(pageNumber,left,top,width,height)    -> 軸揃えbbox → 4頂点に展開
    """
    if not source or not source.startswith("D(") or not source.endswith(")"):
        return None, []
    body = source[2:-1]
    parts = [p.strip() for p in body.split(",") if p.strip()]
    if len(parts) < 5:
        return None, []
    try:
        page_no = int(parts[0])
        nums = [float(x) for x in parts[1:]]
    except ValueError:
        return None, []
    if len(nums) >= 8:
        polygon = [[nums[i], nums[i + 1]] for i in range(0, 8, 2)]
        return page_no, polygon
    if len(nums) == 4:
        left, top, width, height = nums
        polygon = [
            [left, top],
            [left + width, top],
            [left + width, top + height],
            [left, top + height],
        ]
        return page_no, polygon
    return None, []


def _extract_page1_words_di(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Document Intelligence レスポンスからページ1の words を抽出する。"""
    if not pages:
        return {"width": None, "height": None, "unit": None, "words": []}
    page = pages[0]
    words_raw = page.get("words") or []
    words: list[dict[str, Any]] = []
    for w in words_raw:
        polygon = _normalize_polygon(w.get("polygon") or w.get("boundingPolygon") or [])
        if not polygon:
            continue
        words.append(
            {
                "content": w.get("content") or w.get("text") or "",
                "polygon": polygon,
                "confidence": w.get("confidence"),
            }
        )
    return {
        "width": page.get("width"),
        "height": page.get("height"),
        "unit": page.get("unit"),
        "words": words,
    }


def _extract_page1_words_cu(contents: list[dict[str, Any]]) -> dict[str, Any]:
    """Content Understanding レスポンスからページ1の words を抽出する。

    CU は word 位置を `source` 文字列 (e.g. 'D(1,x1,y1,...)') で返す。
    ページ情報は content -> pages[] 以外に content -> words[].source を
    直接返すケースもあるため、両方を走査する。
    """
    page_meta = {"width": None, "height": None, "unit": None}
    words_out: list[dict[str, Any]] = []

    for c in contents:
        for p in c.get("pages") or []:
            if page_meta["width"] is None:
                page_meta = {
                    "width": p.get("width"),
                    "height": p.get("height"),
                    "unit": p.get("unit"),
                }
            for w in p.get("words") or []:
                page_no, polygon = _parse_cu_source(w.get("source", ""))
                if page_no != 1 or not polygon:
                    continue
                words_out.append(
                    {
                        "content": w.get("content") or w.get("text") or "",
                        "polygon": polygon,
                        "confidence": w.get("confidence"),
                    }
                )
        # content 直下に words があるケース (一部のアナライザー)
        if not words_out:
            for w in c.get("words") or []:
                page_no, polygon = _parse_cu_source(w.get("source", ""))
                if page_no != 1 or not polygon:
                    continue
                words_out.append(
                    {
                        "content": w.get("content") or w.get("text") or "",
                        "polygon": polygon,
                        "confidence": w.get("confidence"),
                    }
                )
    return {**page_meta, "words": words_out}


def analyze_with_document_intelligence(
    file_bytes: bytes,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Document Intelligence (prebuilt-read 等) を Foundry エンドポイント経由で呼び出す。"""
    endpoint = _required_env("FOUNDRY_ENDPOINT").rstrip("/")
    model_id = model_id or os.getenv("DOCUMENT_INTELLIGENCE_MODEL_ID", "prebuilt-read")
    api_version = os.getenv("DOCUMENT_INTELLIGENCE_API_VERSION", "2024-11-30")
    max_attempts = int(os.getenv("DOCUMENT_INTELLIGENCE_MAX_POLLING_ATTEMPTS", "60"))
    interval = float(os.getenv("DOCUMENT_INTELLIGENCE_POLLING_INTERVAL_SECONDS", "2"))

    analyze_url = (
        f"{endpoint}/documentintelligence/documentModels/{model_id}:analyze"
        f"?api-version={api_version}"
    )

    started = time.perf_counter()
    with httpx.Client(timeout=60.0) as client:
        analyze_response = client.post(
            analyze_url,
            headers=_auth_headers({"Content-Type": "application/octet-stream"}),
            content=file_bytes,
        )
        analyze_response.raise_for_status()

        operation_location = analyze_response.headers.get("operation-location")
        if not operation_location:
            raise RuntimeError("Document Intelligence operation-location header is missing")

        payload = _poll_operation(client, operation_location, max_attempts, interval)

    result = payload.get("analyzeResult", {}) or {}
    pages = result.get("pages") or []
    text_content = result.get("content", "") or ""
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "service": "documentIntelligence",
        "modelId": model_id,
        "apiVersion": api_version,
        "elapsedMs": elapsed_ms,
        "extractedText": text_content,
        "extractedMarkdown": text_content,
        "page1": _extract_page1_words_di(pages),
        "raw": result,
    }


def analyze_with_content_understanding(
    file_bytes: bytes,
    analyzer_id: str | None = None,
) -> dict[str, Any]:
    """Content Understanding (prebuilt-read 等) を Foundry エンドポイント経由で呼び出す。"""
    endpoint = _required_env("FOUNDRY_ENDPOINT").rstrip("/")
    analyzer_id = analyzer_id or os.getenv("CONTENT_UNDERSTANDING_ANALYZER_ID", "prebuilt-read")
    api_version = os.getenv("CONTENT_UNDERSTANDING_API_VERSION", "2025-11-01")
    max_attempts = int(os.getenv("CONTENT_UNDERSTANDING_MAX_POLLING_ATTEMPTS", "60"))
    interval = float(os.getenv("CONTENT_UNDERSTANDING_POLLING_INTERVAL_SECONDS", "2"))

    analyze_url = (
        f"{endpoint}/contentunderstanding/analyzers/{analyzer_id}:analyze"
        f"?api-version={api_version}"
    )

    encoded = base64.b64encode(file_bytes).decode("ascii")
    started = time.perf_counter()
    with httpx.Client(timeout=60.0) as client:
        analyze_response = client.post(
            analyze_url,
            headers=_auth_headers({"Content-Type": "application/json"}),
            json={"inputs": [{"data": encoded}]},
        )
        analyze_response.raise_for_status()

        operation_location = analyze_response.headers.get("operation-location")
        if not operation_location:
            raise RuntimeError("Content Understanding operation-location header is missing")

        payload = _poll_operation(client, operation_location, max_attempts, interval)

    result = payload.get("result", {}) or {}
    contents = result.get("contents") or []
    markdown_text = "\n\n".join(
        (c.get("markdown") or c.get("text") or "") for c in contents
    ).strip()
    plain_parts: list[str] = []
    for c in contents:
        if c.get("text"):
            plain_parts.append(c["text"])
    plain_text = "\n\n".join(plain_parts).strip() or markdown_text
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "service": "contentUnderstanding",
        "analyzerId": result.get("analyzerId") or analyzer_id,
        "apiVersion": api_version,
        "elapsedMs": elapsed_ms,
        "extractedText": plain_text,
        "extractedMarkdown": markdown_text,
        "page1": _extract_page1_words_cu(contents),
        "raw": result,
    }


def _safe_run(fn, *args) -> dict[str, Any]:
    try:
        return fn(*args)
    except httpx.HTTPStatusError as exc:  # API レスポンスのボディも保存して原因究明を容易にする
        body = ""
        try:
            body = exc.response.text[:1000]
        except Exception:
            pass
        return {
            "service": fn.__name__,
            "error": f"{exc} | body={body}",
        }
    except Exception as exc:  # 並行実行時に片方が失敗しても比較できるようにする
        return {
            "service": fn.__name__,
            "error": str(exc),
        }


def run_ocr(
    file_bytes: bytes,
    di_model_id: str | None = None,
    cu_analyzer_id: str | None = None,
) -> dict[str, Any]:
    """Document Intelligence と Content Understanding を並行実行し、結果を比較用に返す。"""
    with ThreadPoolExecutor(max_workers=2) as pool:
        di_future = pool.submit(_safe_run, analyze_with_document_intelligence, file_bytes, di_model_id)
        cu_future = pool.submit(_safe_run, analyze_with_content_understanding, file_bytes, cu_analyzer_id)
        di_result = di_future.result()
        cu_result = cu_future.result()

    return {
        "documentIntelligence": di_result,
        "contentUnderstanding": cu_result,
    }
