# Changelog

このプロジェクトの主な変更点を記録します。
フォーマットは [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に、バージョニングは [Semantic Versioning](https://semver.org/lang/ja/) に従います。

All notable changes to this project are documented here, following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- 公開用ドキュメント一式（README 日英版、CONTRIBUTING、CODE_OF_CONDUCT、SECURITY、CHANGELOG）
- GitHub Actions による CI（pytest / cfn-lint / Docker イメージビルド検証）
- Issue テンプレート・Pull Request テンプレート・Dependabot 設定
- `.gitignore` / `.dockerignore`
- MIT ライセンス

### Changed
- `samconfig.toml` の ECR URI からアカウント固有の値を除去し、`<AWS_ACCOUNT_ID>` プレースホルダに戻した

### Removed
- リポジトリから `.aws-sam/` ビルド成果物と `__pycache__/` の追跡を解除

## [0.1.0] - 2026-08-15

初期実装。

### Added
- Input S3 → EventBridge → Step Functions → Lambda → Output S3 のサーバーレス変換パイプライン（AWS SAM）
- 拡張子による3パターン分岐（AnyDoc 変換 / テキストコピー / スキップ）
- [firecrawl-anydoc](https://github.com/firecrawl/anydoc) 0.1.9 による Markdown 変換（コンテナイメージ Lambda）
- 変換結果と並置される `.metadata.json` サイドカーの生成
- Step Functions による最大3回・指数バックオフのリトライと `HandleUnsupported` によるエラー握り込み
- hypothesis によるプロパティテスト 16件 + ユニットテスト 8件
- 詳細設計書（`DESIGN.md`）と仕様書（`.kiro/specs/`）

[Unreleased]: https://github.com/akira-sato22/anydoc-RAG-preprocessor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/akira-sato22/anydoc-RAG-preprocessor/releases/tag/v0.1.0
