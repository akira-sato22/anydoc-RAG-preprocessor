# 実装計画: AnyDoc RAG前処理パイプライン

## 概要

AWS SAMを使用してRAG文書前処理パイプラインを構築する。S3イベント駆動で起動し、Step Functions経由でLambda関数を実行、firecrawl-anydocによるドキュメント変換を行う。実装言語はPython。

## タスク

- [x] 1. プロジェクト構造とSAMテンプレートの基盤構築
  - [x] 1.1 SAMテンプレート（template.yaml）の作成
    - Parameters（Environment, Project）の定義
    - Input S3 Bucket の定義（SSE-S3暗号化、EventBridge通知有効化）
    - Output S3 Bucket の定義（SSE-S3暗号化）
    - スタック名ベースのリソース名自動生成
    - _Requirements: 9.1, 9.2, 9.4, 9.6_
  - [x] 1.2 Lambda関数リソースの定義（template.yaml）
    - ConvertDocument Lambda（コンテナイメージ方式）
    - メモリ1024MB、タイムアウト300秒、ReservedConcurrentExecutions=10
    - IAMポリシー: Input Bucket→s3:GetObject、Output Bucket→s3:PutObject
    - 環境変数: OUTPUT_BUCKET_NAME
    - _Requirements: 9.3, 9.5_
  - [x] 1.3 Step Functions ステートマシンの定義（template.yaml）
    - StateMachineType: STANDARD
    - DefinitionUri: statemachine/convert.asl.json
    - IAMロール: Lambda Invoke 権限
    - _Requirements: 8.4, 9.1_
  - [x] 1.4 EventBridgeルールの定義（template.yaml）
    - Input BucketのObjectCreatedイベントをトリガー
    - ターゲット: Step Functions State Machine
    - フィルタリングなし（全ObjectCreatedイベント）
    - _Requirements: 1.1, 1.2, 1.3_
  - [x] 1.5 samconfig.toml の作成
    - デフォルトパラメータの設定
    - _Requirements: 9.6_

- [x] 2. Step Functions ASL定義の作成
  - [x] 2.1 statemachine/convert.asl.json の作成
    - ConvertDocument Task状態（Lambda呼び出し）
    - Retry設定: ErrorEquals=[States.TaskFailed, Lambda.ServiceException], IntervalSeconds=2, MaxAttempts=3, BackoffRate=2.0
    - Catch設定: ErrorEquals=[States.ALL], Next=HandleUnsupported
    - HandleUnsupported Pass状態
    - Succeed 終了状態
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 3. チェックポイント - インフラ定義の確認
  - SAMテンプレートの構文チェック（`sam validate`）
  - 全テストがパスすることを確認。不明点があればユーザーに質問する。

- [x] 4. Lambda関数のコアロジック実装
  - [x] 4.1 ファイル分類ロジックの実装（src/convert_document/app.py）
    - FilePattern Enum定義
    - ANYDOC_EXTENSIONS, TEXT_EXTENSIONS 定数定義
    - classify_file() 関数の実装
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - [x] 4.2 ファイル分類のプロパティテスト作成
    - **Property 1: ファイル分類の完全性と正確性**
    - **Property 2: ファイル分類の決定性**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**
  - [x] 4.3 出力キー生成ロジックの実装（src/convert_document/app.py）
    - get_output_key() 関数の実装
    - get_metadata_key() 関数の実装
    - _Requirements: 7.1, 7.2, 7.3_
  - [x] 4.4 出力キー生成のプロパティテスト作成
    - **Property 3: 出力キー命名の非衝突性**
    - **Validates: Requirements 7.1, 7.2, 7.3**
  - [x] 4.5 メタデータ生成ロジックの実装（src/convert_document/app.py）
    - generate_metadata() 関数の実装
    - ISO 8601 UTC形式の日時生成
    - source_uri フォーマット生成
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - [x] 4.6 メタデータ生成のプロパティテスト作成
    - **Property 4: メタデータ構造の完全性**
    - **Property 5: メタデータのsource_uriフォーマット整合性**
    - **Property 6: メタデータのconverted_at形式**
    - **Validates: Requirements 6.1, 6.2, 6.3**

- [x] 5. Lambda関数のS3操作と変換処理の実装
  - [x] 5.1 AnyDoc変換処理の実装（src/convert_document/app.py）
    - S3からファイルダウンロード（/tmp）
    - firecrawl-anydoc による変換呼び出し
    - 変換結果のMarkdownをOutput Bucketに格納
    - メタデータJSONをOutput Bucketに格納
    - 変換失敗時の例外raise
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - [x] 5.2 テキストコピー処理の実装（src/convert_document/app.py）
    - S3からファイル取得
    - 同一キーでOutput Bucketにコピー
    - メタデータJSON生成・格納
    - _Requirements: 4.1, 4.2, 4.3_
  - [x] 5.3 スキップ処理の実装（src/convert_document/app.py）
    - 構造化ログ出力（バケット名、キー、拡張子）
    - レスポンス返却（status=skipped）
    - _Requirements: 5.1, 5.2, 5.3_
  - [x] 5.4 lambda_handler の実装（src/convert_document/app.py）
    - イベントからバケット名・オブジェクトキーの取得
    - classify_file()呼び出しによるパターン判定
    - パターンに応じた処理関数の呼び出し
    - メタデータ格納失敗時のエラーハンドリング（ログのみ）
    - _Requirements: 1.2, 6.5_
  - [x] 5.5 Lambda handler のユニットテスト作成（tests/unit/test_convert_document.py）
    - 各パターンのハンドラ動作テスト（モック使用）
    - エラーケースのテスト
    - メタデータ格納失敗時の非エラー動作テスト
    - _Requirements: 3.4, 3.5, 4.3, 5.2, 6.5_

- [x] 6. Dockerfileと依存関係の設定
  - [x] 6.1 Dockerfile の作成（src/convert_document/Dockerfile）
    - public.ecr.aws/lambda/python ベースイメージ
    - firecrawl-anydoc==0.1.9 のインストール
    - app.py のコピーとCMD設定
    - _Requirements: 9.1_
  - [x] 6.2 requirements.txt の作成（src/convert_document/requirements.txt）
    - firecrawl-anydoc==0.1.9
    - _Requirements: 9.1_

- [x] 7. 最終チェックポイント - 全体統合確認
  - 全テストがパスすることを確認。不明点があればユーザーに質問する。
  - `sam validate` でテンプレートの構文チェック
  - `sam build` でビルド可能であることを確認

## 備考

- `*` マーク付きタスクはオプション（スキップ可能）
- 各タスクは特定の要件に対するトレーサビリティを持つ
- チェックポイントでインクリメンタルな検証を実施
- プロパティテストは正確性プロパティの普遍的な検証、ユニットテストは具体的な例とエッジケースの検証を行う
