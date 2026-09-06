# 翻訳採用ポリシー — Phase 1B準備

## 原則と優先順位

AoK / AoC日本語版で実際に使用された公式訳を原則として基準訳とする。
DEで日本語だけが変更された場合、「現代的」「直訳に近い」「一般的な日本語として自然」という理由だけではDE訳を優先しない。
Legacyの基準訳へ戻すことを原則的な候補とし、採用の例外には具体的な根拠を残す。

1. AoK/AoC日本語版で実際に使用された公式訳
2. HD日本語版で継承された訳
3. DE既存訳
4. 新規コンテンツではLegacy日本語版の命名規則を参考に新訳を検討

現在の意味・仕様を判断する際はDE英語を参照する。Legacy訳を説明文や現在の仕様の絶対的な正解としない。
「古いから悪い」「新しいから良い」という評価をしない。AoKとAoCが競合するとき、あるいはAoC DLLのロード順に依存するときは優先順位を推測しない。

Blacksmithの「鉄工所」、Monasteryの「神殿」、Universityの「学問所」、Siege Workshopの「包囲攻撃訓練所」、Crossbowmanの「石弓射手」、Elite Samuraiの「剣豪」、Fire Shipの「火炎船」は、この原則に基づく復元候補となる。
ただし例示はID対応や資料確認を省略する理由にはならない。

「Elite → 精鋭」がDE内で一貫していても、それだけでは採用理由にしない。
「剣豪」「重装亀甲船」等の固有のLegacy名称は個別に復元候補として評価する。
系列の一括置換は行わない。

## 要個別判断となる例外

- 現在のゲーム仕様・概念・意味が変わった可能性がある。
- 英語原文自体がLegacy時代から変わっている。
- 同じString IDが別用途に再利用されている。
- DLC等の新規コンテンツとの整合性に重大な問題が生じる。
- Legacyにも明白な誤訳・不整合がある。
- 現代では著しく誤解を招く、または不適切になっている。
- AoK/AoC/HD間ですでに訳語が安定していない。
- DLLの収録関係・ロード順が未確定で、実際のゲーム表示を確定できない。

例外は内容・用途・一次資料やゲーム内確認の根拠を添えてレビューする。単なる好みや新旧だけの評価は根拠としない。
The Last Chieftainsの名称でもID一致だけで旧訳を復元しない。英語と説明によって旧用途と新用途の対応を確認する。
Chroniclesは独立した文脈として扱い、通常AoE2の宗教・軍事などの命名規則を機械的に適用しない。

## 候補レポートの分類

| 分類 | 意味 |
|---|---|
| restore_candidate | 資料の一致から原則復元を強く推奨できる候補。最終採用ではない |
| manual_review | 競合・意味・用途・対応関係などの個別確認が必要 |
| keep_de_candidate | 復元変更をしない具体的な根拠がある候補 |
| new_content | 既存の基準訳を特定できず、新規翻訳方針の調査が必要な候補 |
| id_reuse | 別用途へのID再利用を確認し、同IDによるLegacy復元が無効な候補 |

今回の機械判定では keep_de_candidate を「Legacy/HD/DEがすでに一致する名称」に限定する。
DEの変更訳が優れているという評価ではない。人間が例外に基づきDE維持を提案するときは、その独立した根拠を記録する。
new_content は収録資料に同IDがなく、HD英語名称にも同名がない場合の暫定調査分類。
Legacy英語や別名・別IDを網羅できていないため、概念そのものが新規であるとは断定しない。

## 自動抽出の範囲と判定順

Phase 1Aの full_name 候補を母集団とする。compactラベル、未確定別名は除外し、関連IDとして別途レビューする。
これは完全なゲームオブジェクト一覧ではない。Phase 1Aの分類・検出漏れ・稼働中コンテンツの不確実性を引き継ぐ。

1. 重複、不正入力は manual_review。AoCの同値重複にも優先順位を導入しない。
2. 確認済みID再利用の登録根拠と現在のHD/DE英語SHA-256が一致すれば id_reuse。不一致なら根拠が古いものとして manual_review。
3. データセット未配置、DE値欠損は manual_review。
4. 資料上の新規条件を満たせば new_content。Chroniclesでも復元提案はしない。
5. core以外、分類不明、名称と英語説明の不一致は manual_review。
6. HD/DE英語が完全一致しない場合は manual_review。改名とID再利用を同一視しない。
7. 一意な非空Legacy訳が最低1世代に存在し、存在するAoK/AoC訳すべてとHD日本語が完全一致することを確認する。
8. エスケープ・マークアップ・プレースホルダーを含む比較は構文レビューに回す。
9. DEも同じなら keep_de_candidate。DEだけ異なれば restore_candidate とし、Legacyの値をそのまま proposed JP に記録する。

空白も含む保存値の完全一致で比較する。欠損を補完せず、AoCにAoKを自動継承させない。
DLLのゼロ長スロットは未定義と空訳の区別ができないため、非空の基準訳として使わない。
重複は出現ごとの値・LANGID・ブロック・スロット・オフセットを保持する。

source-corroborated は収録資料の一致の確度であり、採用や意味継続の確度ではない。
手元にLegacy英語はなく、HD/DE英語の一致は旧英語原文不変の証明ではない。
AoKのみとHDの一致から候補は作れるが、実ゲーム表示やDLLロード関係を確定したとは扱わない。
全件に human_approval_required / legacy_english_unavailable / runtime_display_unverified を付ける。
最終採用前に仕様・実表示・例外を人間が確認する。

## CLIと成果物

```powershell
python -m tools.localization restoration
python -m tools.localization restoration --classification restore_candidate --limit 25
python -m tools.localization restoration --output-dir reports/phase1b
python -m unittest discover -v
```

出力は candidates.tsv と summary.md。既存ファイルは上書きしないので再実行時は別ディレクトリを指定する。
分類フィルターを指定して出力した場合、件数はフィルター後の母集団を示す。
標準出力は最大200件、既定25件。ファイル出力は正式名称の限定一覧のみで、公式ローカライズ全文を複製しない。

TSVはID、category、content family、分類、DE EN/JP・HD EN/JP・AoK/AoC JP、proposed JP、confidence、flags、review reason、全出現のsource、名称リンクの根拠、関連ID、系列を持つ。
文字列セルはJSON表現で、空白・エスケープを保存し表計算ソフトの式として解釈されるのを避ける。
missing / dataset_unavailable / ambiguous を区別し、曖昧な値は全出現をJSONで格納する。proposed JP は復元候補以外 null。
サマリーに入力ファイルSHA-256、分類ルール・例外根拠・本ポリシーのSHA-256を記録する。
既存CLI同様、入力診断や重複が残れば生成成功でも終了コード1。エラーは2。

確認済みID再利用は `tools/localization/restoration_evidence.json` にID・英語値の指紋・用途変更の理由を記録する。
これは確認済みの小さな集合であり、再利用の全件リストではない。他の英語変更は個別判断のまま残す。

## 採用に進む際の記録とSource保護

レビュー担当者、判断日、対象IDと用途、現在英語、収録訳、採用案、根拠、例外検討、系列・関連ラベルへの影響、ゲーム内確認、承認状態を記録する。
このPhaseは方針・候補・根拠のみで、翻訳ファイルやmodを変更・生成しない。
source以下は絶対に変更せず、公式資料・巨大な生成物をGitへ追加しない。レポートはgitignoreされたreports以下に限定する。
作業前後のSHA-256でsourceと翻訳ファイルの不変を検証する。
