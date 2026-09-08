# Phase 1D blocked audit

公式source、人間裁定、Mod用翻訳、既存patch planを変更しない独立したdry-run監査。
apply機能はない。

```powershell
python -m tools.localization blocked-audit
# 再生成時は別の出力先を指定する
python -m tools.localization blocked-audit --output-dir reports/phase1d-blocked-audit-next
python -m tools.localization blocked-review
python -m unittest discover -s tests -v
```

入力は `--scope-dir`（既定 `reports/phase1c-normalized`）、`--ledger`
（既定 `reviews/phase1b-decisions.json`）、`--plan-dir`（既定 `reports/phase1d`）。
Phase 1Dの全検証を再実行し、保存済みpatch-plan.json / blocked.jsonと一致しなければ出力を拒否する。
source hash、現在値、裁定signature、英語の用途、名称span、occurrence、競合の検証は緩和しない。
未解決候補または既存dataset重複がある場合、CLI終了コードは1になる。

## 改行保持の十分条件

以下をすべて満たす位置のみ `auto_resolvable` とする。

1. Phase 1Dの失敗理由が `technical_structure_changed` だけで、その原因がlayout tokenだけ。
2. 名称spanの技術tokenが表示用改行・タブ等の1個だけ。その他の技術tokenはspan内にない。
3. canonical translationに明示的な半角空白の語区切りがある。
4. 改行の左右の少なくとも片側がcanonicalの区切りの片側と完全一致する（2文字以上の構成要素）。一致する区切りは一意。
5. その区切りを元のlayout separator（前後の空白も含む）で置き換えると、canonicalとのnormalized comparisonが同一になる。
6. 名称spanの外側はそのまま保持し、文字列全体の技術token列が順序・個数・値を含め完全一致する。
7. 同じsource occurrenceの全候補が安全に解決でき、異なる置換の要求やspan重複がない。

文字数の位置合わせ、類似度、辞書による語分割、翻訳語の新たな裁定は使わない。
`精鋭\nベルセルク` → `エリート\nベルセルク` は一致する右構成要素を根拠にできる。
`精鋭\nロングボウ兵` → `エリート ロングボウ` は両側が変わるので保留する。
`精鋭\n連弩兵` → `改良型連弩兵` は採用訳に明示的な語区切りがなく、機械的に区切りを補わない。
この十分条件を満たさないこと自体は、原理的に自動処理不可能であることを意味しない。
追加の構成要素対応を人間が記録すれば、将来の監査で検証可能になる。

normalized-equivalentのTeutonic Knight / Archery Rangeには変更候補を生成しない。
タグやplaceholderを含むHelpも、span外を保持した全体token比較を行う。
token抽出は既存Phase 1Dの規則を再利用し、`<b>`、`<i>`、`<cost>`、printf、brace、escape等を翻訳本文と分離する。
原因表示ではlayout / markup / placeholder / その他に分けるが、安全判定は分類名に依存せず完全なtoken列を比較する。

## 出力

`reports/phase1d-blocked-audit/` に以下を生成する（Git対象外）。

- `blocked-audit.tsv`: candidate単位。JSONエンコードのセルで元の改行・escapeを保存。87行。
- `blocked-summary.md`: 原因、候補件数、統合シミュレーション、残る位置。
- `auto-resolvable.json`: 安全条件を満たすsource occurrenceとbefore/after、span、hash、signature、英語provenance。
- `manual-review.json`: 未解決occurrenceと理由。未承認のafterは生成しない。

同じIDでもpath/lineが異なれば別の出現。IDだけの解決や伝播は行わない。
同じspan・同じ置換の複数裁定は1 operationとして集計する。
原因分類は複数該当し得るため、将来のデータではカテゴリ合計が全件数を超える場合がある。
各カテゴリのcandidate数は、その原因で位置全体が保留された候補数。

## 実データ監査結果

46位置・87候補はすべて保存値 `\n` の消失によるlayout差。
markup、placeholder、span非一意、現在値、hash、duplicate、overlap、その他の原因はそれぞれ0。
33位置・66候補を33 operationsへ統合でき、既存300と合わせて333 operationsの想定。
13位置・21候補は人間レビューに残る。既存patch planへの統合は実行していない。

auto-resolvableは構造上の再現可能性を示す。文字幅や表示領域への収まりを保証するものではなく、
実際にModを構築するPhaseではゲーム内表示の確認も必要。

## JSON文字コードとartifact検証

Windows PowerShell 5.1の `Get-Content` は、BOMのないUTF-8を文字コード指定なしで読むと
ANSIとして解釈する。以前の出力はUTF-8としては正常なJSONだったが、この読込経路では
日本語が文字化けし、17415付近などで `ConvertFrom-Json` も失敗した。

blocked auditのJSONは標準 `json.dumps(ensure_ascii=True, allow_nan=False)` で生成し、
UTF-8（BOMなし）で保存する。UnicodeはJSON標準の `\uXXXX` escapeで表現される。
ASCIIはUTF-8の部分集合なのでPowerShell 5.1の既定読込でも壊れず、パース後の日本語は完全に元へ戻る。
sourceや裁定のUnicode・レイアウトescapeを置換・正規化する変更ではない。
TSVとMarkdownは引き続き日本語のUTF-8。PowerShellでは明示的な文字コード指定を推奨する。

```powershell
$review = Get-Content -Raw -Encoding UTF8 reports/phase1d-blocked-audit/manual-review.json | ConvertFrom-Json
python -m tools.localization blocked-review
# 他の保存済みartifactを表示（sourceの再読込は不要）
python -m tools.localization blocked-review --input reports/phase1d-blocked-audit-next/manual-review.json
```

各JSON出力直後にディスク上のファイルを `json.load()` で再読込し、生成前のオブジェクトと
全フィールドを比較する。非JSON定数・重複キーは拒否する。
追加のEnglishフィールドは監査済みのDE ENを記録するだけで、候補の選別や裁定は変更しない。
CLIは保存済みJSONからID、English、current、canonical、理由を表示する。

テストは17415の日本語・保存値 `\n`、引用符、実改行、補助平面Unicode等のround-trip、
全生成JSONの再読込、Windows PowerShellでの既定読込（利用可能な環境）、
ローカルsourceが存在する場合の13位置・21候補の実データ回帰を検証する。
公式データはテストfixtureへコピーしない。
