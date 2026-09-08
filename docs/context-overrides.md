# 名称裁定と文脈付き直接override

2026-09-08の火箭系追加を含む現行pipeline。既存129裁定を用途別に分離し、その後ユーザーが明示したShinkichonの名称裁定2件を追加した。合計131裁定。

## 衝突の原因と正本

旧名称ledgerは、裁定した名称を関連する名称・Button・Help見出しへ伝播する。
そこへ全文修正を入れると、同じHelpの名称spanと全文spanが重なる。
また、改行入りの短縮表示の裁定が通常名称へ逆伝播して異なるreplacementを要求していた。
これはsourceの重複IDを解決すれば直る問題ではない。
分離前のscopeは39衝突、patchは10衝突だった。

- `reviews/phase1b-decisions.json`: 名称103件。既存schemaと署名の意味を維持する。
- `reviews/context-overrides.json`: 文脈付き全文裁定28件。関連箇所へ伝播しない。
- `reviews/phase1d-layout-decisions.json`: 従来の人間layout裁定13件。変更なし。

対象27 IDのうち、5064 / 5065 / 7432 / 7470 / 17432は名称、残り22件は直接override。
以前の103件中にも全文の文明選択説明が6件（90280 / 90313 / 90319 / 90327 / 90328 / 90329）あったため、同じ直接override側へ移した。
103→129は26件追加と既存7432の更新。分離の前後で129件のdecision、proposed_jp、notes、expected_de_english、help_ids、既存signatureは一致する。
過去のledgerコピーは履歴資料であり、実行時の入力にはしない。

## 直接overrideのschemaと優先関係

schema_version=1、authority=explicit_context_decisions。各recordには以下を保存する。

- 元の人間裁定の全フィールドと、`kind=context_full_value`、文脈を説明する`context`。
- `target`: 日本語source_path / source_line / source_sha256 / current_value_sha256、英語の出現情報とファイルSHA-256。
- `binding_signature`: binding_signature自身を除いたrecordのJSON（sort_keys=True、ensure_ascii=False）をUTF-8でSHA-256化したもの。
- 移行元ファイルのSHA-256はledgerの`migration_source_sha256`に保持。

指定した出現位置の全文は人間が既に確定した値なので、同じ位置への自動名称伝播より優先する。
伝播側の監査行は消さず、`suppressed_by_context_override`と`suppression_signature`を付け、review / change_candidate=falseとして残す。
直接裁定本文に他の旧名称が残っていても、機械的に書き換えない。必要ならその全文裁定を人間が更新する。
同じIDを二つの正本へ登録することは禁止。複数の直接裁定や重複source IDも暗黙に統合しない。

直接裁定にも従来のsource evidence signatureを要求し、加えてrecordと全文の出現位置を拘束する。
日本語と英語が一意に解決できない、hash/行/値/英語/署名が異なる、技術token列が変わる場合はfail closed。
scope metadataは直接正本のパスと内容hashを保持する。patch生成時は直接監査行と抑制情報を再構成して照合する。
Mod buildは同じ入力からplan全体を再構成し、直接正本のファイルhashもmanifestへ記録する。
名前だけの旧scope・ledger形式も引き続き処理できる。最新ledgerと古いscope/planの混用は検証失敗になる。
明示的に裁定された全文は空白のみの修正も対象になり得る。これは名称伝播のnormalized-equivalent除外とは別の権限であり、技術token列の保存要件は変わらない。

## 再生成コマンド

出力は上書きしない。既に存在する場合は全段階で新しい共通ディレクトリ名を指定する。

```powershell
python -m tools.localization scope-audit --output-dir reports/final/scope
python -m tools.localization patch-plan --scope-dir reports/final/scope --output-dir reports/final/patch
python -m tools.localization layout-plan --scope-dir reports/final/scope --output-dir reports/final/layout
python -m tools.localization mod-build --scope-dir reports/final/scope --plan reports/final/layout/patch-plan.json --output-dir dist/final-mod
python -m tools.localization mod-build --scope-dir reports/final/scope --plan reports/final/layout/patch-plan.json --output-dir dist/final-mod --verify-only
python -m tools.localization mod-package --scope-dir reports/final/scope --plan reports/final/layout/patch-plan.json --input-dir dist/final-mod --output-dir dist/final-local-mod
python -m pytest -q
```

scope-auditは既定で両正本を読む。`--context-overrides PATH`で別の直接正本、`--ledger PATH`で名称正本を指定可能。
直接正本が欠損した場合は停止する。黙って名称のみの部分成果物を生成しない。
`--names-only`は名称だけの監査を明示的に選ぶ互換モード。直接修正が必要な今回の製品生成では使用しない。
scope-reviewにも`--names-only`がある。下流はscope metadataに記録された直接正本を自動検証する。
ローカルsourceには従来から59組の重複dataset/IDがあるため、解析CLIは診断を出して終了1となる場合がある。
これは成功扱いへの丸め込みではない。生成JSONのconflict/blockedと診断を別々に確認する。

## 現行結果

| 段階 | 件数・結果 |
|---|---:|
| 名称 / 文脈付き全文 / 合計裁定 | 103 / 28 / 131 |
| scope required変更候補 | 596 |
| scope conflict_count | 0 |
| 初期patch operations / layout待ち位置 | 339 / 46 |
| patch conflicts | 0 |
| 自動layout / 人間layout | 33 / 13 |
| 最終operations / unique String IDs | 385 / 385 |
| 全文 / span置換 | 227 / 158 |
| 最終blocked / conflicts / 重複ID適用 | 0 / 0 / 0 |
| 直接overrideの変更あり / 既に一致 | 26 / 2 |
| 変更された出力ファイル | 1 |

Phase 1Eの未対象文字列はバイト単位で保持し、期待値・token列も検証する。
Phase 1Fは最終385 IDのみを抽出し、ID集合・保存値の一致とmissing/extra/duplicate/value mismatch=0を検証する。
以前の346件は最初の85裁定版の履歴値。旧85裁定版を再生成して346件になる回帰テストも維持する。

検証: pytest **162 passed / 70 subtests passed**。ユーザーによる10名称の[ゲーム実機確認](game-validation.md)も記録した。
新規テストは全文と名称spanの重複、正本間のID重複、sourceの重複出現、署名・行・hash・英語・tokenの不一致、
scope抑制情報の改変、直接正本の欠損、無関係なロケット文脈、指定27 IDの最終値を保護する。
実データの統合テストはscopeとplanを同じ入力から一緒に生成し、過去の生成物を最新ledgerと混用しない。
source全30ファイルの作業前後SHA-256一致と、既存129裁定の全recordフィールドの保存を確認した。
新しい7438 / 17438の署名、名称と全文overrideの分離、5 IDの最終値の整合性をテストする。
新裁定2件を外すと従来383 operationsをそのまま再現でき、既存operationsは変化しない。
検証結果は `reports/final/preservation.json` と `reports/final/verification.json` に記録する。

## 適用範囲と未裁定事項

Rocket Cartは火箭車、Heavy Rocket Cartは重装火箭車、Rocketryは火箭術。
中国系rocketの全文修正とShinkichonの神機箭は、指定された文脈・IDだけに適用する。
一般の「ロケット」は全文検索置換しない。シナリオ・文明説明も直接裁定がある出現だけが対象。

Shinkichonの名称ID 7438 / 17438は、追加の人間裁定により「神機箭」を正式採用した。
両IDのDE ENはShinkichonで、研究Help 28438を共有する。名称正本にreviseとして記録し、現在のsource evidenceへ署名で拘束する。
8438 / 28438 / 120167の既採用「神機箭」は全文overrideをそのまま維持する。これらからの逆伝播ではなく、今回の明示的な名称裁定を根拠とする。
新たな変更は名称2 IDのみで、従来383 operationsは変更せず385 operationsとなった。公式sourceの「新機箭」は書き換えない。

ゲームへのコピー・起動・公開は行わない。sourceと既存layout裁定は変更せず、生成操作は既存成果物を上書きしない。

## 採用前の整理

署名付き裁定3正本を保全し、実機確認は別の `reviews/game-validation.json` に記録した。
旧ledger作業コピー2件とrootの文字列調査メモは不要になったため削除。回帰テストは現行正本を読み、旧85件の条件をメモリ内で再構成する。
生成途中の重複成果物を整理し、最終成果物を `dist/final-mod` / `dist/final-local-mod` に集約する。
Phase 0〜1Dの調査・レビュー報告は過去の根拠として保持する。生成物・公式sourceをcommitへ含めない。
