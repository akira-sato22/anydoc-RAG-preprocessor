"""ConvertDocument Lambda handler のユニットテスト.

Requirements:
    - 3.4: 変換成功時 {"status": "converted"} を返却
    - 3.5: 変換失敗時 例外をraise
    - 4.3: コピー完了時 {"status": "copied"} を返却
    - 5.2: パターン③ {"status": "skipped", "reason": "unsupported_extension"} を返却
    - 6.5: メタデータ格納失敗時、全体を失敗扱いにせずログ出力のみ
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    """OUTPUT_BUCKET_NAME 環境変数を設定."""
    monkeypatch.setenv("OUTPUT_BUCKET_NAME", "test-output-bucket")


@pytest.fixture
def mock_boto3():
    """boto3 モジュールのモック."""
    mock_module = MagicMock()
    mock_s3 = MagicMock()
    mock_module.client.return_value = mock_s3
    return mock_module, mock_s3


@pytest.fixture
def mock_anydoc_module():
    """anydoc モジュールのモック."""
    mock_module = MagicMock()
    return mock_module, mock_module.to_markdown


@pytest.fixture
def docx_event():
    """パターン①: AnyDoc変換対象の .docx イベント."""
    return {
        "detail": {
            "bucket": {"name": "test-input-bucket"},
            "object": {"key": "path/to/file.docx"},
        }
    }


@pytest.fixture
def txt_event():
    """パターン②: テキストコピー対象の .txt イベント."""
    return {
        "detail": {
            "bucket": {"name": "test-input-bucket"},
            "object": {"key": "path/to/file.txt"},
        }
    }


@pytest.fixture
def exe_event():
    """パターン③: スキップ対象の .exe イベント."""
    return {
        "detail": {
            "bucket": {"name": "test-input-bucket"},
            "object": {"key": "path/to/file.exe"},
        }
    }


class TestLambdaHandlerConvert:
    """パターン①: AnyDoc変換のハンドラ動作テスト (Req 3.4)."""

    def test_docx_returns_converted(self, docx_event, mock_boto3, mock_anydoc_module):
        """lambda_handler に .docx ファイルを渡すと convert_document が呼ばれ {"status": "converted"} を返す."""
        mock_boto3_mod, mock_s3 = mock_boto3
        mock_anydoc_mod, mock_to_markdown = mock_anydoc_module

        # anydoc 変換結果のモック
        mock_to_markdown.return_value = "# Converted Content"

        with patch.dict(sys.modules, {"boto3": mock_boto3_mod, "anydoc": mock_anydoc_mod}):
            with patch("os.path.getsize", return_value=1024):
                with patch("os.path.exists", return_value=True):
                    with patch("os.remove"):
                        from src.convert_document.app import lambda_handler
                        result = lambda_handler(docx_event, None)

        assert result == {"status": "converted"}

    def test_docx_puts_markdown_and_metadata(self, docx_event, mock_boto3, mock_anydoc_module):
        """変換成功時、MarkdownとメタデータJSONが Output Bucket に格納される."""
        mock_boto3_mod, mock_s3 = mock_boto3
        mock_anydoc_mod, mock_to_markdown = mock_anydoc_module

        mock_to_markdown.return_value = "# Converted Content"

        with patch.dict(sys.modules, {"boto3": mock_boto3_mod, "anydoc": mock_anydoc_mod}):
            with patch("os.path.getsize", return_value=2048):
                with patch("os.path.exists", return_value=True):
                    with patch("os.remove"):
                        from src.convert_document.app import lambda_handler
                        lambda_handler(docx_event, None)

        # put_object が少なくとも2回呼ばれる（Markdown + メタデータ）
        put_calls = mock_s3.put_object.call_args_list
        assert len(put_calls) >= 2

        # Markdown の格納確認
        md_call = put_calls[0]
        assert md_call.kwargs["Bucket"] == "test-output-bucket"
        assert md_call.kwargs["Key"] == "path/to/file.docx.md"

        # メタデータの格納確認
        meta_call = put_calls[1]
        assert meta_call.kwargs["Bucket"] == "test-output-bucket"
        assert meta_call.kwargs["Key"] == "path/to/file.docx.md.metadata.json"


class TestLambdaHandlerCopy:
    """パターン②: テキストコピーのハンドラ動作テスト (Req 4.3)."""

    def test_txt_returns_copied(self, txt_event, mock_boto3):
        """lambda_handler に .txt ファイルを渡すと copy_text_file が呼ばれ {"status": "copied"} を返す."""
        mock_boto3_mod, mock_s3 = mock_boto3

        # get_object のモック
        mock_body = MagicMock()
        mock_body.read.return_value = b"Hello, world!"
        mock_s3.get_object.return_value = {
            "Body": mock_body,
            "ContentLength": 13,
        }

        with patch.dict(sys.modules, {"boto3": mock_boto3_mod}):
            from src.convert_document.app import lambda_handler
            result = lambda_handler(txt_event, None)

        assert result == {"status": "copied"}

    def test_txt_copies_content_to_output_bucket(self, txt_event, mock_boto3):
        """テキストファイルが同一キーで Output Bucket にコピーされる."""
        mock_boto3_mod, mock_s3 = mock_boto3

        mock_body = MagicMock()
        mock_body.read.return_value = b"Hello, world!"
        mock_s3.get_object.return_value = {
            "Body": mock_body,
            "ContentLength": 13,
        }

        with patch.dict(sys.modules, {"boto3": mock_boto3_mod}):
            from src.convert_document.app import lambda_handler
            lambda_handler(txt_event, None)

        # put_object が呼ばれていることを確認
        put_calls = mock_s3.put_object.call_args_list
        assert len(put_calls) >= 1

        # ファイルコピーの確認（同一キー）
        copy_call = put_calls[0]
        assert copy_call.kwargs["Bucket"] == "test-output-bucket"
        assert copy_call.kwargs["Key"] == "path/to/file.txt"
        assert copy_call.kwargs["Body"] == b"Hello, world!"


class TestLambdaHandlerSkip:
    """パターン③: スキップのハンドラ動作テスト (Req 5.2)."""

    def test_exe_returns_skipped(self, exe_event):
        """lambda_handler に .exe ファイルを渡すと {"status": "skipped", "reason": "unsupported_extension"} を返す."""
        from src.convert_document.app import lambda_handler

        result = lambda_handler(exe_event, None)

        assert result == {"status": "skipped", "reason": "unsupported_extension"}


class TestConvertDocumentError:
    """エラーケースのテスト (Req 3.5)."""

    def test_anydoc_exception_propagates(self, docx_event, mock_boto3, mock_anydoc_module):
        """AnyDoc変換が例外をraiseした場合、lambda_handler も例外をraiseする."""
        mock_boto3_mod, mock_s3 = mock_boto3
        mock_anydoc_mod, mock_to_markdown = mock_anydoc_module

        # anydoc が例外を発生させる
        mock_to_markdown.side_effect = RuntimeError(
            "Encrypted file cannot be converted"
        )

        with patch.dict(sys.modules, {"boto3": mock_boto3_mod, "anydoc": mock_anydoc_mod}):
            with patch("os.path.getsize", return_value=1024):
                with patch("os.path.exists", return_value=True):
                    with patch("os.remove"):
                        from src.convert_document.app import lambda_handler
                        with pytest.raises(
                            RuntimeError, match="Encrypted file cannot be converted"
                        ):
                            lambda_handler(docx_event, None)


class TestMetadataStorageFailure:
    """メタデータ格納失敗時の非エラー動作テスト (Req 6.5)."""

    def test_convert_metadata_failure_still_returns_converted(
        self, docx_event, mock_boto3, mock_anydoc_module
    ):
        """convert_document でメタデータ put_object が失敗しても {"status": "converted"} を返す."""
        mock_boto3_mod, mock_s3 = mock_boto3
        mock_anydoc_mod, mock_to_markdown = mock_anydoc_module

        mock_to_markdown.return_value = "# Converted Content"

        # put_object: Markdown格納は成功、メタデータ格納は失敗
        call_count = {"n": 0}

        def put_object_side_effect(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:  # 2回目（メタデータ）で失敗
                raise Exception("S3 PutObject failed for metadata")

        mock_s3.put_object.side_effect = put_object_side_effect

        with patch.dict(sys.modules, {"boto3": mock_boto3_mod, "anydoc": mock_anydoc_mod}):
            with patch("os.path.getsize", return_value=1024):
                with patch("os.path.exists", return_value=True):
                    with patch("os.remove"):
                        from src.convert_document.app import lambda_handler
                        result = lambda_handler(docx_event, None)

        # メタデータ格納失敗でも全体は成功
        assert result == {"status": "converted"}

    def test_copy_metadata_failure_still_returns_copied(self, txt_event, mock_boto3):
        """copy_text_file でメタデータ put_object が失敗しても {"status": "copied"} を返す."""
        mock_boto3_mod, mock_s3 = mock_boto3

        mock_body = MagicMock()
        mock_body.read.return_value = b"Hello, world!"
        mock_s3.get_object.return_value = {
            "Body": mock_body,
            "ContentLength": 13,
        }

        # put_object: ファイルコピーは成功、メタデータ格納は失敗
        call_count = {"n": 0}

        def put_object_side_effect(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:  # 2回目（メタデータ）で失敗
                raise Exception("S3 PutObject failed for metadata")

        mock_s3.put_object.side_effect = put_object_side_effect

        with patch.dict(sys.modules, {"boto3": mock_boto3_mod}):
            from src.convert_document.app import lambda_handler
            result = lambda_handler(txt_event, None)

        # メタデータ格納失敗でも全体は成功
        assert result == {"status": "copied"}
