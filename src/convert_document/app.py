"""ConvertDocument Lambda - ファイル分類と変換処理モジュール."""

import json
import logging
import os
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class FilePattern(Enum):
    """ファイル分類の結果を表す列挙型."""

    ANYDOC_CONVERT = "convert"  # パターン①: AnyDoc変換
    TEXT_COPY = "copy"          # パターン②: テキストコピー
    SKIP = "skip"              # パターン③: スキップ


ANYDOC_EXTENSIONS: set[str] = {
    ".doc", ".docx", ".docm",
    ".ppt", ".pps", ".pot", ".pptx", ".pptm", ".ppsx", ".ppsm",
    ".xls", ".xlsx", ".xlsm", ".xlsb",
    ".odt", ".ods", ".odp",
    ".rtf", ".epub", ".csv", ".pdf",
}

TEXT_EXTENSIONS: set[str] = {".txt", ".md"}


def classify_file(object_key: str) -> FilePattern:
    """
    オブジェクトキーの拡張子に基づきファイルを3パターンに分類する。

    拡張子の比較は大文字・小文字を区別しない（小文字に正規化して比較）。

    Args:
        object_key: S3オブジェクトキー（例: "documents/report.docx"）

    Returns:
        FilePattern: 分類結果
            - ANYDOC_CONVERT: AnyDoc対応拡張子の場合
            - TEXT_COPY: テキスト系拡張子（.txt, .md）の場合
            - SKIP: 上記以外の拡張子の場合
    """
    _, ext = os.path.splitext(object_key)
    ext_lower = ext.lower()

    if ext_lower in ANYDOC_EXTENSIONS:
        return FilePattern.ANYDOC_CONVERT
    elif ext_lower in TEXT_EXTENSIONS:
        return FilePattern.TEXT_COPY
    else:
        return FilePattern.SKIP


def get_output_key(source_key: str, pattern: FilePattern) -> Optional[str]:
    """
    入力キーから出力キーを生成する。

    パターン①（ANYDOC_CONVERT）: "{source_key}.md"
        例: "docs/report.docx" → "docs/report.docx.md"
    パターン②（TEXT_COPY）: "{source_key}" （キーそのまま）
        例: "docs/notes.txt" → "docs/notes.txt"
    パターン③（SKIP）: None（出力なし）

    Args:
        source_key: 入力S3オブジェクトキー
        pattern: ファイル分類結果

    Returns:
        出力キー文字列、またはスキップ時はNone
    """
    if pattern == FilePattern.ANYDOC_CONVERT:
        return f"{source_key}.md"
    elif pattern == FilePattern.TEXT_COPY:
        return source_key
    else:
        return None


def get_metadata_key(output_key: str) -> str:
    """
    出力キーからメタデータキーを生成する。

    規則: "{output_key}.metadata.json"
        例: "docs/report.docx.md" → "docs/report.docx.md.metadata.json"
        例: "docs/notes.txt" → "docs/notes.txt.metadata.json"

    Args:
        output_key: 出力S3オブジェクトキー

    Returns:
        メタデータJSONファイルのキー
    """
    return f"{output_key}.metadata.json"


def generate_metadata(
    source_bucket: str,
    source_key: str,
    file_size_bytes: int,
    conversion_duration_ms: int = 0,
) -> dict:
    """
    メタデータJSONの内容を生成する。

    Args:
        source_bucket: 入力S3バケット名
        source_key: 入力S3オブジェクトキー
        file_size_bytes: 元ファイルのサイズ（バイト）
        conversion_duration_ms: 変換所要時間（ミリ秒）。コピーの場合は0

    Returns:
        全必須フィールドを含むメタデータdict:
            - source_bucket: 入力バケット名
            - source_key: 入力オブジェクトキー
            - source_uri: "s3://{source_bucket}/{source_key}" 形式
            - converted_at: ISO 8601 UTC形式の日時文字列
            - anydoc_version: "0.1.9"
            - file_size_bytes: 元ファイルサイズ
            - conversion_duration_ms: 変換所要時間
    """
    return {
        "source_bucket": source_bucket,
        "source_key": source_key,
        "source_uri": f"s3://{source_bucket}/{source_key}",
        "converted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "anydoc_version": "0.1.9",
        "file_size_bytes": file_size_bytes,
        "conversion_duration_ms": conversion_duration_ms,
    }


def copy_text_file(bucket: str, key: str, output_bucket: str) -> dict:
    """
    テキストファイルをそのままOutput Bucketにコピーし、メタデータを生成する。

    S3からファイルを取得し、同一キーでOutput Bucketに格納後、
    メタデータJSONを生成して格納する。

    Args:
        bucket: 入力S3バケット名
        key: 入力S3オブジェクトキー
        output_bucket: 出力S3バケット名

    Returns:
        dict: {"status": "copied"}
    """
    import boto3

    s3_client = boto3.client("s3")

    # S3からファイルを取得
    response = s3_client.get_object(Bucket=bucket, Key=key)
    content = response["Body"].read()
    file_size_bytes = response["ContentLength"]

    # 同一キーでOutput Bucketにコピー
    output_key = get_output_key(key, FilePattern.TEXT_COPY)
    s3_client.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=content,
    )

    # メタデータを生成
    metadata = generate_metadata(
        source_bucket=bucket,
        source_key=key,
        file_size_bytes=file_size_bytes,
        conversion_duration_ms=0,
    )

    # メタデータJSONをOutput Bucketに格納
    metadata_key = get_metadata_key(output_key)
    try:
        s3_client.put_object(
            Bucket=output_bucket,
            Key=metadata_key,
            Body=json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
    except Exception:
        logger.warning(
            "Failed to store metadata JSON, but main file was stored successfully",
            extra={"bucket": output_bucket, "key": key, "metadata_key": metadata_key},
            exc_info=True,
        )

    return {"status": "copied"}


def skip_file(bucket: str, key: str) -> dict:
    """
    非対応ファイルをスキップし、構造化ログを記録する。

    Output Bucketへの書き込みは一切行わない。

    Args:
        bucket: 入力S3バケット名
        key: 入力S3オブジェクトキー

    Returns:
        dict: {"status": "skipped", "reason": "unsupported_extension"}
    """
    _, ext = os.path.splitext(key)

    logger.info(
        "Skipping unsupported file",
        extra={"bucket": bucket, "key": key, "extension": ext},
    )

    return {"status": "skipped", "reason": "unsupported_extension"}


def convert_document(bucket: str, key: str, output_bucket: str) -> dict:
    """
    AnyDocを使用してドキュメントをMarkdownに変換する。

    S3からファイルをダウンロードし、firecrawl-anydocで変換後、
    変換結果のMarkdownとメタデータJSONをOutput Bucketに格納する。

    Args:
        bucket: 入力S3バケット名
        key: 入力S3オブジェクトキー
        output_bucket: 出力S3バケット名

    Returns:
        dict: {"status": "converted"}

    Raises:
        Exception: 変換が失敗した場合（暗号化、破損等）。
            State MachineのCatch機構で捕捉される。
    """
    import boto3
    from anydoc import to_markdown

    s3_client = boto3.client("s3")
    filename = os.path.basename(key)
    local_path = f"/tmp/{filename}"

    try:
        # S3からファイルをダウンロード
        s3_client.download_file(bucket, key, local_path)

        # ファイルサイズを取得
        file_size_bytes = os.path.getsize(local_path)

        # firecrawl-anydoc による変換
        start_time = time.time()
        markdown_content = to_markdown(local_path)
        conversion_duration_ms = int((time.time() - start_time) * 1000)

        # 出力キーを生成
        output_key = get_output_key(key, FilePattern.ANYDOC_CONVERT)

        # MarkdownをOutput Bucketに格納
        s3_client.put_object(
            Bucket=output_bucket,
            Key=output_key,
            Body=markdown_content.encode("utf-8"),
            ContentType="text/markdown",
        )

        # メタデータを生成
        metadata = generate_metadata(
            source_bucket=bucket,
            source_key=key,
            file_size_bytes=file_size_bytes,
            conversion_duration_ms=conversion_duration_ms,
        )

        # メタデータJSONをOutput Bucketに格納
        metadata_key = get_metadata_key(output_key)
        try:
            s3_client.put_object(
                Bucket=output_bucket,
                Key=metadata_key,
                Body=json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
                ContentType="application/json",
            )
        except Exception:
            logger.warning(
                "Failed to store metadata JSON, but markdown was stored successfully",
                extra={"bucket": output_bucket, "key": key, "metadata_key": metadata_key},
                exc_info=True,
            )

        return {"status": "converted"}

    finally:
        # /tmp ファイルのクリーンアップ
        if os.path.exists(local_path):
            os.remove(local_path)


def lambda_handler(event: dict, context) -> dict:
    """
    ConvertDocument Lambda のエントリーポイント。

    Step Functions から渡されるイベントからバケット名・オブジェクトキーを取得し、
    ファイル分類に基づいて適切な処理を実行する。

    Args:
        event: Step Functions から渡されるイベント
            - detail.bucket.name: 入力バケット名
            - detail.object.key: オブジェクトキー
        context: Lambda実行コンテキスト

    Returns:
        dict: 処理結果
            - status: "converted" | "copied" | "skipped"
            - reason: (skipped時のみ) "unsupported_extension"
    """
    # イベントからバケット名・オブジェクトキーを取得
    bucket = event["detail"]["bucket"]["name"]
    key = event["detail"]["object"]["key"]
    output_bucket = os.environ["OUTPUT_BUCKET_NAME"]

    logger.info(
        "Processing file",
        extra={"bucket": bucket, "key": key, "output_bucket": output_bucket},
    )

    # ファイル分類
    pattern = classify_file(key)

    logger.info(
        "File classified",
        extra={"key": key, "pattern": pattern.value},
    )

    # パターンに応じた処理関数の呼び出し
    if pattern == FilePattern.ANYDOC_CONVERT:
        return convert_document(bucket, key, output_bucket)
    elif pattern == FilePattern.TEXT_COPY:
        return copy_text_file(bucket, key, output_bucket)
    else:
        return skip_file(bucket, key)
