# 要件定義書

## はじめに

本文書は、RAG（Retrieval-Augmented Generation）のための文書前処理パイプラインの要件を定義する。S3に配置された各種オフィス文書・PDF等をMarkdown化し、後続のRAGインデクシング処理が利用できる形でOutput S3 Bucketに格納するシステムの機能要件および非機能要件を規定する。

## 用語集

- **Pipeline**: 入力S3バケットのObjectCreatedイベントから出力S3バケットへの格納までの一連の処理フロー
- **ConvertDocument_Lambda**: ファイル分類と変換処理を一括で実行するAWS Lambda関数
- **State_Machine**: Step Functions標準タイプのステートマシン。Lambda呼び出し、リトライ制御、エラーハンドリングを行う
- **Input_Bucket**: 変換対象の原本ファイルを格納するS3バケット
- **Output_Bucket**: 変換済みMarkdownファイルおよびメタデータを格納するS3バケット
- **AnyDoc**: firecrawl-anydoc ライブラリ。Rust製のMarkdown変換エンジン（バージョン0.1.9）
- **FilePattern**: ファイル分類の結果を表す列挙型（ANYDOC_CONVERT, TEXT_COPY, SKIP）
- **Metadata_JSON**: 変換結果のトレーサビリティ情報を格納するサイドカーJSONファイル

## 要件

### 要件1: イベント駆動によるパイプライン起動

**ユーザーストーリー:** インフラ運用者として、S3へのファイルアップロードを契機に自動的に変換処理を開始したい。手動操作なしで新規ファイルが処理されるようにするため。

#### 受入基準

1. WHEN Input_Bucket にオブジェクトが作成された場合（PutObject, CompleteMultipartUpload）、THE Pipeline SHALL EventBridgeルール経由でState_Machineの実行を開始する
2. WHEN State_Machine が起動される場合、THE Pipeline SHALL イベントからバケット名とオブジェクトキーをState_Machineの入力として渡す
3. THE EventBridge ルール SHALL Input_Bucket の全てのObjectCreatedイベントを対象とする（プレフィックス/サフィックスによるフィルタリングは行わない）

### 要件2: ファイル分類

**ユーザーストーリー:** 開発者として、入力ファイルの拡張子に基づいて適切な処理パターンに振り分けたい。ファイル種別に応じた最適な処理を実行するため。

#### 受入基準

1. WHEN オブジェクトキーの拡張子が `.doc`, `.docx`, `.docm`, `.ppt`, `.pps`, `.pot`, `.pptx`, `.pptm`, `.ppsx`, `.ppsm`, `.xls`, `.xlsx`, `.xlsm`, `.xlsb`, `.odt`, `.ods`, `.odp`, `.rtf`, `.epub`, `.csv`, `.pdf` のいずれかである場合、THE ConvertDocument_Lambda SHALL 当該ファイルをパターン①（AnyDoc変換）に分類する
2. WHEN オブジェクトキーの拡張子が `.txt` または `.md` である場合、THE ConvertDocument_Lambda SHALL 当該ファイルをパターン②（テキストコピー）に分類する
3. WHEN オブジェクトキーの拡張子が上記のいずれにも該当しない場合、THE ConvertDocument_Lambda SHALL 当該ファイルをパターン③（スキップ）に分類する
4. THE ConvertDocument_Lambda SHALL 全てのオブジェクトキーに対して必ずいずれかのパターンに分類し、未分類の状態を発生させない
5. WHEN 同一の拡張子を持つオブジェクトキーが複数回処理される場合、THE ConvertDocument_Lambda SHALL 常に同一の分類結果を返す

### 要件3: AnyDoc変換処理（パターン①）

**ユーザーストーリー:** 開発者として、オフィス文書やPDFをMarkdown形式に変換したい。RAGインデクシング処理で利用可能なテキストデータを生成するため。

#### 受入基準

1. WHEN ファイルがパターン①に分類された場合、THE ConvertDocument_Lambda SHALL Input_Bucketから `/tmp` にファイルをダウンロードし、firecrawl-anydoc を用いてMarkdownに変換する
2. WHEN 変換が成功した場合、THE ConvertDocument_Lambda SHALL 変換結果のMarkdownファイルを Output_Bucket に `{元のキー}.md` というキーで格納する
3. WHEN 変換が成功した場合、THE ConvertDocument_Lambda SHALL メタデータJSONファイルを Output_Bucket に `{元のキー}.md.metadata.json` というキーで格納する
4. WHEN 変換が成功した場合、THE ConvertDocument_Lambda SHALL `{"status": "converted"}` を返却する
5. WHEN 変換が失敗した場合（暗号化、破損等）、THE ConvertDocument_Lambda SHALL 例外をraiseし、State_MachineのCatch機構で捕捉させる

### 要件4: テキストコピー処理（パターン②）

**ユーザーストーリー:** 開発者として、既にテキスト形式のファイルはそのままOutput Bucketに格納したい。不要な変換処理を省略して効率的に処理するため。

#### 受入基準

1. WHEN ファイルがパターン②に分類された場合、THE ConvertDocument_Lambda SHALL Input_Bucketから当該ファイルを取得し、同一キーでOutput_Bucketにコピーする
2. WHEN コピーが完了した場合、THE ConvertDocument_Lambda SHALL メタデータJSONファイルを Output_Bucket に `{元のキー}.metadata.json` というキーで格納する
3. WHEN コピーが完了した場合、THE ConvertDocument_Lambda SHALL `{"status": "copied"}` を返却する

### 要件5: スキップ処理（パターン③）

**ユーザーストーリー:** 運用者として、非対応ファイルがアップロードされた場合にエラーとせず正常にスキップしたい。不要なアラームを回避するため。

#### 受入基準

1. WHEN ファイルがパターン③に分類された場合、THE ConvertDocument_Lambda SHALL CloudWatch Logsにスキップした旨（バケット名、キー、拡張子）を構造化ログで記録する
2. WHEN ファイルがパターン③に分類された場合、THE ConvertDocument_Lambda SHALL `{"status": "skipped", "reason": "unsupported_extension"}` を返却する
3. WHEN ファイルがパターン③に分類された場合、THE ConvertDocument_Lambda SHALL Output_Bucketへの書き込みを一切行わない

### 要件6: メタデータ生成

**ユーザーストーリー:** RAGシステム運用者として、変換結果のトレーサビリティ情報を取得したい。元ファイルの追跡と変換品質の監視のため。

#### 受入基準

1. THE ConvertDocument_Lambda SHALL メタデータJSONに以下の全フィールドを含める: `source_bucket`, `source_key`, `source_uri`, `converted_at`, `anydoc_version`, `file_size_bytes`, `conversion_duration_ms`
2. THE ConvertDocument_Lambda SHALL `source_uri` フィールドを `s3://{source_bucket}/{source_key}` 形式で生成する
3. THE ConvertDocument_Lambda SHALL `converted_at` フィールドを ISO 8601 UTC形式（例: `2026-08-14T12:34:56Z`）で生成する
4. THE ConvertDocument_Lambda SHALL `anydoc_version` フィールドに `"0.1.9"` を設定する
5. WHEN メタデータJSONの格納に失敗した場合、THE ConvertDocument_Lambda SHALL Markdownファイル自体は格納済みのため全体を失敗扱いにせず、ログ出力のみ行う

### 要件7: 出力キー命名規則

**ユーザーストーリー:** 開発者として、入力ファイルと出力ファイルの対応関係を明確にしたい。ファイル追跡と同名ファイルの衝突回避のため。

#### 受入基準

1. WHEN パターン①の変換が成功した場合、THE ConvertDocument_Lambda SHALL 出力Markdownのキーを `{入力キー}.md` とする（例: `documents/report.docx` → `documents/report.docx.md`）
2. WHEN パターン②のコピーが完了した場合、THE ConvertDocument_Lambda SHALL 出力ファイルのキーを入力キーと同一にする
3. THE ConvertDocument_Lambda SHALL 異なる入力キーに対して異なる出力キーを生成し、キーの衝突を発生させない
4. WHEN 同一キーのファイルが再度PUTされた場合、THE ConvertDocument_Lambda SHALL 出力MarkdownおよびメタデータJSONを上書きする（冪等性）

### 要件8: Step Functions オーケストレーション

**ユーザーストーリー:** 運用者として、変換処理のリトライ制御と失敗ハンドリングを自動化したい。一時的なエラーからの回復と安定した運用のため。

#### 受入基準

1. WHEN ConvertDocument_Lambda がS3スロットリング等の一時的なエラーで失敗した場合、THE State_Machine SHALL 最大3回、指数バックオフ（IntervalSeconds=2, BackoffRate=2.0）でリトライする
2. WHEN ConvertDocument_Lambda が例外をraiseした場合（リトライ上限超過を含む）、THE State_Machine SHALL Catchで捕捉し HandleUnsupported 状態に遷移する
3. THE State_Machine SHALL 全てのパターン（変換成功、コピー成功、スキップ、変換失敗）において正常終了（Succeed）する
4. THE State_Machine SHALL Standard タイプで作成し、全実行履歴を記録する

### 要件9: インフラストラクチャ構成

**ユーザーストーリー:** 開発者として、AWS SAMを用いてインフラを再現可能な形で定義したい。デプロイの自動化と環境再現性のため。

#### 受入基準

1. THE Pipeline SHALL AWS SAM テンプレート（template.yaml）でInput_Bucket、Output_Bucket、EventBridgeルール、State_Machine、ConvertDocument_Lambdaを定義する
2. THE Pipeline SHALL Input_Bucket と Output_Bucket を SAMテンプレートで新規作成する
3. THE ConvertDocument_Lambda SHALL メモリ1024MB、タイムアウト5分、Reserved Concurrency 10で設定する
4. THE Pipeline SHALL SSE-S3（S3管理キー）によるデフォルト暗号化を両バケットに設定する
5. THE ConvertDocument_Lambda SHALL Input_Bucketに対して `s3:GetObject` のみ、Output_Bucketに対して `s3:PutObject` のみの最小権限IAMポリシーを持つ
6. THE Pipeline SHALL スタック名ベースでリソース名を自動生成し、タグ付け用パラメータ（Environment, Project）を`samconfig.toml`で設定可能にする
