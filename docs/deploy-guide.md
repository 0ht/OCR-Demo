# デプロイガイド

本書では、OCR-Demo を Azure 環境へデプロイする手順を、初学者でも追えるように丁寧に説明する。Azure Developer CLI (azd) を主軸に、内部で何が起きているかを順を追って解説する。

> ⚠️ **本手順は PoC / 検証用構成のデプロイです。** 本番ワークロードでは WAF・複数リージョン展開・CI/CD パイプライン化・Key Vault 統合などの追加設計が必要です。差分の一覧は [poc-vs-production.md](poc-vs-production.md) を参照してください。

## Azure Developer CLI (azd) とは

[Azure Developer CLI (azd)](https://learn.microsoft.com/azure/developer/azure-developer-cli/overview) は、Azure アプリケーションのプロビジョニングからデプロイまでを **1 コマンドで完結**させる開発者向け CLI ツールである。

| 特徴 | 説明 |
|---|---|
| **IaC と アプリデプロイの統合** | Bicep / Terraform によるインフラ構築と、コンテナイメージのビルド・デプロイを `azd up` 1 コマンドで実行 |
| **環境管理** | `.azure/<env_name>/` にサブスクリプション ID・リージョン・出力変数等を永続化し、複数環境 (dev/stg/prod) を切り替え可能 |
| **hooks** | `azure.yaml` に `postprovision` / `predeploy` / `postdeploy` 等のフックを定義し、任意のシェルスクリプトを挟める |
| **サービス検出** | `azure.yaml` の `services` セクションと Azure リソースの `azd-service-name` タグで、ソースコードとデプロイ先を自動マッピング |

本プロジェクトで使用する主なコマンド:

| コマンド | 動作 |
|---|---|
| `azd env new <name>` | 新しい環境を作成 |
| `azd env set <KEY> <VALUE>` | 環境変数を設定（Bicep パラメータ・Container App 環境変数に展開される） |
| `azd up` | provision + deploy を一括実行（初回向け） |
| `azd provision` | Bicep のみ適用（インフラ変更時） |
| `azd deploy [service]` | アプリのみデプロイ（コード変更時） |
| `azd down --purge --force` | 全リソース削除（検証完了時） |

詳細は [azd 公式ドキュメント](https://learn.microsoft.com/azure/developer/azure-developer-cli/) を参照。

## クイックスタート

ここでは「とにかく動かす」ための最短手順を示す。詳細は後続の各セクションで掘り下げる。

### PowerShell (Windows)

```powershell
# 1. azd 環境を新規作成（ローカルの .azure/<env_name>/ に状態が保存される）
azd env new ocr-demo

# 2. デプロイ先リージョンと環境略号を設定
#    - AZURE_LOCATION: Foundry / DI / CU が同時提供されるリージョン
#    - ENVIRONMENT   : dev / stg / prod のいずれか（リソース命名に使われる）
azd env set AZURE_LOCATION westus
azd env set ENVIRONMENT dev

# 3. プロビジョニング (Bicep) + アプリデプロイ (azd deploy) を一括実行
azd up
```

### sh (Linux / macOS / WSL)

```bash
azd env new ocr-demo
azd env set AZURE_LOCATION westus
azd env set ENVIRONMENT dev
azd up
```

正常終了すると `azd up` の出力末尾に `SERVICE_UI_ENDPOINT` の URL が表示される。これをブラウザで開くと UI にアクセスできる。`SERVICE_API_INTERNAL_ENDPOINT` は VNet 内のみ到達可能なため、ブラウザからは直接アクセスできない（UI が内部で呼び出す）。

## 前提条件

| ツール | バージョン | 用途 |
|---|---|---|
| Azure CLI | 2.60 以上 | 認証、azd 内部呼び出し、hook 内の `az` 実行 |
| azd | 1.10 以上 | プロビジョニング + デプロイのオーケストレーション |
| Bicep CLI | 0.30 以上 | IaC コンパイル（azd が同梱） |
| Python | 3.11 以上 | ローカル実行 / pytest 実行時のみ |

事前に以下を済ませておくこと:

```powershell
az login                              # 対話ログイン
az account set --subscription <id>    # 利用するサブスクリプションを選択
```

azd は `az login` のセッションを再利用するため、別途 `azd auth login` は通常不要だが、エラーが出る場合は `azd auth login` も実行する。

## ディレクトリツリー（デプロイ関連）

デプロイ動作を理解するうえで重要なファイルだけを抜粋する。

```text
OCR-Demo/
├── azure.yaml              # azd プロジェクト定義 + postprovision/predeploy/postdeploy hooks
├── infra/
│   ├── main.bicep          # サブスクリプションスコープのエントリポイント
│   ├── main.parameters.json# azd 環境変数 → Bicep パラメータのマッピング
│   └── modules/
│       ├── monitoring.bicep    # Log Analytics
│       ├── network.bicep       # VNet + 2 サブネット
│       ├── privateDns.bicep    # 4 つの Private DNS Zone + VNet link
│       ├── acr.bicep           # ACR (Premium / Private)
│       ├── foundry.bicep       # AIServices アカウント + プロジェクト
│       ├── containerEnv.bicep  # ACA Environment + DiagnosticSettings
│       ├── containerApps.bicep # API / UI Container App (System MI)
│       └── rbac.bicep          # RBAC ロール割り当て (AcrPull / CogSvcUser / AIUser)
└── src/
    ├── backend/Dockerfile  # FastAPI (Python) のコンテナ定義
    └── ui/Dockerfile       # Streamlit (Python) のコンテナ定義
```

`azure.yaml` の `services.api` / `services.ui` セクションが、`src/backend` / `src/ui` をそれぞれ Container App 上の `azd-service-name=api` / `azd-service-name=ui` タグに紐付け、`azd deploy` 時のターゲットを決定する。

## 環境変数

azd 環境変数は `.azure/<env_name>/.env` に永続化され、Bicep パラメータと Container App の環境変数に展開される。

| 変数 | 必須 | 既定値 | 説明 |
|---|---|---|---|
| `AZURE_ENV_NAME` | ✓ | (azd 入力) | プロジェクト名。リソース命名の `{prj}` に展開される |
| `AZURE_LOCATION` | ✓ | `westus` | デプロイリージョン。Foundry / DI / CU が同時提供される地域を選ぶ |
| `ENVIRONMENT` | - | `dev` | 環境略号 (`dev` / `stg` / `prod`)。命名の `{env}` に展開 |
| `AZURE_RESOURCE_GROUP` | - | `rg-{prj}-{env}` | リソースグループ名。明示指定時は既存 RG を使用可 |
| `FOUNDRY_PROJECT_NAME` | - | `default-project` | 新版 Foundry のプロジェクト（子リソース）名 |
| `CONTENT_UNDERSTANDING_ANALYZER_ID` | - | `prebuilt-read` | CU で利用する prebuilt / custom analyzer ID |
| `CONTENT_UNDERSTANDING_API_VERSION` | - | `2025-11-01` | CU REST API バージョン |
| `DOCUMENT_INTELLIGENCE_MODEL_ID` | - | `prebuilt-read` | DI で利用する prebuilt モデル ID |
| `DOCUMENT_INTELLIGENCE_API_VERSION` | - | `2024-11-30` | DI REST API バージョン |

**設定例**:

```powershell
# CU の analyzer を変更する場合（Bicep に反映するため azd provision が必要）
azd env set CONTENT_UNDERSTANDING_ANALYZER_ID prebuilt-documentSearch
azd provision
```

API キーや接続文字列は一切使用しない。すべて Managed Identity 経由で Entra ID 認証する。

## 作成されるリソース

`azd up` 1 回で作成されるリソースの一覧と命名規則。`{prj}` = `AZURE_ENV_NAME`、`{env}` = `ENVIRONMENT`、`{6char}` = `uniqueString(rg.id)` の先頭 6 文字。

| 種別 | 名前パターン | 例 | 役割 |
|---|---|---|---|
| Resource Group | `rg-{prj}-{env}` | `rg-ocr-demo-dev` | リソースを束ねる論理コンテナ |
| VNet | `vnet-{prj}-{env}` | `vnet-ocr-demo-dev` | ACA / Private Endpoint 用ネットワーク |
| Log Analytics | `log-{prj}-{env}` | `log-ocr-demo-dev` | ACA コンテナログの集約先 |
| ACR (Premium) | `acr{prj}{env}{6char}` | `acrocrdemodevbuhhb3` | コンテナイメージ格納（Premium 必須） |
| Foundry (AIServices) | `ai-{prj}-{env}-{6char}` | `ai-ocr-demo-dev-buhhb3` | DI / CU REST の提供元 |
| Foundry Project | `{foundry}/default-project` | - | 新版 Foundry のプロジェクト |
| ACA Environment | `cae-{prj}-{env}` | `cae-ocr-demo-dev` | Container Apps の実行環境（VNet 統合） |
| Container App (API) | `ca-{prj}-{env}-api` | `ca-ocr-demo-dev-api` | FastAPI バックエンド（internal, System MI） |
| Container App (UI) | `ca-{prj}-{env}-ui` | `ca-ocr-demo-dev-ui` | Streamlit UI（external, System MI） |
| Private Endpoint (ACR) | `pe-{acr}` | - | ACA → ACR の private 通信入口 |
| Private Endpoint (Foundry) | `pe-{ai}` | - | API → Foundry の private 通信入口 |
| Private DNS Zones | 4 種 | `privatelink.azurecr.io` 他 | private IP への名前解決 |

## アクセス経路と認証

「誰が・どこから・どう認証して・どこへ」を整理する。

| アクセス元 | 手段 | 認証 |
|---|---|---|
| 利用者 | ブラウザ → UI external ingress (HTTPS) | なし（公開エンドポイント） |
| UI Container App | API internal FQDN (HTTP) | なし（VNet 内 / 同一 ACA Environment） |
| API Container App | Foundry REST (HTTPS) via Private Endpoint | System Assigned MI が発行する Bearer トークン |
| ACA (UI / API) | ACR pull via Private Endpoint | System Assigned MI (`AcrPull` ロール) |
| azd (デプロイ時) | ACR public（hook で一時開放） | 開発者の Entra ID（`az login` セッション） |

API → Foundry の認証は、Python 側の [`DefaultAzureCredential`](src/backend/app/ocr_service.py#L8) が Container App の System Assigned MI を自動検出してトークンを取得し、`Authorization: Bearer ...` ヘッダで REST 呼び出しする。

## デプロイ運用

### 初回プロビジョニング + デプロイ

`azd up` は内部的に以下を順に実行する:

1. **Package**: `services.*.docker.path` の Dockerfile を検出（remoteBuild のため実ビルドは ACR Tasks 側）
2. **Provision**: `infra/main.bicep` をコンパイルし、サブスクリプションスコープで `New-AzDeployment` 相当を実行
3. **Hooks (postprovision)**: Container App の System MI で ACR レジストリを設定 (`az containerapp registry set --identity system`)
4. **Hooks (predeploy)**: ACR public 開放
5. **Deploy**: ソースコードを ACR Tasks に upload → ACR でビルド → イメージプッシュ → Container App revision 更新
6. **Hooks (postdeploy)**: ACR を閉域へ戻す

```powershell
azd up
```

### インフラのみ更新

Bicep を編集した場合や環境変数を Container App に反映したい場合に使う。アプリイメージは更新されない。

```powershell
azd provision
```

### アプリのみデプロイ

ソースコード変更を素早く反映したい場合に使う。

```powershell
azd deploy           # 全サービス
azd deploy api       # API のみ
azd deploy ui        # UI のみ
```

### 環境のクリーンアップ

検証完了後にリソースを完全削除する。`--purge` を付けないと Foundry / Key Vault などの論理削除データが残り、同名で再作成できなくなるため必ず付与する。

```powershell
azd down --purge --force
```

## hooks による ACR 一時開放の動作

ACR は常時閉域 (`publicNetworkAccess: Disabled` + `defaultAction: Deny`) に設定されている。一方で `azd deploy` のリモートビルドは ACR Tasks のサービスエンドポイントへ HTTPS でアクセスするため、デプロイ中だけ public を有効化する必要がある。これを `azure.yaml` の `hooks` で完全自動化している。

実行順序:

1. **predeploy**:
   ```bash
   az acr update -n $AZURE_CONTAINER_REGISTRY_NAME --public-network-enabled true --default-action Allow
   sleep 30   # ネットワーク変更の伝播待ち
   ```
2. **deploy** (azd 本体): ACR Tasks がソースをビルドしイメージをプッシュ → Container App の image を更新
3. **postdeploy**:
   ```bash
   az acr update -n $AZURE_CONTAINER_REGISTRY_NAME --public-network-enabled false --default-action Deny
   ```

POSIX 環境 (`shell: sh`) と Windows 環境 (`shell: pwsh`) の両方の hook が定義されているため、OS を意識せず動作する。

postdeploy が何らかの理由で失敗した場合は、ACR が public のまま残る。手動で閉域に戻す:

```powershell
$acr = azd env get-value AZURE_CONTAINER_REGISTRY_NAME
$rg  = azd env get-value AZURE_RESOURCE_GROUP
az acr update -n $acr -g $rg --public-network-enabled false --default-action Deny
```

## トラブルシュート（クイック）

詳細は [operations.md](operations.md) を参照。本書では「デプロイ時に遭遇しやすい」典型例のみを示す。

| 症状 | 原因 | 対処 |
|---|---|---|
| `azd deploy` で `denied: client with IP ... is not allowed` | predeploy hook が起動していない（旧 azure.yaml）／30 秒の伝播待ちが不十分 | 最新 azure.yaml を取得し再実行。改善しない場合 hook 内 `sleep` を 60 秒に延長 |
| Container App が `ImagePullBackOff` | ACR Private Endpoint / DNS Zone Group が未完成 | `azd provision` を再実行し、完了後 `az containerapp revision restart` |
| API → Foundry が `401` / `403` | RBAC 割り当ての反映待ち（最大数分） | 数分待ち、改善しなければ `az role assignment list --assignee {clientId}` で確認 |
| API → Foundry が `Name resolution failed` | Private DNS Zone と VNet のリンク欠落 | [privateDns.bicep](../infra/modules/privateDns.bicep) のリンクリソース存在を確認し再 provision |
| `azd up` が `A resource with this name already exists` | 同名リソースの論理削除データが残存 | `azd down --purge --force` 実施後に再 `azd up`、または `AZURE_ENV_NAME` を変更 |
| `azd deploy` が完了するが UI に古い画面 | Container App が古い revision のまま | `az containerapp revision list -g $rg -n {ca-name}` で active revision を確認 |
