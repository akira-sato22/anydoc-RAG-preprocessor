"""ファイル分類のプロパティテスト.

Property 1: ファイル分類の完全性と正確性
Property 2: ファイル分類の決定性

Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5
"""

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from src.convert_document.app import (
    ANYDOC_EXTENSIONS,
    TEXT_EXTENSIONS,
    FilePattern,
    classify_file,
)

# --- Strategies ---

# S3オブジェクトキーに使用可能な文字（ASCII + 一般的なパス文字）
_s3_key_chars = string.ascii_letters + string.digits + "-_./!@#$%^&()+={}"

# ディレクトリプレフィックスの生成
_prefix_strategy = st.one_of(
    st.just(""),
    st.text(alphabet=string.ascii_letters + string.digits + "-_/", min_size=1, max_size=50).map(
        lambda s: s.rstrip("/") + "/"
    ),
)

# ファイル名（拡張子なし）の生成
_filename_strategy = st.text(
    alphabet=string.ascii_letters + string.digits + "-_ ",
    min_size=1,
    max_size=30,
)


def _make_object_key(prefix: str, filename: str, ext: str) -> str:
    """プレフィックス + ファイル名 + 拡張子からオブジェクトキーを組み立てる."""
    return f"{prefix}{filename}{ext}"


# ANYDOC拡張子を持つオブジェクトキー（大文字/小文字/混在ケース含む）
def _case_variant(ext: str) -> st.SearchStrategy[str]:
    """拡張子の大文字・小文字バリエーションを生成."""
    return st.sampled_from([
        ext.lower(),
        ext.upper(),
        ext.lower()[0] + ext.upper()[1:],  # 混在: .Docx
    ])


_anydoc_ext_strategy = st.sampled_from(sorted(ANYDOC_EXTENSIONS)).flatmap(_case_variant)
_text_ext_strategy = st.sampled_from(sorted(TEXT_EXTENSIONS)).flatmap(_case_variant)

# ANYDOC_EXTENSIONSにもTEXT_EXTENSIONSにも含まれない拡張子
_all_known_extensions = ANYDOC_EXTENSIONS | TEXT_EXTENSIONS
_unknown_ext_strategy = st.one_of(
    st.just(""),  # 拡張子なし
    st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=6).map(
        lambda s: f".{s}"
    ).filter(lambda e: e.lower() not in _all_known_extensions),
)

# ANYDOC対応のオブジェクトキー
anydoc_key_strategy = st.builds(_make_object_key, _prefix_strategy, _filename_strategy, _anydoc_ext_strategy)

# TEXT対応のオブジェクトキー
text_key_strategy = st.builds(_make_object_key, _prefix_strategy, _filename_strategy, _text_ext_strategy)

# 非対応拡張子のオブジェクトキー
skip_key_strategy = st.builds(_make_object_key, _prefix_strategy, _filename_strategy, _unknown_ext_strategy)

# 任意のオブジェクトキー（全パターン混合）
any_key_strategy = st.one_of(anydoc_key_strategy, text_key_strategy, skip_key_strategy)


# --- Property 1: ファイル分類の完全性と正確性 ---


class TestClassifyFileCompletenessAndCorrectness:
    """Property 1: ファイル分類の完全性と正確性.

    任意のS3オブジェクトキーに対して、classify_file()は必ずFilePatternのいずれかの値
    (ANYDOC_CONVERT, TEXT_COPY, SKIP)を返し、未分類の状態にはならない。
    かつ、ANYDOC_EXTENSIONSに含まれる拡張子はパターン①に、
    TEXT_EXTENSIONSに含まれる拡張子はパターン②に、それ以外はパターン③に分類される。

    **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
    """

    @given(object_key=any_key_strategy)
    @settings(max_examples=500)
    def test_always_returns_valid_file_pattern(self, object_key: str) -> None:
        """任意のオブジェクトキーに対して、結果は必ずFilePatternのいずれかである."""
        result = classify_file(object_key)
        assert isinstance(result, FilePattern), (
            f"classify_file('{object_key}') returned {result}, which is not a FilePattern"
        )
        assert result in (FilePattern.ANYDOC_CONVERT, FilePattern.TEXT_COPY, FilePattern.SKIP)

    @given(object_key=anydoc_key_strategy)
    @settings(max_examples=300)
    def test_anydoc_extensions_classified_as_convert(self, object_key: str) -> None:
        """ANYDOC_EXTENSIONSに含まれる拡張子のファイルはANYDOC_CONVERTに分類される."""
        result = classify_file(object_key)
        assert result == FilePattern.ANYDOC_CONVERT, (
            f"classify_file('{object_key}') returned {result.name}, expected ANYDOC_CONVERT"
        )

    @given(object_key=text_key_strategy)
    @settings(max_examples=300)
    def test_text_extensions_classified_as_copy(self, object_key: str) -> None:
        """TEXT_EXTENSIONSに含まれる拡張子のファイルはTEXT_COPYに分類される."""
        result = classify_file(object_key)
        assert result == FilePattern.TEXT_COPY, (
            f"classify_file('{object_key}') returned {result.name}, expected TEXT_COPY"
        )

    @given(object_key=skip_key_strategy)
    @settings(max_examples=300)
    def test_unknown_extensions_classified_as_skip(self, object_key: str) -> None:
        """既知拡張子以外のファイルはSKIPに分類される."""
        result = classify_file(object_key)
        assert result == FilePattern.SKIP, (
            f"classify_file('{object_key}') returned {result.name}, expected SKIP"
        )


# --- Property 2: ファイル分類の決定性 ---


class TestClassifyFileDeterminism:
    """Property 2: ファイル分類の決定性.

    任意のオブジェクトキーに対して、classify_file()を複数回呼び出しても
    常に同一のFilePatternを返す（決定的な動作）。

    **Validates: Requirements 2.5**
    """

    @given(object_key=any_key_strategy)
    @settings(max_examples=500)
    def test_classify_file_is_deterministic(self, object_key: str) -> None:
        """同一キーに対する複数回の呼び出しで常に同一結果を返す."""
        result1 = classify_file(object_key)
        result2 = classify_file(object_key)
        result3 = classify_file(object_key)
        assert result1 == result2 == result3, (
            f"classify_file('{object_key}') returned different results: "
            f"{result1.name}, {result2.name}, {result3.name}"
        )
