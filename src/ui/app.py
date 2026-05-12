import io
import os
from typing import Any

import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(page_title="OCR Demo", page_icon="📄", layout="wide")
st.title("OCR 比較デモ")
st.caption("同じ入力ファイルを Document Intelligence と Content Understanding に並行送信して結果を比較します。")

api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")

DI_MODEL_OPTIONS = [
    "prebuilt-read",
    "prebuilt-layout",
    "prebuilt-document",
    "prebuilt-invoice",
    "prebuilt-receipt",
    "prebuilt-businessCard",
    "prebuilt-idDocument",
]
CU_ANALYZER_OPTIONS = [
    "prebuilt-read",
    "prebuilt-layout",
]
CU_NOTE = (
    "※ CU の domain 特化 (`prebuilt-invoice` / `prebuilt-receipt` / `*Search` など) は "
    "`gpt-4.1` + `text-embedding-3-large` のデプロイとマッピング設定が必要です。"
)
OUTPUT_FORMATS = ["text", "markdown", "json (raw)"]

with st.sidebar:
    st.header("解析設定")
    di_model_id = st.selectbox(
        "Document Intelligence モデル",
        DI_MODEL_OPTIONS,
        index=0,
    )
    cu_analyzer_id = st.selectbox(
        "Content Understanding アナライザー",
        CU_ANALYZER_OPTIONS,
        index=0,
    )
    st.caption(CU_NOTE)
    output_format = st.radio("出力形式", OUTPUT_FORMATS, index=0, horizontal=False)
    st.caption("出力形式は表示のみ。両 API は常に同条件で呼び出されます。")


uploaded_file = st.file_uploader(
    "ファイルをアップロード",
    type=["pdf", "png", "jpg", "jpeg", "tiff", "bmp"],
)


def _file_bytes_to_image(file_bytes: bytes, content_type: str | None) -> Image.Image | None:
    """アップロードファイルから 1 ページ目の PIL Image を生成する。"""
    ct = (content_type or "").lower()
    if "pdf" in ct or file_bytes[:4] == b"%PDF":
        try:
            import fitz  # PyMuPDF
        except Exception as exc:
            st.warning(f"PDF 表示には pymupdf が必要です: {exc}")
            return None
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        if doc.page_count == 0:
            return None
        page = doc.load_page(0)
        # 解像度 144 DPI 相当
        matrix = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    try:
        return Image.open(io.BytesIO(file_bytes)).convert("RGB")
    except Exception as exc:
        st.warning(f"画像のデコードに失敗しました: {exc}")
        return None


def _scale_factor(page_meta: dict[str, Any], image: Image.Image) -> tuple[float, float]:
    """API が返す page width/height (inch / pixel) を実際の画像 px にスケールする係数を返す。"""
    img_w, img_h = image.size
    page_w = page_meta.get("width")
    page_h = page_meta.get("height")
    if not page_w or not page_h:
        return 1.0, 1.0
    return img_w / float(page_w), img_h / float(page_h)


def _draw_words_on_image(
    base_image: Image.Image,
    page_meta: dict[str, Any],
    color: str,
) -> tuple[Image.Image, list[dict[str, Any]]]:
    """word polygon を描画し、番号付きリストも返す。"""
    image = base_image.copy()
    draw = ImageDraw.Draw(image, "RGBA")
    sx, sy = _scale_factor(page_meta, image)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    words = page_meta.get("words") or []
    items: list[dict[str, Any]] = []
    fill_rgba = (255, 165, 0, 50) if color == "orange" else (0, 120, 255, 50)
    outline = "orange" if color == "orange" else "blue"

    for idx, w in enumerate(words, start=1):
        polygon = w.get("polygon") or []
        if len(polygon) < 3:
            continue
        scaled = [(p[0] * sx, p[1] * sy) for p in polygon]
        draw.polygon(scaled, outline=outline, fill=fill_rgba, width=2)
        x0 = min(pt[0] for pt in scaled)
        y0 = min(pt[1] for pt in scaled)
        # 番号バッジ
        label = str(idx)
        bbox = draw.textbbox((x0, y0 - 16), label, font=font)
        draw.rectangle(bbox, fill=outline)
        draw.text((x0, y0 - 16), label, fill="white", font=font)
        items.append({"index": idx, "content": w.get("content", ""), "confidence": w.get("confidence")})
    return image, items


def _render_extracted(payload: dict[str, Any], format_choice: str) -> None:
    if format_choice == "markdown":
        md = payload.get("extractedMarkdown") or payload.get("extractedText") or ""
        st.markdown(md if md else "_(空)_")
        return
    if format_choice == "json (raw)":
        st.json(payload.get("raw", {}))
        return
    text = payload.get("extractedText", "") or ""
    st.text_area(
        label="text",
        value=text,
        height=300,
        label_visibility="collapsed",
    )
    st.caption(f"文字数: {len(text)}")


def _render_panel(
    title: str,
    payload: dict[str, Any],
    base_image: Image.Image | None,
    format_choice: str,
    color: str,
) -> None:
    st.subheader(title)

    if "error" in payload:
        st.error(payload["error"])
        return

    elapsed_ms = payload.get("elapsedMs")
    meta_cols = st.columns(2)
    with meta_cols[0]:
        st.metric("経過時間 (ms)", elapsed_ms if elapsed_ms is not None else "-")
    with meta_cols[1]:
        identifier = payload.get("modelId") or payload.get("analyzerId") or ""
        st.metric("モデル / アナライザー", identifier)

    page1 = payload.get("page1") or {}
    if base_image is not None and page1.get("words"):
        annotated, items = _draw_words_on_image(base_image, page1, color=color)
        st.image(annotated, caption=f"{title} – ページ1 word 単位 polygon", width="stretch")
        with st.expander(f"番号 → テキスト 対応表 ({len(items)} 件)"):
            for it in items:
                conf = f" (conf={it['confidence']:.2f})" if it.get("confidence") is not None else ""
                st.markdown(f"**{it['index']}**: `{it['content']}`{conf}")
    elif base_image is not None:
        st.info("このサービスは word 単位の polygon を返しませんでした。")
    else:
        st.info("画像プレビューが生成できませんでした。")

    st.markdown("**抽出結果**")
    _render_extracted(payload, format_choice)

    with st.expander("生レスポンス (JSON)"):
        st.json(payload.get("raw", {}))


if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    st.write(f"ファイル: `{uploaded_file.name}` ({len(file_bytes):,} bytes)")
    if st.button("OCR実行 (両方を並行呼び出し)"):
        with st.spinner("両サービスで解析中..."):
            uploaded_content_type = uploaded_file.type or "application/octet-stream"
            files = {
                "file": (
                    uploaded_file.name,
                    file_bytes,
                    uploaded_content_type,
                )
            }
            data = {
                "di_model_id": di_model_id,
                "cu_analyzer_id": cu_analyzer_id,
            }
            response = requests.post(
                f"{api_base_url.rstrip('/')}/ocr",
                files=files,
                data=data,
                timeout=300,
            )

        if response.status_code != 200:
            st.error(f"APIエラー: {response.status_code} {response.text}")
        else:
            payload = response.json()
            di_payload = payload.get("documentIntelligence", {}) or {}
            cu_payload = payload.get("contentUnderstanding", {}) or {}
            base_image = _file_bytes_to_image(file_bytes, uploaded_content_type)

            left, right = st.columns(2)
            with left:
                _render_panel("🅰 Document Intelligence", di_payload, base_image, output_format, "orange")
            with right:
                _render_panel("🅱 Content Understanding", cu_payload, base_image, output_format, "blue")

            st.divider()
            st.subheader("サマリ比較")
            di_text = di_payload.get("extractedText", "") or ""
            cu_text = cu_payload.get("extractedText", "") or ""
            di_words = (di_payload.get("page1") or {}).get("words") or []
            cu_words = (cu_payload.get("page1") or {}).get("words") or []
            summary_cols = st.columns(2)
            with summary_cols[0]:
                st.metric("DI 文字数", len(di_text), delta=len(di_text) - len(cu_text))
                st.metric("DI word 数", len(di_words), delta=len(di_words) - len(cu_words))
                st.metric("DI 経過時間 (ms)", di_payload.get("elapsedMs", "-"))
            with summary_cols[1]:
                st.metric("CU 文字数", len(cu_text), delta=len(cu_text) - len(di_text))
                st.metric("CU word 数", len(cu_words), delta=len(cu_words) - len(di_words))
                st.metric("CU 経過時間 (ms)", cu_payload.get("elapsedMs", "-"))
