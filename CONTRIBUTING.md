# コントリビューションガイド / Contributing Guide

AnyDoc RAG Preprocessor に興味を持っていただきありがとうございます。バグ報告・機能提案・Pull Request、どれも歓迎します。

*English follows Japanese.*

---

## 日本語

### はじめる前に

- 大きめの変更（アーキテクチャの変更、新しい AWS リソースの追加など）を考えている場合は、まず Issue を立てて方向性をすり合わせてください。書いてから「その方針は取らない」となるのはお互いに残念なので。
- 小さな修正（typo、ドキュメントの改善、テストの追加）は、Issue なしでいきなり PR を送ってもらって構いません。

### 開発環境のセットアップ

```bash
git clone https://github.com/akira-sato22/anydoc-RAG-preprocessor.git
cd anydoc-RAG-preprocessor

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r tests/requirements-test.txt
pytest
```

24件のテストがすべて通れば準備完了です。AWS アカウントがなくても、テストと `cfn-lint` によるテンプレート検証までは動きます。

### 変更を送るまで

1. リポジトリを fork して、ブランチを切ります（例: `feat/sns-notification`, `fix/large-file-timeout`）。
2. 変更を加えます。
3. **テストを追加します。** ロジックの変更には対応するテストが必要です。
4. ローカルで確認します。

   ```bash
   pytest
   pip install cfn-lint && cfn-lint template.yaml   # テンプレートを変更した場合
   ```

5. コミットして push し、Pull Request を作成します。

### コーディング規約

このリポジトリは既存のスタイルに合わせることを最優先にしてください。具体的には:

- **型ヒントを付ける。** 引数・戻り値ともに。
- **docstring は日本語**で、Args / Returns / Raises を書く。既存の `src/convert_document/app.py` の書き方に揃えてください。
- **ログは構造化する。** `logger.info("message", extra={"key": value})` の形式。文字列連結でコンテキストを埋め込まない。
- **依存関係はピン留めする。** `requirements.txt` には `==` でバージョンを固定します（例: `firecrawl-anydoc==0.1.9`）。

### テストの方針

このプロジェクトは [hypothesis](https://hypothesis.readthedocs.io/) によるプロパティテストを重視しています。純粋関数（`classify_file`、`get_output_key`、`generate_metadata` など）に手を入れる場合は、個別の例だけでなく「守られるべき性質」を検証するテストを検討してください。

たとえば `get_output_key` なら「異なる入力キーからは必ず異なる出力キーが出る」が性質です。副作用のある関数（S3 アクセスなど）は `tests/unit/` でモックを使ってテストします。

### コミットメッセージ

[Conventional Commits](https://www.conventionalcommits.org/) 形式を使っています。

```
feat(convert-document): add SNS notification on conversion failure
fix(statemachine): correct retry backoff rate
docs(readme): clarify ECR setup step
test(property): add case-insensitivity test for classify_file
chore(ci): bump actions/checkout to v5
```

### Pull Request のチェックリスト

- [ ] `pytest` が通る
- [ ] ロジックの変更にテストを追加した
- [ ] `template.yaml` を変更したなら `cfn-lint` が通る
- [ ] 挙動が変わるなら README を更新した
- [ ] コミットメッセージが Conventional Commits 形式

### バグ報告のコツ

再現に必要な情報があると、修正がぐっと速くなります。

- 入力ファイルの**拡張子とおおよそのサイズ**（ファイル自体は不要です。機密文書は絶対に添付しないでください）
- CloudWatch Logs の該当部分（**バケット名やアカウント ID はマスクしてください**）
- Step Functions の実行結果（成功 / 失敗、どのステートで止まったか）
- `sam --version` の出力

---

## English

### Before you start

- For larger changes (architecture changes, new AWS resources), please open an issue first so we can agree on direction. It's no fun for anyone to write code that then gets turned down.
- For small fixes (typos, docs, extra tests), just send the PR directly.

### Setting up

```bash
git clone https://github.com/akira-sato22/anydoc-RAG-preprocessor.git
cd anydoc-RAG-preprocessor

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r tests/requirements-test.txt
pytest
```

If all 24 tests pass, you're set. You don't need an AWS account to run the tests or lint the template.

### Submitting a change

1. Fork the repo and create a branch (e.g. `feat/sns-notification`, `fix/large-file-timeout`).
2. Make your change.
3. **Add tests.** Logic changes need matching tests.
4. Verify locally:

   ```bash
   pytest
   pip install cfn-lint && cfn-lint template.yaml   # if you touched the template
   ```

5. Commit, push, and open a pull request.

### Code style

Match the surrounding code. Concretely:

- **Use type hints** on parameters and return values.
- **Docstrings are written in Japanese** with Args / Returns / Raises sections, following the existing style in `src/convert_document/app.py`. Japanese docstrings are the established convention here — please keep it consistent rather than mixing languages within the module.
- **Log structurally**: `logger.info("message", extra={"key": value})`. Don't build context into the message string.
- **Pin dependencies** with `==` in `requirements.txt` (e.g. `firecrawl-anydoc==0.1.9`).

### Testing approach

This project leans on [hypothesis](https://hypothesis.readthedocs.io/) property tests. When touching a pure function (`classify_file`, `get_output_key`, `generate_metadata`), consider testing the *property* that must hold rather than only specific examples — for `get_output_key`, that property is "distinct input keys always produce distinct output keys." Functions with side effects (S3 access) are tested with mocks in `tests/unit/`.

### Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(convert-document): add SNS notification on conversion failure
fix(statemachine): correct retry backoff rate
docs(readme): clarify ECR setup step
```

### Pull request checklist

- [ ] `pytest` passes
- [ ] Tests added for logic changes
- [ ] `cfn-lint` passes if `template.yaml` changed
- [ ] README updated if behavior changed
- [ ] Commit messages follow Conventional Commits

### Filing a good bug report

- The input file's **extension and approximate size** (don't attach the file — never attach confidential documents)
- The relevant CloudWatch Logs excerpt, with **bucket names and account IDs redacted**
- The Step Functions execution result (succeeded/failed, and which state it stopped at)
- Output of `sam --version`

---

Thanks for helping out. 🙏
