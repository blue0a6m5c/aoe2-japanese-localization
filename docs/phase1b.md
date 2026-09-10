# Phase 1B 採用候補レビュー

現行正本は従来の名称104件＋Phase 2A wording 64 concept＋文脈付き全文29件＝197裁定。restore 90 / keep_de 32 / revise 75。
387 operationsへ統合した。現行387-entry翻訳は[実機確認](game-validation.md)のhashに拘束される。
最新仕様と再生成手順は [context overrides](context-overrides.md) を参照。以下の80/85件は初回レビューの履歴。

Phase 2Aで追加した64 conceptと249 target IDのrole別bindingは [Phase 2A wording ledger](phase2a-wording-ledger.md) に記録する。従来104 recordsは変更せず、Phase 2A recordだけにconcept-scoped bindingを追加した。

## 2026-09-08 人間裁定の反映

正本は [reviews/phase1b-decisions.json](../reviews/phase1b-decisions.json)。生成レポートとは独立してGit管理する入力データである。
現在のadoption CLIはこの正本を自動的に読み、人間裁定を優先する。
初回未承認のレポートは履歴として残し、新しいレポートを `reports/phase1b/human-review/` に生成した。

元の80件は restore 77 / keep_de 1 / revise 2。追加の5件も明示された人間裁定として保持する。
追加ID: 5115 Royal Janissary、5118 Flamethrower、5130 Elite Organ Gun、5186 Palisade Gate、5205 Fortified Palisade Wall。
すべて現行DE英語とHelpに存在することを確認した。全85件は restore 81 / keep_de 2 / revise 2。

decision / proposed_jp / reason / signature は以前の自動提案・根拠を保存する。
reviewer_* は人間裁定、human_signature はその裁定時の資料の指紋。
effective_decision / effective_proposed_jp は指紋が一致する人間裁定を優先する表示であり、Modへの適用処理ではない。
approval_status は一致時 approved、不一致時 approved_requires_revalidation。後者でも人間の指定値を破棄しない。
sourceやHelpが消えた裁定も正本に残り、human-review-audit.jsonのabsent_source_idsへ報告する。

追加出力 `human-review-audit.json` に候補漏れ、追加ID、原資料との不一致、関連IDの整合性を記録する。
同じ英語名に加えて共有Help、名称に一致するアクションHelp、または対応するアクションボタンがある場合にのみ同一名称用途の証拠として扱う。
同じ名称への人間裁定同士は採用訳の一致を確認する。未裁定の関連IDは実装時の確認対象として残し、裁定を自動コピーしない。
系列名・語句一致だけのリンクは not_propagated。内部ゲーム参照まで検証したとは扱わない。

以下は人間レビュー前の提案段階の仕様。全件pendingという記述は初回レポートについてのものであり、明示された人間裁定を撤回するものではない。

`restore_candidate` を採用済み訳とは扱わず、未承認の編集提案に整理する。
元の80件の一覧を変更せず、その次のレビュー段階として追加した。
採用原則は [localization-policy.md](localization-policy.md) を参照する。

## 実行

```powershell
python -m tools.localization adoption --output-dir reports/phase1b/review
python -m unittest discover -v
```

既存ファイルは上書きしない。再生成時は別ディレクトリを指定する。
原資料更新で候補母集団が変わった場合は現在の候補を出力し、80件を固定的に仮定しない。

- `review.tsv`: 候補ごとの6世代値、旧訳候補、提案訳、Decision、Confidence、理由、上流分類、関連ID、出典、見出し不一致。
- `evidence.tsv`: 関連名称・作成／建造／研究／進化ボタン・Helpの日英およびLegacy値と全出現位置。主表とString IDで結合する。
- `review-summary.md`: 全候補と個別理由、ID再利用の問題、入力SHA-256と編集根拠の指紋。
- `definite-bugs.json`: 復元表と分けた確定的な比較・復元上の問題。現在のDEの翻訳バグを確認したかどうかも別フィールドで保持する。

文字列は既存レポートと同じJSONセル表現で原文の空白・エスケープを保持する。
missing と ambiguous を補完しない。曖昧な出現は provenance に全件保持する。
公式全文の出力ではなく、80名称候補に直接関係する限定資料だけをreportsへ生成する。

## 判断と承認

Decision は `restore / keep_de / revise / manual_review`。
restore は継承訳への復元提案、keep_de は具体的な意味・用途に基づく維持提案、revise は別案を根拠付きで提案できる場合、manual_review は未解決事項がある場合。
今回、根拠のない新訳を埋めるために revise を使用しない。
manual_review の Proposed Japanese は null。元の復元候補は Legacy Candidate Japanese に残る。

全件の approval_status は pending。人間が記入する reviewer / reviewer_decision / reviewer_proposed_jp / reviewer_notes を別に設けた。
生成時の提案や原資料を編集せず、人間の判断欄を用いて採用を進める。自動適用や翻訳ファイルの生成処理はない。

Confidence:

- high: ローカルHD/DE Helpから主要用途の継続と提案の根拠を個別に確認できたもの。
- medium: 関連証拠はあるが、語義・系列や仕様差の判断が残るもの。
- low: 名称一致を超えた意味継続や歴史語義をまだ確定できないもの。

high も実ゲーム表示やLegacy英語の確認済みを意味しない。Legacy英語は未収集で、DLLのロード順も未確定。
現在の用途とは今回、ローカルDE英語Helpが示す用途を指す。ゲーム内部データ・画面表示を検証したとは主張しない。
個別レビューを記録していない候補は一律復元せず manual_review に残す。

## 上流提案の分類

- definite_bug: 異なる概念の同一ID比較など、明確な誤り。現在のDE翻訳バグと比較ツール上の危険を区別する。
- consistency_fix: 同じ名称とリンクされたHelp見出し等に表記不一致がある。解消先の訳を決めることとは分ける。
- legacy_restoration: 継承訳を基準とする本プロジェクトの復元提案。
- subjective: 歴史語義・音写・意味の適切さなど、編集判断を伴うもの。

主分類とは別に upstream_classes も保持する。表記不一致があっても、それだけで旧訳が上流に採用される根拠とはしない。

## 関連文字列と代表例

同じDEファイル内の英語名称一致（改行等を正規化した比較）、Create/Build/Research/Upgrade to/Advance toボタン、およびPhase 1Aで確認したHelpリンクから関連資料を集める。
IDへの固定加算で関連性を決めない。単なる名称一致は実ゲーム内部の参照を証明しないため、その関係をレポートに明示する。
Samurai、Galleon/Cannon Galleon、Fire Ship、Turtle Shipは系列名も明示して収集する。

建物5種、Imperial Age、Crossbowman、Fire Ship、Samurai、Galleon系列等を個別確認した編集理由は `tools/localization/adoption_cases.json` に保存。
名称とリンクされたHelpの全世代値・出現位置から指紋を計算し、更新後に一致しなければ manual_review に戻す。
このファイルには翻訳原文の大量コピーや採用訳は収録しない。

RocketryではHDとDEの技術効果が変化しているため、旧名復元を保留しDE維持を提案した。
Champi Scoutの5526はHDのJoan of ArcのIDを再利用している。旧英雄名の復元は明確な誤りになる。
ただし調査時のDE名称5526、ボタン6526、Help26526はチャンピ斥候として一致しており、現在のDEにジャンヌ表記が残っている証拠とはしない。

Chroniclesへ通常AoE2の名称体系を波及させない。名称の修正と説明文の古いゲーム仕様への巻き戻しは別物である。
sourceは読み取り専用とし、作業前後のSHA-256を照合する。このPhaseで翻訳文字列は変更しない。
