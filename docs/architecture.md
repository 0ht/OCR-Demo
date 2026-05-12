# アーキテクチャ詳細

## 全体像

本デモは閉域構成の Azure Container Apps 上で Streamlit UI と FastAPI バックエンドを稼働させ、Microsoft Foundry の Document Intelligence / Content Understanding REST API を Private Endpoint 経由で呼び出す。

## コンポーネント

| 層 | 技術 | リソース |
|---|---|---|
| プレゼンテーション | Streamlit (Python) | `ca-{env}-{prj}-ui` (ACA, external) |
| アプリケーション | FastAPI (Python / httpx) | `ca-{env}-{prj}-api` (ACA, internal) |
| AI / OCR | Foundry AIServices (DI + CU) | `ai-{prj}-{env}-{suffix}` |
| イメージレジストリ | Azure Container Registry (Premium) | `acr{prj}{env}{suffix}` |
| ID | System Assigned Managed Identity | 各 Container App のシステム割り当て MI |
| 監視 | Log Analytics + Diagnostic Settings | `log-{prj}-{env}` |
| ネットワーク | VNet + 2 サブネット + 4 Private DNS Zone | `vnet-{prj}-{env}` |

## ディレクトリ構成

```text
OCR-Demo/
├── azure.yaml              # azd プロジェクト定義 + デプロイ hooks
├── requirements-dev.txt    # テスト用依存 (pytest)
├── infra/
│   ├── main.bicep          # サブスクリプションスコープ
│   ├── main.parameters.json
│   └── modules/
│       ├── monitoring.bicep
│       ├── network.bicep
│       ├── privateDns.bicep
│       ├── acr.bicep
│       ├── foundry.bicep
│       ├── containerEnv.bicep
│       ├── containerApps.bicep
│       └── rbac.bicep
├── src/
│   ├── backend/            # FastAPI
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── app/
│   │       ├── __init__.py
│   │       ├── main.py
│   │       └── ocr_service.py
│   └── ui/                 # Streamlit
│       ├── Dockerfile
│       ├── requirements.txt
│       └── app.py
├── tests/                  # pytest
│   ├── conftest.py
│   └── test_api.py
└── docs/                   # 本ドキュメント群
```

## ネットワーク構成

| サブネット | CIDR | 用途 | 設定 |
|---|---|---|---|
| `aca-infra` | 10.10.0.0/23 | Container Apps Environment 統合 | `Microsoft.App/environments` 委任 |
| `pe-subnet` | 10.10.2.0/24 | Private Endpoint 配置 | `privateEndpointNetworkPolicies: Disabled` |

### Private DNS Zone

| Zone | 紐付けリソース |
|---|---|
| `privatelink.cognitiveservices.azure.com` | Foundry (legacy 名前解決) |
| `privatelink.openai.azure.com` | Foundry (Azure OpenAI 互換 API) |
| `privatelink.services.ai.azure.com` | Foundry (新版統一エンドポイント) |
| `privatelink.azurecr.io` | ACR |

## 通信経路

| アクセス元 | 宛先 | 経路 | 認証 |
|---|---|---|---|
| 利用者ブラウザ | UI Container App | インターネット → ACA external ingress (HTTPS) | なし（公開） |
| UI Container App | API Container App | VNet 内 (HTTP, internal FQDN) | なし（VNet 内信頼） |
| API Container App | Foundry エンドポイント | VNet → pe-subnet → Private Endpoint → `*.services.ai.azure.com` | Managed Identity (Bearer) |
| ACA (ANY) | ACR | VNet → pe-subnet → Private Endpoint → `*.azurecr.io` | Managed Identity (`AcrPull`) |
| ACA | Log Analytics | Diagnostic Settings (Azure 内、**パブリック経路**) | リソース間信頼 |
| azd (デプロイ時) | ACR | インターネット → ACR public（一時開放） | Entra ID |

> **⚠️ Log Analytics への通信経路について**: ACA から Log Analytics へのログ送信は Azure Monitor Private Link Scope (AMPLS) が未構成のため**パブリック経路**で行われる。データは Azure 基盤内で TLS 暗号化されるため PoC 用途では許容できるが、本番環境では AMPLS + Private Endpoint を構成し閉域化すること。AMPLS には Private DNS Zone が 5 つ (`monitor.azure.com`, `oms.opinsights.azure.com`, `ods.opinsights.azure.com`, `agentsvc.azure-automation.net`, `blob.core.windows.net`) 必要となり構成が複雑化する点に留意。

## RBAC

RBAC は `rbac.bicep` モジュールで一元管理される。Container App の System Assigned MI が作成された後、その `principalId` に対してロールを割り当てる。

| MI 種別 | スコープ | ロール | 用途 |
|---|---|---|---|
| API Container App (System MI) | Foundry アカウント | `Cognitive Services User` | DI / CU REST 呼び出し |
| API Container App (System MI) | Foundry プロジェクト | `Azure AI User` | 新版プロジェクト API |
| API Container App (System MI) | ACR | `AcrPull` | コンテナイメージ pull |
| UI Container App (System MI) | ACR | `AcrPull` | コンテナイメージ pull |
| Foundry SystemAssigned MI | （プロジェクト操作の自動付与） | - | 内部利用 |

## セキュリティ要点

- Foundry: `publicNetworkAccess: 'Disabled'` + `disableLocalAuth: true` + `networkAcls.defaultAction: 'Deny'`
- ACR: `publicNetworkAccess: 'Disabled'` + `networkRuleSet.defaultAction: 'Deny'` + `adminUserEnabled: false`
- API Container App: `ingress.external: false`（VNet 内のみ）
- アプリ認証: `DefaultAzureCredential` (System Assigned MI を自動検出)
- シークレット: 0 件（Key Vault 不使用 / 接続文字列なし / API キーなし）

## デプロイ時の例外運用

ACR が常時閉域のため、`azd deploy` の remoteBuild は ACR public を一時開放する必要がある。これを `azure.yaml` の `hooks` で自動化:

| Hook | 処理 |
|---|---|
| `postprovision` | Container App の System MI で ACR レジストリを設定 (`az containerapp registry set --identity system`) |
| `predeploy` | `az acr update --public-network-enabled true --default-action Allow` + 30 秒待機 |
| `postdeploy` | `az acr update --public-network-enabled false --default-action Deny` |

## API エンドポイントマッピング

新版 Foundry の統一エンドポイント `https://<account>.services.ai.azure.com/` 配下に以下のパスを提供。

| サービス | パス | API バージョン (既定) |
|---|---|---|
| Document Intelligence | `/documentintelligence/documentModels/{modelId}:analyze` | `2024-11-30` |
| Content Understanding | `/contentunderstanding/analyzers/{analyzerId}:analyze` | `2025-11-01` |
| Project API (Agents 等) | `/api/projects/{projectName}/...` | `2025-04-01-preview` |
