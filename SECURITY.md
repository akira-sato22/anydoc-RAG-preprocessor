# セキュリティポリシー / Security Policy

## 脆弱性の報告 / Reporting a Vulnerability

**脆弱性を公開 Issue に書かないでください。** / **Please do not report vulnerabilities in public issues.**

GitHub の非公開報告機能を使ってください。

Use GitHub's private vulnerability reporting:

**[Report a vulnerability](https://github.com/akira-sato22/anydoc-RAG-preprocessor/security/advisories/new)**

（リポジトリの **Security** タブ → **Report a vulnerability** からも辿れます。 / You can also reach it via the repository's **Security** tab → **Report a vulnerability**.）

### 報告に含めてほしいこと / What to include

- 脆弱性の種類と影響範囲 / Type of issue and its impact
- 再現手順 / Steps to reproduce
- 影響を受ける設定・バージョン / Affected configuration or version
- 可能であれば修正案 / A suggested fix, if you have one

**機密情報を報告に含めないでください** — 実際の AWS アカウント ID、アクセスキー、実データのドキュメントなどは、再現に必要であってもマスクしてお送りください。

**Do not include sensitive material** in a report — redact real AWS account IDs, access keys, and any actual documents, even if they're part of the reproduction.

### 対応の流れ / Response process

これは個人が余暇に運営しているプロジェクトです。SLA は保証できませんが、以下を目安としています。

This is a personal project maintained in spare time. No SLA is guaranteed, but the intent is:

| ステップ / Step | 目安 / Target |
|---|---|
| 受領の連絡 / Acknowledgement | 7日以内 / within 7 days |
| 初期評価 / Initial assessment | 14日以内 / within 14 days |
| 修正と公開 / Fix and disclosure | 深刻度による / depends on severity |

修正の公開後、報告者としてクレジットさせていただきます（希望されない場合は匿名にします）。

Reporters are credited in the advisory once a fix ships, unless you prefer to stay anonymous.

## サポート対象 / Supported versions

`main` ブランチの最新コミットのみをサポート対象とします。過去のコミットへのバックポートは行いません。

Only the latest commit on `main` is supported. Fixes are not backported.

## このプロジェクトのセキュリティ上の性質 / Security characteristics

デプロイして使う方に知っておいてほしい点です。

Things worth knowing before you deploy this:

- **データは AWS アカウント外に出ません。** 変換は Lambda コンテナ内で完結し、外部 API への送信はありません。 / **No data leaves your AWS account.** Conversion happens entirely inside the Lambda container; nothing is sent to an external API.
- **S3 バケットは SSE-S3 (AES256) で暗号化**されます。より強い要件があれば SSE-KMS への変更を検討してください。 / **Buckets use SSE-S3 (AES256).** Switch to SSE-KMS if you have stronger requirements.
- **Lambda の IAM 権限は最小限**です。入力バケットの `s3:GetObject` と出力バケット配下の `s3:PutObject` のみで、他のリソースにはアクセスできません。 / **The Lambda's IAM permissions are minimal** — `s3:GetObject` on the input bucket and `s3:PutObject` under the output bucket, nothing else.
- **バケットはパブリックアクセスを許可していません**が、デプロイ後にアカウントレベルの Block Public Access が有効になっていることを確認することを推奨します。 / **Buckets are not public**, but confirming account-level Block Public Access after deployment is recommended.
- **信頼できないファイルの変換にはリスクが伴います。** 変換エンジン（[firecrawl/anydoc](https://github.com/firecrawl/anydoc)）は未検証の入力をパースします。不特定多数からのアップロードを受け付ける構成にする場合は、この点を織り込んでください。 / **Converting untrusted files carries risk.** The conversion engine parses unvalidated input. Factor this in before accepting uploads from untrusted sources.
- **CloudWatch Logs にはオブジェクトキーが記録されます。** ファイル名に機密情報を含めないでください。 / **Object keys are written to CloudWatch Logs.** Don't put secrets in filenames.
