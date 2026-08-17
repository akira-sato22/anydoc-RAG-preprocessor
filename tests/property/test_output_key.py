"""出力キー生成のプロパティテスト.

Property 3: 出力キー命名の非衝突性

Validates: Requirements 7.1, 7.2, 7.3
"""

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from src.convert_document.app import (
    ANYDOC_EXTENSIONS,
    TEXT_EXTENSIONS,
    FilePattern,
    get_metadata_key,
    get_output_key,
)

# --- Strategies ---

# ディレクトリプレフィックスの生成
_prefix_strategy = st.one_of(
    st.just(""),
    st.text(
        alphabet=string.ascii_letters + string.digits + "-_/",
        min_size=1,
        max_size=50,
    ).map(lambda s: s.rstrip("/") + "/"),
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


# 拡張子の大文字・小文字バリエーションを生成
def _case_variant(ext: str) -> st.SearchStrategy[str]:
    """拡張子の大文字・小文字バリエーションを生成."""
    return st.sampled_from([
        ext.lower(),
        ext.upper(),
        ext.lower()[0] + ext.upper()[1:],
    ])


_anydoc_ext_strategy = st.sampled_from(sorted(ANYDOC_EXTENSIONS)).flatmap(_case_variant)
_text_ext_strategy = st.sampled_from(sorted(TEXT_EXTENSIONS)).flatmap(_case_variant)

# ANYDOC対応のオブジェクトキー
anydoc_key_strategy = st.builds(
    _make_object_key, _prefix_strategy, _filename_strategy, _anydoc_ext_strategy
)

# TEXT対応のオブジェクトキー
text_key_strategy = st.builds(
    _make_object_key, _prefix_strategy, _filename_strategy, _text_ext_strategy
)

# 任意のS3オブジェクトキー（パターン①②共通で使用可能）
any_key_strategy = st.text(
    alphabet=string.ascii_letters + string.digits + "-_./!@#$%^&()+={} ",
    min_size=1,
    max_size=80,
)


# --- Property 3: 出力キー命名の非衝突性 ---


class TestOutputKeyNonCollision:
    """Property 3: 出力キー命名の非衝突性.

    任意の異なる入力キーのペアに対して、同一パターンであれば
    get_output_key() の結果も異なる（キーの衝突が発生しない）。

    **Validates: Requirements 7.1, 7.2, 7.3**
    """

    @given(key1=anydoc_key_strategy, key2=anydoc_key_strategy)
    @settings(max_examples=500)
    def test_different_anydoc_keys_produce_different_output_keys(
        self, key1: str, key2: str
    ) -> None:
        """パターン①: 異なるソースキーからは異なる出力キーが生成される."""
        # 同一キーのペアは非衝突性の検証対象外
        if key1 == key2:
            return

        output1 = get_output_key(key1, FilePattern.ANYDOC_CONVERT)
        output2 = get_output_key(key2, FilePattern.ANYDOC_CONVERT)
        assert output1 != output2, (
            f"Key collision detected for ANYDOC_CONVERT:\n"
            f"  key1='{key1}' → '{output1}'\n"
            f"  key2='{key2}' → '{output2}'"
        )

    @given(key1=text_key_strategy, key2=text_key_strategy)
    @settings(max_examples=500)
    def test_different_text_keys_produce_different_output_keys(
        self, key1: str, key2: str
    ) -> None:
        """パターン②: 異なるソースキーからは異なる出力キーが生成される."""
        if key1 == key2:
            return

        output1 = get_output_key(key1, FilePattern.TEXT_COPY)
        output2 = get_output_key(key2, FilePattern.TEXT_COPY)
        assert output1 != output2, (
            f"Key collision detected for TEXT_COPY:\n"
            f"  key1='{key1}' → '{output1}'\n"
            f"  key2='{key2}' → '{output2}'"
        )

    @given(source_key=anydoc_key_strategy)
    @settings(max_examples=300)
    def test_anydoc_convert_appends_md_suffix(self, source_key: str) -> None:
        """パターン①: 出力キーは "{source_key}.md" 形式である."""
        output_key = get_output_key(source_key, FilePattern.ANYDOC_CONVERT)
        assert output_key == f"{source_key}.md", (
            f"Expected '{source_key}.md', got '{output_key}'"
        )

    @given(source_key=text_key_strategy)
    @settings(max_examples=300)
    def test_text_copy_equals_source_key(self, source_key: str) -> None:
        """パターン②: 出力キーは入力キーと同一である."""
        output_key = get_output_key(source_key, FilePattern.TEXT_COPY)
        assert output_key == source_key, (
            f"Expected '{source_key}', got '{output_key}'"
        )

    @given(source_key=any_key_strategy)
    @settings(max_examples=300)
    def test_skip_returns_none(self, source_key: str) -> None:
        """パターン③: 出力キーはNoneである."""
        output_key = get_output_key(source_key, FilePattern.SKIP)
        assert output_key is None, (
            f"Expected None for SKIP, got '{output_key}'"
        )

    @given(output_key=any_key_strategy)
    @settings(max_examples=300)
    def test_metadata_key_appends_metadata_json(self, output_key: str) -> None:
        """メタデータキーは常に ".metadata.json" サフィックスが付与される."""
        metadata_key = get_metadata_key(output_key)
        assert metadata_key == f"{output_key}.metadata.json", (
            f"Expected '{output_key}.metadata.json', got '{metadata_key}'"
        )
