# PoC 前提とプロダクション ベストプラクティス

> **重要**: 本リポジトリは **PoC / 検証目的** で構成されている。Microsoft Foundry の Document Intelligence と Content Understanding を比較検証することが主目的であり、シンプルさ・コスト・展開容易性を優先している。本番運用ではここに挙げる改善が必要となる。

## 設計トレードオフの一覧

| 領域 | 本 PoC の選択 | 本番ベストプラクティス | 理由・例 |
|---|---|---|---|
| **UI 公開** | UI Container App を `external: true` でインターネット公開（認証なし） | App Gateway / Front Door + WAF を前段に配置し、Entra ID (Easy Auth) で認証強制 | 例: Front Door Premium + Private Link Origin で WAF + DDoS 保護を有効化 |
| **API 認証** | UI → API は VNet 内通信のみで認証なし | API 側でも Entra ID トークン検証 / API Management を挟む | 例: APIM の `validate-jwt` policy で UI が取得した user token を検証 |
| **シークレット管理** | 環境変数でリソース名のみ注入（API キー不使用） | 機微値は Key Vault + CSI Driver / Container App secret reference | 例: `secretRef: keyvaultref:https://kv.../secrets/foo,identityref:...` |
| **Foundry エンドポイント** | 単一リージョン (`westus`) | 複数リージョン デプロイ + Front Door でフェイルオーバー | 例: westus / eastus2 双方に Foundry を配置し、リージョン障害時に切替 |
| **ACR 公開制御** | デプロイ時のみ azd hooks で一時 public 化 | ACR は常時閉域、ビルドは VNet 統合された self-hosted runner / Azure DevOps スケールセット で実施 | 例: GitHub Actions の self-hosted runner を VNet 内 VM に配置し、Private Link 経由で push |
| **Container Apps スケール** | min=0 / max=1（コスト優先） | min=2 以上 + ゾーン冗長 + HPA ルール（HTTP同時接続数 / Service Bus キュー長） | 例: `minReplicas: 3, maxReplicas: 30, scaleRules: [{ http: { concurrentRequests: 50 } }]` |
| **データ永続化** | ファイルアップロード結果はメモリ上で破棄 | Blob Storage に原本を保存 + Cosmos DB に解析結果を保存（監査ログ） | 例: 原本 `<sha256>.pdf` + 結果 JSON を顧客テナント単位のコンテナに保存 |
| **観測性** | コンテナ stdout を Log Analytics へ転送するのみ | Application Insights + OpenTelemetry で分散トレース、SLI/SLO ダッシュボード、アラートルール | 例: `azure-monitor-opentelemetry` を Python アプリに組み込み、Foundry REST 呼び出しを依存関係として記録 |
| **CI/CD** | ローカルから `azd up` 手動実行 | GitHub Actions / Azure DevOps で IaC（what-if）→ 承認 → デプロイのパイプライン化、環境分離 (`dev/stg/prod`) | 例: `azd pipeline config` でテンプレ生成、stg→prod は手動承認ゲート |
| **ガバナンス** | RBAC のみ | Azure Policy で命名・タグ・暗号化・リージョン強制、Defender for Cloud 有効化 | 例: `Allowed locations` policy + `Require tag and its value` policy をサブスクリプション割り当て |
| **DR / バックアップ** | バックアップなし | Foundry プロジェクト構成・カスタム analyzer 定義を IaC で再現可能にし、定期 export | 例: Custom analyzer 定義 JSON を Git 管理 + 別リージョンで再作成可能にする |
| **コスト管理** | 監視なし | Budget アラート + Cost Analysis ビュー + 自動スケールイン | 例: 月額 $500 で 80% / 100% アラートを Action Group に紐付け |
| **ネットワーク** | 単一 VNet (10.10.0.0/16) フラット構成 | Hub-Spoke + Azure Firewall で egress 制御、各環境を別 Spoke に分離 | 例: Hub に Firewall + Bastion、Spoke に ACA / Foundry。Firewall ルールで Foundry 以外の egress を拒否 |
| **ログ送信経路** | Log Analytics へのログ送信はパブリック経路（AMPLS 未構成） | Azure Monitor Private Link Scope (AMPLS) + Private Endpoint で閉域化。Private DNS Zone 5 つ (`monitor.azure.com` 等) の追加が必要 | 例: AMPLS を作成し `monitor.azure.com`, `oms.opinsights.azure.com`, `ods.opinsights.azure.com`, `agentsvc.azure-automation.net`, `blob.core.windows.net` の Private DNS Zone を VNet にリンク |
| **コンプライアンス** | ログ保持 30 日（Log Analytics 既定） | 業界規制に応じた長期保持（Storage Account へエクスポート + Immutable Blob） | 例: 7 年保持が必要な金融案件で Immutable Storage + Customer-managed key |
| **イメージ署名** | 未対応 | ACR Notation で署名 + Container Apps の admission ポリシーで未署名イメージを拒否 | 例: `notation sign` を CI に組み込み、prod 環境のみ署名検証必須 |

## 本 PoC の利用範囲

- ✅ 適している: Foundry の DI / CU の機能比較、社内デモ、概念実証、教育用
- ❌ 適していない: 本番ワークロード、機微データ処理、SLA を伴うサービス提供、規制対象業務

本番化を検討する場合は、上記の各項目を要件・コスト・運用体制と照らし合わせて段階的に強化する。具体的なベストプラクティスは [Azure Well-Architected Framework](https://learn.microsoft.com/azure/well-architected/) を参照。
