import os

import requests
import streamlit as st

st.set_page_config(page_title="OCR Demo", page_icon="📄")
st.title("OCR Demo")
st.caption("Document Intelligence + Content Understanding")

api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
uploaded_file = st.file_uploader("ファイルをアップロード", type=["pdf", "png", "jpg", "jpeg", "tiff", "bmp"])

if uploaded_file is not None:
    if st.button("OCR実行"):
        with st.spinner("解析中..."):
            uploaded_content_type = uploaded_file.type or "application/octet-stream"
            file_payload = (uploaded_file.name, uploaded_file.getvalue(), uploaded_content_type)
            files = {"file": file_payload}
            response = requests.post(f"{api_base_url.rstrip('/')}/ocr", files=files, timeout=120)

        if response.status_code != 200:
            st.error(f"APIエラー: {response.status_code} {response.text}")
        else:
            payload = response.json()
            st.subheader("抽出テキスト")
            st.write(payload.get("documentIntelligence", {}).get("content", ""))

            st.subheader("Document Intelligence 結果")
            st.json(payload.get("documentIntelligence", {}))

            st.subheader("Content Understanding 結果")
            st.json(payload.get("contentUnderstanding", {}))
