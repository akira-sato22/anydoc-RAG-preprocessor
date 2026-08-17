# AnyDoc RAG前処理パイプライン 設計書

## 1. 目的・概要

RAG（Retrieval-Augmented Generation）のための文書前処理パイプラインを構築する。
S3に配置された各種オフィス文書・PDF等を [firecrawl/anydoc](https://github.com/firecrawl/anydoc)（Rust製、外部API/GPU不要のMarkdown変換ライブラリ）を用いてMarkdown化し、後続のRAGインデクシング処理が利用できる形でS3に格納する。

本設計書がカバーするのは「入力S3 → 変換 → 出力S3」までであり、Markdown化後のチャンク分割・Embedding化・ベクトルDB登録等は本パイプラインのスコープ外とする。

## 2. 全体アーキテクチャ

```
                 ObjectCreated
[Input S3 Bucket] ---------------> [EventBridge Rule] ---------------> [Step Functions State Machine]
                                                                                 |
                                                                                 v
                                                                    [Lambda: ConvertDocument]
                                                                    (拡張子で分類→処理分岐)
                                                                                 |
                                                        +------------+-----------+------------+
                                                        |            |                        |
                                                  パターン①     パターン②               パターン③
                                                  AnyDoc変換    テキストコピー             スキップ
                                                        |            |                        |
                                                   成功 / 失敗   Output Bucketへ        ログ記録のみ
                                                    |       |    コピー+メタデータ       (何もしない)
                                                    v       v         |
                                              [Output S3] [HandleUnsupported]
                                              MD+メタデータ (ログ記録)
```

### コンポーネント構成

| コンポーネント | 役割 |
|---|---|
| Input S3 Bucket | 変換対象の原本ファイルを格納 |
| EventBridge Rule | Input BucketへのPUT（`Object Created`）イベントを検知し、Step Functionsを起動 |
| Step Functions State Machine | 変換Lambdaの実行、成功/失敗の分岐、リトライ制御を行うオーケストレーション |
| Lambda: ConvertDocument | S3から原本を取得し、AnyDocで変換を試行。成功時はOutput Bucketへ結果をPUT |
| Output S3 Bucket | 変換済みMarkdownファイルを格納 |
| CloudWatch Logs / (任意)SNS | 失敗・非対応ファイルの記録、および必要に応じた通知 |

## 3. 確定した設計方針（ユーザー確認済み）

| 項目 | 決定事項 |
|---|---|
| IaCツール | AWS SAM |
| Lambda実装言語 | Python（`pip install firecrawl-anydoc`） |
| S3バケット構成 | 入力用・出力用の2バケット構成 |
| ファイル分類と処理方針 | 3パターン分岐（後述3.2参照）: ①AnyDoc対応拡張子→変換、②テキスト系(.txt/.md)→そのままコピー＋メタデータ生成、③それ以外→スキップ（何もしない） |
| AnyDocバージョン | `firecrawl-anydoc==0.1.9`（PyPI最新安定版をピン留め） |
| 冪等性 | 同一キーのファイルが再PUTされた場合、出力Markdownおよびメタデータを上書きする。S3バージョニングは使用しない |
| 出力ファイル名規則 | 元の拡張子を残した上で `.md` を付与する（例: `report.docx.md`）。同一プレフィックスに異なる拡張子の同名ファイルが存在しても衝突しない |
| メタデータ付与方式 | 変換済みMarkdownと同一プレフィックスに `.metadata.json` ファイルを配置する |

### 3.1 ファイル分類と処理パターン

入力ファイルを拡張子に基づき以下の3パターンに分類し、それぞれ異なる処理を行う。

| パターン | 対象拡張子 | 処理内容 |
|---|---|---|
| ① AnyDoc変換 | `.doc`, `.docx`, `.docm`, `.ppt`, `.pps`, `.pot`, `.pptx`, `.pptm`, `.ppsx`, `.ppsm`, `.xls`, `.xlsx`, `.xlsm`, `.xlsb`, `.odt`, `.ods`, `.odp`, `.rtf`, `.epub`, `.csv`, `.pdf` | AnyDocで変換し、Markdown + `.metadata.json` をOutput Bucketに格納 |
| ② テキストコピー | `.txt`, `.md` | 変換不要のため**そのままOutput Bucketにコピー** + `.metadata.json` を生成 |
| ③ スキップ | 上記以外（`.png`, `.jpg`, `.zip` 等） | 何もしない。CloudWatch Logsにスキップした旨を記録するのみ |

この分類はLambda内で拡張子を判定して分岐する。AnyDoc変換対象の場合は実際に変換を試行し、変換時エラー（暗号化ファイル等）が発生した場合は失敗として扱う。

### 3.2 判定ロジックに関する設計上の帰結

AnyDoc変換対象（パターン①）の場合、**「判定」と「変換」は同一のLambda呼び出し内で行う**（判定用Lambdaと変換用Lambdaを分離しない）。
これにより、同じファイルに対してAnyDocの変換処理を二重に実行するコストを避ける。Step Functions上は以下の構造で表現する。

1. `ClassifyFile`（Lambda内で拡張子による分類）
2. `Choice`（パターン①/②/③で分岐）
   - パターン① → `ConvertDocument`（AnyDoc変換 + 出力格納）
     - 成功 → `Succeed`
     - 失敗 → `HandleUnsupported`
   - パターン② → `CopyTextFile`（そのままコピー + メタデータ生成）→ `Succeed`
   - パターン③ → `SkipFile`（ログ出力のみ）→ `Succeed`

## 4. 処理フロー詳細

### 4.1 トリガー

- Input BucketのS3 Event NotificationsをEventBridge連携で有効化する（バケットのプロパティで `EventBridge通知` をOnにする）。
- EventBridgeルールで `Object Created`（`PutObject`, `CompleteMultipartUpload`等）をフィルタし、Step Functionsステートマシンを直接ターゲットとして起動する（Lambdaを起動用に挟まない、EventBridge→SFN直接連携）。
- 実行ロールはEventBridgeからStep Functionsへの`StartExecution`権限のみを付与する。

### 4.2 Step Functions ステートマシン

- タイプ: Standard（実行履歴の追跡・再実行のしやすさを優先）
- 入力: EventBridgeイベント（バケット名・オブジェクトキーを含む）
- 処理フロー:
  1. `ConvertDocument` Lambda を呼び出す（分類・処理を一括で実行）
  2. Lambda戻り値の `status` フィールドで分岐:
     - `"converted"` or `"copied"` → `Succeed`
     - `"skipped"` → `Succeed`（正常終了扱い）
  3. Lambda実行時例外（変換失敗）は `Catch` で捕捉し `HandleUnsupported` → `Succeed`
- `ConvertDocument` Lambda呼び出しに対して `Retry`（一時的なエラー、例: S3スロットリング等を想定し2〜3回・指数バックオフ）を設定
- `HandleUnsupported` はPass状態とし、ステートマシン自体は「異常終了」ではなく正常に完了させる（非対応ファイルや変換エラーはビジネス上想定内の分岐であり、SFNレベルのアラームを発報させないため）

### 4.3 Lambda: ConvertDocument

処理内容:
1. イベントから対象バケット名・オブジェクトキーを取得
2. 拡張子に基づきファイルを分類（パターン①/②/③）
3. **パターン③（スキップ対象）** の場合:
   - CloudWatch Logsにスキップした旨を記録
   - `{"status": "skipped", "reason": "unsupported_extension"}` を返却
4. **パターン②（テキストコピー）** の場合:
   - S3から原本を取得し、そのままOutput Bucketにコピー（キーは変えない）
   - `.metadata.json` を生成して格納
   - `{"status": "copied"}` を返却
5. **パターン①（AnyDoc変換）** の場合:
   - S3から `/tmp` に原本ファイルをダウンロード
   - `firecrawl-anydoc` の変換関数を呼び出しMarkdown化を試行
   - 変換成功時、Markdown（`.{元拡張子}.md`）と `.metadata.json` をOutput Bucketに格納
   - `{"status": "converted"}` を返却
   - 変換失敗時（暗号化、破損等）は例外をraiseし、Step FunctionsのCatchで捕捉

技術的な考慮事項:
- **パッケージング**: `firecrawl-anydoc` はRustのネイティブバインディング（PyO3等）を含むため、Lambda実行環境（Amazon Linux）とホスト側のビルド環境のOS/CPUアーキテクチャ齟齬による実行時エラーのリスクがある。`sam build --use-container` でLambda互換環境を使ってビルドするか、Lambdaコンテナイメージ（`public.ecr.aws/lambda/python` ベース）を用いる方式を推奨する。
- **メモリ／タイムアウト**: 大きめのOfficeファイルやPDFの変換を想定し、メモリ1024MB・タイムアウト5分を初期値とし、実測に応じて調整する。
- **一時ストレージ**: Lambdaの Ephemeral Storage（`/tmp`）を利用。数十MB程度のファイルを想定し、デフォルト512MBで運用する。
- **IAM**: Input Bucketに対して `s3:GetObject` のみ、Output Bucketに対して `s3:PutObject` のみを許可する最小権限とする。

### 4.4 Output Bucketのキー設計

入力オブジェクトキーとの対応が追跡できるよう、原則として入力キーを踏襲する。

**パターン①（AnyDoc変換）:**
元の拡張子を残した上で `.md` を付与する。同一プレフィックスに `report.docx` と `report.pdf` が存在する場合でもキーが衝突しない。

```
Input:  s3://<input-bucket>/documents/2026/report.docx
Output: s3://<output-bucket>/documents/2026/report.docx.md
         s3://<output-bucket>/documents/2026/report.docx.metadata.json
```

**パターン②（テキストコピー）:**
キーをそのまま維持してコピーし、メタデータのみ追加生成する。

```
Input:  s3://<input-bucket>/documents/2026/notes.txt
Output: s3://<output-bucket>/documents/2026/notes.txt
         s3://<output-bucket>/documents/2026/notes.txt.metadata.json
```

同一ファイルが再PUTされた場合は出力を上書きする（冪等性はラストライター勝ちで担保。バージョニングは使用しない）。

### 4.5 メタデータファイル（`.metadata.json`）

変換済みMarkdownと同一プレフィックスに `.metadata.json` を配置し、RAG側でのトレーサビリティを確保する。

```json
{
  "source_bucket": "<input-bucket>",
  "source_key": "documents/2026/report.docx",
  "source_uri": "s3://<input-bucket>/documents/2026/report.docx",
  "converted_at": "2026-08-14T12:34:56Z",
  "anydoc_version": "0.1.9",
  "file_size_bytes": 1048576,
  "conversion_duration_ms": 42
}
```

- Lambda内で変換成功後、Markdownの `PutObject` とメタデータの `PutObject` を同一Lambda実行内で行う。
- メタデータファイルの格納に失敗した場合もMarkdown自体は格納済みのため、Lambda全体を失敗扱いにはしない（ログ出力のみ）。

## 5. エラー・非対応ファイルの扱い

- **パターン③（スキップ）**: AnyDoc非対応かつテキスト系でもないファイルは、何もせずスキップする。CloudWatch Logsにスキップした旨（バケット名・キー・拡張子）を構造化ログで出力する。
- **パターン①の変換失敗**: AnyDoc変換時に例外が発生したファイル（暗号化、破損等）は、CloudWatch Logsにエラー内容を記録し、Step Functionsの `HandleUnsupported` 状態で処理する。
- Step Functionsの実行自体は全パターンで正常終了として扱う（=CloudWatchアラームの誤発報を避ける）。
- 初期リリースではSNS通知は設けない（ログのみ）。将来的にCloudWatch Logs Insights / Metric Filterでの集計を追加可能。

## 6. IaC構成（AWS SAM）

```
anydoc-RAG-preprocessor/
├── template.yaml                 # SAMテンプレート（S3, EventBridge Rule, StateMachine, Lambda, IAM）
├── statemachine/
│   └── convert.asl.json          # Step Functions定義（ASL）
├── src/
│   └── convert_document/
│       ├── app.py                # Lambdaハンドラ
│       ├── requirements.txt      # firecrawl-anydoc, boto3等
│       └── Dockerfile            # コンテナイメージ方式を採る場合
├── tests/
│   └── unit/
│       └── test_convert_document.py
├── samconfig.toml
└── DESIGN.md
```

- パラメータ化: スタック名ベースでリソース名を自動生成する。タグ付け用の `Parameters`（`Environment`, `Project` 等）を用意し、`samconfig.toml` で値を設定できるようにする。
- バケットはSAMで新規作成する（既存バケットの参照は不要）。

## 7. 監視・運用

- テスト用途のため、初期リリースではSNS通知・CloudWatch Alarmは設けない。
- Lambda実行ログはCloudWatch Logsに出力される（構造化ログ形式）。
- Step Functionsの実行履歴はコンソールから確認可能（Standard タイプのため全実行が記録される）。
- 将来的に本番化する際は、X-Rayトレーシングの有効化、CloudWatch Alarm（Lambda エラー率・SFN 実行失敗）の追加を検討する。

## 8. 確定済み運用方針

以下は全てヒアリングにより確定済み。

| 項目 | 決定事項 |
|---|---|
| バケット | Input/Output共にSAMで新規作成 |
| デプロイ先 | シングルアカウント・シングル環境（テスト用） |
| 暗号化 | SSE-S3（S3管理キーによるデフォルト暗号化） |
| 対象フィルタ | EventBridgeでのプレフィックス/サフィックス絞り込みは行わない。Lambda内で拡張子により3パターン分岐 |
| 同時実行 | 一度に最大100件程度のPUTを想定。Lambda Reserved Concurrency = 10 で並列処理を制御 |
| ファイルサイズ | 数十MB以下を想定。Lambdaデフォルト `/tmp` 512MB・タイムアウト5分で対応可能 |
| 命名規則 | スタック名ベースで自動生成。タグ付け用パラメータ（`Environment`, `Project`）を `samconfig.toml` で設定可能にする |
| 通知 | 初期リリースではSNS通知なし（CloudWatch Logsのみ） |
| 非対応ファイル | 何もしない（スキップ）。ログ記録のみ |

---

上記方針に基づき `template.yaml` 等の実装に着手可能な状態。
