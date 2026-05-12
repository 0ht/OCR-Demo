# OCR-Demo

> ⚠️ **本リポジトリは PoC / 検証目的の構成です。** 本番運用には追加のセキュリティ・可用性・運用設計が必要です。詳細は [docs/poc-vs-production.md](docs/poc-vs-production.md) を参照してください。

Microsoft Foundry (AIServices) リソースのエンドポイントを介して、**Document Intelligence (`prebuilt-read` 等)** と **Content Understanding (`prebuilt-read` 等)** の両方を同じファイルに対して並行実行し、抽出結果と所要時間を **UI 上で左右並べて比較**するデモです。
両サービスは Foundry の単一エンドポイント上で `documentintelligence/...` と `contentunderstanding/...` のパスとして提供されます。

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [docs/requirement.md](docs/requirement.md) | 要件定義 |
| [docs/architecture.md](docs/architecture.md) | アーキテクチャ詳細 |
| [docs/deploy-guide.md](docs/deploy-guide.md) | デプロイ手順 |
| [docs/operations.md](docs/operations.md) | 運用ガイド |
| [docs/cost-estimate.md](docs/cost-estimate.md) | 月額コスト見積もり |
| [docs/poc-vs-production.md](docs/poc-vs-production.md) | PoC 前提と本番ベストプラクティスの差分 |

## 構成

- **UI**: Python Streamlit (`src/ui`)
- **バックエンド API**: FastAPI (`src/backend`)
- **ホスティング**: Azure Container Apps (ACA)
- **インフラ**: Bicep (`infra/main.bicep`)
- **デプロイ**: azd (`azure.yaml`)

Bicep では、Container Apps Environment を閉域 (internal) で構成し、**API は internal ingress**、**UI のみ external ingress** で公開します。

## API 仕様

バックエンド API (FastAPI) は以下のエンドポイントを提供します。

| メソッド | パス | 説明 |
|---|---|---|
| `GET` | `/health` | ヘルスチェック。`{"status": "ok"}` を返す |
| `POST` | `/ocr` | ファイルを DI / CU で並行解析し、結果を JSON で返す |

`POST /ocr` のリクエスト:

| パラメータ | 種別 | 必須 | 説明 |
|---|---|---|---|
| `file` | `File` (multipart) | ✓ | 解析対象ファイル (PDF / PNG / JPG / JPEG / TIFF / BMP)。上限 20 MB |
| `di_model_id` | `Form` | - | DI モデル ID (既定: 環境変数 `DOCUMENT_INTELLIGENCE_MODEL_ID`) |
| `cu_analyzer_id` | `Form` | - | CU アナライザー ID (既定: 環境変数 `CONTENT_UNDERSTANDING_ANALYZER_ID`) |

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

1. `azd env new ocr-demo`
2. リージョンと環境を設定:
   ```powershell
   azd env set AZURE_LOCATION westus
   azd env set ENVIRONMENT dev
   ```
3. 必要に応じて追加の環境変数を `azd env set` で設定:
   - `FOUNDRY_PROJECT_NAME` (新版 Foundry プロジェクト名。既定: `default-project`)
   - `CONTENT_UNDERSTANDING_ANALYZER_ID` (既定: `prebuilt-read`)
   - `CONTENT_UNDERSTANDING_API_VERSION` (既定: `2025-11-01`)
   - `DOCUMENT_INTELLIGENCE_MODEL_ID` (既定: `prebuilt-read`)
   - `DOCUMENT_INTELLIGENCE_API_VERSION` (既定: `2024-11-30`)
4. `azd up`

詳細な手順・環境変数一覧・トラブルシュートは [docs/deploy-guide.md](docs/deploy-guide.md) を参照。

> **新版 Microsoft Foundry プロジェクト構成**: AIServices アカウント (`allowProjectManagement: true`) とその子リソースである Foundry プロジェクトを作成します。
>
> - エンドポイントは新版 Foundry の統一アカウントエンドポイント `FOUNDRY_ENDPOINT` = `https://<account>.services.ai.azure.com/` に一本化
> - Document Intelligence / Content Understanding / プロジェクト API いずれも同一エンドポイント配下で提供
> - 認証は Managed Identity ベース (キーレス)。Container App の System Assigned MI に `Cognitive Services User` (アカウントスコープ) と `Azure AI User` (プロジェクトスコープ) を Bicep から自動付与
