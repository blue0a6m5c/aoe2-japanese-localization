# Phase 1D human layout decisions and integrated dry-run plan

現行は131裁定、339 baseline operations＋自動layout 33＋人間layout 13＝385 operations（全文227 / span158）。
blocked / conflictsは0。以下の300/346件は初回統合の履歴であり、最新の入力パスは [再生成手順](context-overrides.md) を使用する。

`reviews/phase1d-layout-decisions.json` はユーザーが指定した13個の改行位置の正本。
Phase 1Bの名称裁定とは別管理し、その採用語句を変更しない。
レコードはString IDだけでなくsource path / line、現在値、名称span、ファイルhash、
英語provenance、関連するPhase 1B裁定signature・canonicalを束ねたbindingを持つ。
record signatureはそのbindingと人間指定replacementを含む全内容のSHA-256。
署名は資料変更を検出する指紋であり、暗号学的な本人認証ではない。

```powershell
python -m tools.localization layout-plan
# 再生成には新しい出力先を使用
python -m tools.localization layout-plan --output-dir reports/phase1d-layout-next
python -m unittest discover -s tests -q
```

既定出力は `reports/phase1d-layout/` のpatch-plan.json、patch-plan.tsv、patch-summary.md、blocked.json。
元の `reports/phase1d/` は変更しない。JSONはUTF-8のUnicode escape表現で保存し、
書込後に再読込して全フィールドを照合する。CLIは既存dataset重複のため終了コード1を返し得る。

Phase 1Dの全検証とblocked auditを再実行し、次の3種類を区別して統合する。

- `baseline_phase1d`: 既存300 operations。元のbefore/afterと証拠は維持。
- `automatic_layout`: 一致する構成要素から安全に改行保持できる33位置。規則名と根拠を保持。
- `human_layout`: 正本の13位置。review ID、reviewer、record signature、layout ledger hashを保持。

人間指定の改行位置は自動規則を満たす必要はないが、canonicalとのnormalized一致、
文字列全体の技術token列の完全一致、出現位置と証拠の一致は必須。
人間指定でも別の訳語、タグ・placeholderの追加削除、無関係な出現への適用は許可しない。
同じ出現を二重指定した正本や未確認の出現はerror、資料の不一致や構造変更はblocked。
未裁定箇所を推測で補わない。同じspan・同じreplacementの候補を統合し、異値・overlapはconflict。

今回の結果は346 operations（全文186、span160）、346 ID、551候補。
元のblocked 46位置は自動33＋人間13で解決し、blocked/conflict/duplicate IDを含むpatchは0。
source、人間裁定の既存ファイル、Mod用翻訳、従来のレポートは変更していない。
この処理はdry-run計画だけを出力し、apply機能は持たない。実適用前のゲーム内表示検証は別工程。
