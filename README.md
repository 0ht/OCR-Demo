# OCR-Demo

Microsoft Foundry の Document Intelligence / Content Understanding を使った OCR デモです。

## 構成

- **UI**: Python Streamlit (`src/ui`)
- **バックエンド API**: FastAPI (`src/backend`)
- **ホスティング**: Azure Container Apps (ACA)
- **インフラ**: Bicep (`infra/main.bicep`)
- **デプロイ**: azd (`azure.yaml`)

Bicep では、Container Apps Environment を閉域 (internal) で構成し、**API は internal ingress**、**UI のみ external ingress** で公開します。

## ローカル実行

```bash
cd src/backend && pip install -r requirements.txt && uvicorn app.main:app --reload
```

別ターミナル:

```bash
cd src/ui && pip install -r requirements.txt && API_BASE_URL=http://localhost:8000 streamlit run app.py
```

## テスト

```bash
pip install -r src/backend/requirements.txt -r requirements-dev.txt
pytest -q
```

## azd での利用

1. `azd init` (既存プロジェクトとして)
2. 必要な環境変数を `azd env set` で設定:
   - `DOCUMENT_INTELLIGENCE_ENDPOINT`
   - `DOCUMENT_INTELLIGENCE_KEY`
   - `CONTENT_UNDERSTANDING_ENDPOINT`
   - `CONTENT_UNDERSTANDING_KEY`
   - `CONTENT_UNDERSTANDING_PROJECT`
   - `CONTENT_UNDERSTANDING_API_VERSION` (任意)
3. `azd up`
