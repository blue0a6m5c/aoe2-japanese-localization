# Phase 1C 適用範囲監査

> Current pipeline: [context-bound overrides](context-overrides.md). 104 name + 29 direct decisions; 387 operations, conflicts 0, final blocked 0. Counts and default paths below document the original phase baseline. Use matching current scope/plan paths.

## 表示正規化と重複監査の追加

改良版のレポートは `reports/phase1c-normalized/` に保存し、元の556件のrequiredを含むレポートは比較用に残した。
再生成: `python -m tools.localization scope-audit --output-dir reports/phase1c-normalized-next`。

`literal_stored_value_equal` は対象箇所の保存値と採用訳の完全一致。
`normalized_equal` は表示用空白を除いた比較キー同士の一致。
`normalized_equivalent` は後者のみ一致する場合で、`comparison_result` にも明示する。
`normalized_matched_jp` / `normalized_effective_jp` は検証用のキーであり、翻訳出力ではない。
`literal_scope_class` / `literal_change_candidate` は正規化前の判定を保持する。

layout_whitespace_v1はUnicode空白文字と、単独のバックスラッシュに続くn/r/tの表示用エスケープを比較キーから除く。
エスケープされたバックスラッシュ、引用符、未知のエスケープ、タグ、プレースホルダー、句読点、全角半角、長音は変換しない。
例: `チュートン\nナイト` と `チュートン ナイト`、`射手\n育成所` と `射手育成所` は同じキーになる。
保存値・対象位置・レイアウトは完全に保持する。語義の同一性を正規化だけで認定しない。
既にrequired/recommendedの根拠があり正規化で一致する箇所はalready_consistentへ分類し、change_candidate=falseとする。
review/unrelatedの箇所は、正規化だけを理由に昇格させない。

restore / revise / keep_deの全裁定でeffective_jpを同じようにcanonical translationとして参照する。
keep_deは関連Helpを変更しない指示ではない。Royal Janissaryの26115は「王家のイェニチェリ」から採用訳「近衛イェニチェリ」へのrequiredである。

summary/metadataのrelation_statisticsは、名称本体・共有Help・ボタン・Help見出し等について、総数、実変更候補、normalized-equivalent、literal already-consistent、その他を集計する。
normalized-equivalentとliteral already-consistentは重複しない。元のrequiredの分岐はformer_required_splitで検証できる。

追加のduplicate-audit.jsonは全datasetを監査する。value_countsの同値・異値・その他と、provenance_countsの同ファイル別位置・別ファイル・同一位置の二重取り込み等を独立した軸で集計する。
同値のsafeは値の選択による差がない意味に限定し、Dataset.resolvedやDLL優先順位は変更しない。不正・曖昧な同値はother_invalidとする。
異値は全出現の位置・値SHA-256・最大200文字の抜粋で明示する。原資料に重複が収録されていることと、その原因・ロード順が分かることは区別する。

現行は名称正本 `reviews/phase1b-decisions.json` の104件と、文脈付き全文正本29件を分離して監査する（合計133件）。初回実装は名称85件を対象とした。
source、正本の裁定、Mod用翻訳は変更しない。翻訳適用・置換処理は実装していない。

## 実行と出力

```powershell
python -m tools.localization scope-audit
python -m tools.localization scope-review --class required --limit 10
python -m tools.localization scope-review --class review --limit 10
python -m unittest discover -v
```

既定出力は `reports/phase1c/scope-audit.tsv`、`scope-summary.md`、`scope-metadata.json`。
再生成時は `scope-audit --output-dir reports/phase1c-next` 等を指定する。既存ファイルは上書きしない。
scope-reviewは最新sourceから再計算して表示する読み取り専用コマンド。既定10件、最大200件。
入力重複がある場合は既存CLI同様、レポートが完成しても終了コード1。失敗は2。

## 証拠と分類

Phase 1Aの名称とHelp対応、Phase 1Bのrelated/evidence、同一名称用途の検証、human signatureを再利用する。
正本の全recordsを対象とし、80候補への絞り込みや新しい訳語選択はしない。
署名不一致・対象資料欠損時はreviewに留め、人間裁定そのものを変更しない。

探索はDE日本語の全出現と対応するDE英語、既知の関連IDを対象とする。
現在の日本語名称・採用訳・原資料から得たHelp見出しの異表記を検出する。
ガレオンは明示された語幹も検出する。Eliteを精鋭へ変換する等の新たな命名規則はない。
英語は名称と単純な複数形を語境界付きで検出する。変則的な別称・複雑な語形・代名詞は網羅できない。
日本語・英語とも長い名称を優先し、既知の別ユニット名の内部にある部分一致はunrelatedにする。

| scope_class | 判定 |
|---|---|
| required | 人間裁定の名称本体、共有Helpで対応した同名ラベル、確認済みアクションのボタン・Help見出しで採用訳と異なる |
| recommended | 同じコンテンツファイルのゲームHelp本文に対象英語名と日本語名称が共存し、表記変更が候補になる |
| review | 語句一致だけ、別コンテンツ、対応未確定、署名不一致、重複、不正、日英欠損等 |
| unrelated | 別の既知名称の内部の部分一致、または別対象の名称・系列リンクで対象英語参照を確認できない |
| already_consistent | 対応確認済み表示箇所が採用訳と同一、またはHelp本文で対象英語・採用訳が各1出現して表記が一致 |

`Research Name (effect)` 等の表示も、確認済みアクションと英語名称の完全一致を確認し、日本語の括弧前の名称が1出現の場合だけrequiredの対象とする。効果説明の全文置換ではない。
採用訳と同じ表記がある本文で複数参照の対応が曖昧な場合はreviewに残し、change_candidate=falseとする。

recommendedは文章内の日英の対応を証明したものではない。特に一般名詞、修飾語、複数出現は人間による確認が必要。
既知の長い名称に該当しない複合語や、数値・説明の書き換えによる対応変化を完全には解析できない。
already_consistentはその出現位置についての判定で、同じHelpの他の部分の整合性を保証しない。
異なるファイルのChronicles・キャンペーン等にはrequired/recommendedを波及させずreviewにする。
内部ゲームオブジェクトや実画面の参照確認とは区別する。

## 出現単位と衝突

1行は「裁定ID × 関連文字列のsource出現 × 日本語の対象位置」。同じString IDに複数行があり得る。
start/endは原文のUnicode文字位置による半開区間で、ファイルのバイト位置ではない。
英語だけの参照や旧evidenceだけの候補には位置を捏造せずnullを記録する。
source_pathは既存parserと同じdataset名からの論理パス（例de_jp/filename）で、source_line・SHA-256から原資料を追跡する。

同じ関連IDへの複数裁定参照と、同じ対象箇所への採用訳衝突を分ける。
required/recommended/already_consistentの位置が重なり、異なるeffective_jpを要求する場合をconflictとして報告する。
同一Help内で「鍛冶場」と「大学」を別々に変更するだけなら衝突ではない。
一致した重複要求は一つへ黙って統合せず、裁定との対応を保持する。
unrelatedはchange_candidate=falseで衝突候補にも含めない。

## レポートの読み方

TSVの列は依頼された比較・分類・reviewer欄に加え、位置、抜粋情報、資料SHA-256、人間signature、衝突フラグを持つ。
文字列セルは既存レポートと同じJSON表現。reviewer_decision/reviewer_notesはPhase 1Cの人間記入用で、生成時は空欄。
effective_jp/effective_decisionはPhase 1B正本の値であり、本Phaseでは変更しない。
ただしsignature不一致時に適用可能と誤認させないようevidence_statusとreview分類を併記する。

related_en/related_jpは最大180文字と省略記号の抜粋。全文の大量複製を避け、変更箇所の前後を示す。
excerpted=trueのときは `python -m tools.localization show ID` またはsourceの該当行で全文を確認する。
抜粋だけを置換入力として使用しない。数値、タグ、エスケープ、プレースホルダーの変更案は生成しない。

summaryには全133裁定の内訳、全体件数、出現がない裁定、衝突、重複参照例、注意点を記載。
metadataには複数裁定参照の全件・検出別名・全入力SHA-256・欠損/署名不一致を記録する。
監査開始前後でsourceとreviewsのSHA-256を照合し、変更しなかったことを別途記録する。

次Phaseではrecommended/reviewの文脈を人間が確認し、確定した位置・対象語だけに適用する差分設計、技術構文検証、Modビルド、ゲーム内確認を行う。
