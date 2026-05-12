# 運用ガイド

> ⚠️ **本ガイドは PoC / 検証用構成を前提とした運用です。** 本番運用には Application Insights による分散トレース、Budget アラート、Defender for Cloud、DR 設計などの強化が必要です。詳細は [poc-vs-production.md](poc-vs-production.md) を参照してください。

## 監視

### ログ参照

ACA のコンテナログは Diagnostic Settings 経由で Log Analytics に転送される。

```powershell
$rg  = azd env get-value AZURE_RESOURCE_GROUP
$ws  = (az monitor log-analytics workspace list -g $rg --query "[0].name" -o tsv)

# API の最新 50 行
az monitor log-analytics query `
  --workspace (az monitor log-analytics workspace show -g $rg -n $ws --query customerId -o tsv) `
  --analytics-query "ContainerAppConsoleLogs_CL | where ContainerAppName_s == 'ca-ocr-demo-dev-api' | top 50 by TimeGenerated desc | project TimeGenerated, Log_s"
```

### リソース状態

```powershell
az containerapp list -g $rg -o table
az containerapp revision list -g $rg -n ca-ocr-demo-dev-api -o table
```

## トラブルシュート

| 症状 | 切り分け | 対処 |
|---|---|---|
| UI にアクセスしても応答なし | `az containerapp show -g $rg -n ca-{prj}-{env}-ui --query properties.runningStatus` | revision を再起動 / ログ確認 |
| API → Foundry で `401` | System MI のロール割り当てを `az role assignment list --assignee {principalId}` で確認 | `azd provision` 再実行 |
| API → Foundry で `Name resolution failed` | `nslookup ai-{prj}-{env}-{suffix}.services.ai.azure.com` を ACA exec で実行し private IP が返るか確認 | Private DNS Zone の VNet link を確認 |
| `azd deploy` が ACR でブロック | postdeploy hook で ACR が閉域に戻ったかを確認 | hook 失敗時は手動で `--public-network-enabled true` |
| イメージ pull で `unauthorized` | Container App の System MI の `AcrPull` ロール割り当てを確認 | `azd provision` 再実行で `rbac.bicep` を再適用 |

### コンテナへのデバッグアクセス

```powershell
az containerapp exec -g $rg -n ca-ocr-demo-dev-api --command "/bin/sh"
```

VNet 内の名前解決テスト（API コンテナ内）:

```bash
nslookup $FOUNDRY_ENDPOINT  # private IP が返れば DNS OK
curl -sS -o /dev/null -w "%{http_code}\n" "$FOUNDRY_ENDPOINT/documentintelligence/info?api-version=2024-11-30"
```

## 更新作業

### コード変更のみ反映

```powershell
azd deploy api    # API のみ
azd deploy ui     # UI のみ
azd deploy        # 両方
```

### Bicep 変更のみ反映

```powershell
azd provision
```

### azd 環境変数の更新

```powershell
azd env set DOCUMENT_INTELLIGENCE_API_VERSION 2024-11-30
azd provision   # ACA env 変数を更新
```

## 復旧手順

### postdeploy hook が失敗し ACR が public のままになった場合

```powershell
$acr = azd env get-value AZURE_CONTAINER_REGISTRY_NAME
$rg  = azd env get-value AZURE_RESOURCE_GROUP
az acr update -n $acr -g $rg --public-network-enabled false --default-action Deny
```

### Container App revision を 1 つ前に戻す

```powershell
$prev = az containerapp revision list -g $rg -n ca-ocr-demo-dev-api `
  --query "[?properties.active==false] | [0].name" -o tsv
az containerapp revision activate -g $rg -n ca-ocr-demo-dev-api --revision $prev
```

### 環境の完全削除

```powershell
azd down --purge --force
```

`--purge` で Foundry / ACR の論理削除データも消去される。再作成時の名前競合を避けるため必ず付与する。

## セキュリティ運用

| 項目 | 確認頻度 | コマンド |
|---|---|---|
| Foundry の `disableLocalAuth` | デプロイ後 | `az cognitiveservices account show -n {ai} -g $rg --query properties.disableLocalAuth` |
| ACR の `publicNetworkAccess` | デプロイ後 | `az acr show -n $acr -g $rg --query publicNetworkAccess` |
| MI のロール | 月次 | `az role assignment list --assignee $(az containerapp show -g $rg -n ca-{prj}-{env}-api --query identity.principalId -o tsv) -o table` |
| Foundry / ACR の Private Endpoint 接続状態 | 月次 | `az network private-endpoint show -g $rg -n {pe-name} --query "privateLinkServiceConnections[0].properties.privateLinkServiceConnectionState.status"` |

> **⚠️ Log Analytics のログ送信経路について**: 現在 Azure Monitor Private Link Scope (AMPLS) は未構成のため、ACA から Log Analytics へのログ送信は**パブリック経路**で行われている。Azure 基盤内で TLS 暗号化されるため PoC 用途では実害は小さいが、本番環境では AMPLS を追加し閉域化すること。

## コスト最適化のヒント

- 開発環境では ACA `minReplicas: 0` に変更してアイドル時の料金を削減（応答に cold start 発生）
- ACR Premium はネットワーク機能のため必須。リテンションポリシーで古いタグを自動削除
- Log Analytics の retention を必要最小限に
