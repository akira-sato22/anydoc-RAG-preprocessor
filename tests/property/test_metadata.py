"""メタデータ生成のプロパティテスト.

Property 4: メタデータ構造の完全性
Property 5: メタデータのsource_uriフォーマット整合性
Property 6: メタデータのconverted_at形式

Validates: Requirements 6.1, 6.2, 6.3
"""

import string
from datetime import datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from src.convert_document.app import generate_metadata

# --- Strategies ---

# S3バケット名: 3-63文字、小文字英数字+ハイフン、先頭末尾は英数字
_bucket_name_char = string.ascii_lowercase + string.digits + "-"
_bucket_name_start_end_char = string.ascii_lowercase + string.digits

_bucket_name_strategy = st.builds(
    lambda start, middle, end: start + middle + end,
    st.text(alphabet=_bucket_name_start_end_char, min_size=1, max_size=1),
    st.text(alphabet=_bucket_name_char, min_size=1, max_size=61),
    st.text(alphabet=_bucket_name_start_end_char, min_size=1, max_size=1),
).filter(lambda s: 3 <= len(s) <= 63 and "--" not in s)

# S3オブジェクトキー: 1-1024文字
_s3_key_chars = string.ascii_letters + string.digits + "-_./!@#$%^&()+={}[]"
_source_key_strategy = st.text(
    alphabet=_s3_key_chars,
    min_size=1,
    max_size=100,
)

# file_size_bytes: 非負整数
_file_size_strategy = st.integers(min_value=0, max_value=10**12)

# conversion_duration_ms: 非負整数
_duration_strategy = st.integers(min_value=0, max_value=600_000)


# --- Property 4: メタデータ構造の完全性 ---


class TestMetadataStructureCompleteness:
    """Property 4: メタデータ構造の完全性.

    任意の有効な入力パラメータ（source_bucket, source_key, file_size_bytes,
    conversion_duration_ms）に対して、generate_metadata()は必ず全ての必須フィールド
    （source_bucket, source_key, source_uri, converted_at, anydoc_version,
    file_size_bytes, conversion_duration_ms）を含むdictを返す。

    **Validates: Requirements 6.1**
    """

    REQUIRED_FIELDS = {
        "source_bucket",
        "source_key",
        "source_uri",
        "converted_at",
        "anydoc_version",
        "file_size_bytes",
        "conversion_duration_ms",
    }

    @given(
        source_bucket=_bucket_name_strategy,
        source_key=_source_key_strategy,
        file_size_bytes=_file_size_strategy,
        conversion_duration_ms=_duration_strategy,
    )
    @settings(max_examples=500)
    def test_metadata_contains_all_required_fields(
        self,
        source_bucket: str,
        source_key: str,
        file_size_bytes: int,
        conversion_duration_ms: int,
    ) -> None:
        """生成されたメタデータは全ての必須フィールドを含む."""
        result = generate_metadata(
            source_bucket=source_bucket,
            source_key=source_key,
            file_size_bytes=file_size_bytes,
            conversion_duration_ms=conversion_duration_ms,
        )

        assert isinstance(result, dict), (
            f"generate_metadata() returned {type(result).__name__}, expected dict"
        )

        missing_fields = self.REQUIRED_FIELDS - set(result.keys())
        assert not missing_fields, (
            f"Metadata is missing required fields: {missing_fields}"
        )

    @given(
        source_bucket=_bucket_name_strategy,
        source_key=_source_key_strategy,
        file_size_bytes=_file_size_strategy,
        conversion_duration_ms=_duration_strategy,
    )
    @settings(max_examples=300)
    def test_metadata_preserves_input_values(
        self,
        source_bucket: str,
        source_key: str,
        file_size_bytes: int,
        conversion_duration_ms: int,
    ) -> None:
        """生成されたメタデータの入力由来フィールドは入力値と一致する."""
        result = generate_metadata(
            source_bucket=source_bucket,
            source_key=source_key,
            file_size_bytes=file_size_bytes,
            conversion_duration_ms=conversion_duration_ms,
        )

        assert result["source_bucket"] == source_bucket
        assert result["source_key"] == source_key
        assert result["file_size_bytes"] == file_size_bytes
        assert result["conversion_duration_ms"] == conversion_duration_ms


# --- Property 5: メタデータのsource_uriフォーマット整合性 ---


class TestMetadataSourceUriFormat:
    """Property 5: メタデータのsource_uriフォーマット整合性.

    任意のsource_bucketとsource_keyの組み合わせに対して、generate_metadata()が返す
    source_uriは "s3://{source_bucket}/{source_key}" の形式と一致する。

    **Validates: Requirements 6.2**
    """

    @given(
        source_bucket=_bucket_name_strategy,
        source_key=_source_key_strategy,
        file_size_bytes=_file_size_strategy,
        conversion_duration_ms=_duration_strategy,
    )
    @settings(max_examples=500)
    def test_source_uri_matches_expected_format(
        self,
        source_bucket: str,
        source_key: str,
        file_size_bytes: int,
        conversion_duration_ms: int,
    ) -> None:
        """source_uriは "s3://{bucket}/{key}" 形式と一致する."""
        result = generate_metadata(
            source_bucket=source_bucket,
            source_key=source_key,
            file_size_bytes=file_size_bytes,
            conversion_duration_ms=conversion_duration_ms,
        )

        expected_uri = f"s3://{source_bucket}/{source_key}"
        assert result["source_uri"] == expected_uri, (
            f"source_uri mismatch: got '{result['source_uri']}', "
            f"expected '{expected_uri}'"
        )


# --- Property 6: メタデータのconverted_at形式 ---


class TestMetadataConvertedAtFormat:
    """Property 6: メタデータのconverted_at形式.

    任意の有効な入力パラメータに対して、generate_metadata()が返すconverted_atは
    ISO 8601 UTC形式の文字列である。

    **Validates: Requirements 6.3**
    """

    @given(
        source_bucket=_bucket_name_strategy,
        source_key=_source_key_strategy,
        file_size_bytes=_file_size_strategy,
        conversion_duration_ms=_duration_strategy,
    )
    @settings(max_examples=500)
    def test_converted_at_is_valid_iso8601_utc(
        self,
        source_bucket: str,
        source_key: str,
        file_size_bytes: int,
        conversion_duration_ms: int,
    ) -> None:
        """converted_atはISO 8601 UTC形式（%Y-%m-%dT%H:%M:%SZ）でパース可能."""
        result = generate_metadata(
            source_bucket=source_bucket,
            source_key=source_key,
            file_size_bytes=file_size_bytes,
            conversion_duration_ms=conversion_duration_ms,
        )

        converted_at = result["converted_at"]

        # ISO 8601 UTC形式でパース可能であることを検証
        parsed = datetime.strptime(converted_at, "%Y-%m-%dT%H:%M:%SZ")
        assert parsed is not None, (
            f"converted_at '{converted_at}' is not valid ISO 8601 UTC format"
        )

    @given(
        source_bucket=_bucket_name_strategy,
        source_key=_source_key_strategy,
        file_size_bytes=_file_size_strategy,
        conversion_duration_ms=_duration_strategy,
    )
    @settings(max_examples=300)
    def test_converted_at_ends_with_z_suffix(
        self,
        source_bucket: str,
        source_key: str,
        file_size_bytes: int,
        conversion_duration_ms: int,
    ) -> None:
        """converted_atはUTCを示す'Z'サフィックスで終わる."""
        result = generate_metadata(
            source_bucket=source_bucket,
            source_key=source_key,
            file_size_bytes=file_size_bytes,
            conversion_duration_ms=conversion_duration_ms,
        )

        assert result["converted_at"].endswith("Z"), (
            f"converted_at '{result['converted_at']}' does not end with 'Z'"
        )
