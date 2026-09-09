# Phase 2A-1: 構造的証拠に基づくゲーム概念・用語統一監査

Phase 2A設計の最初の実装単位。開発基準は `bbd939d`。
受入試験と決定的再生成照合を完了し、`phase2a-1-bbd939d-r4`を基準runとして正式採用した。
採用訳・裁定・適用計画を作らず、人間が「統一する / 現状維持 / 別概念なので対象外」を判断するための資料を作る。
公式DE JPを監査し、既採用訳を公式sourceへ重ねない。

## 対象と対象外

対象は既存 `gameplay.build_inventory()` が抽出した名称・短縮名称のうち、
分類・familyが確定し、英語Helpとの `verified_offset_and_label` が成立するもの。
既存の確認済みID差と英語名称照合を併用し、ID差だけでは対応付けない。
対応するHelpの先頭名称と、同ファイルの同じ操作・対象名を持つ操作表示を追加する。

生産・研究Helpアンカーを持たないゲームオブジェクトは、`gameplay_rules.json` の
`concept_seeds`に記録したレビュー済みの文字列役割を入口にできる。seedは英語ID、
source path、family、category、relation kind、confidence、provenanceだけを根拠とし、
日本語値を概念同一性や採用訳の根拠にはしない。証拠条件を満たさないseedは
supportedへ昇格せず`unresolved`に残る。

一般UI語彙の新規分類、説明本文、台詞・ナレーション・物語の分類、未知の本文alignmentは対象外。
campaignファイルでも構造的根拠を満たす名称はそのfamily内で扱う。
短い文字列、同じ英語綴り、同じ日本語訳だけを理由に対象へ追加しない。
Chronicles、core、dlc、scenario/heroの既存境界を維持し、review-neededは保留する。

## コマンドと安全制約

```powershell
python -B -m tools.localization term-audit --output-dir reports/phase2a/<new-run>
python -B -m unittest tests.test_term_audit tests.test_localization tests.test_gameplay tests.test_legacy tests.test_scope_normalization -q
```

出力先は新しい `reports/phase2a/<run>/` ディレクトリ。既存runは空でも拒否する。
既存 `write_report()` の出力保護・JSONセルTSV・exclusive createを再利用し、
sourceやreviews等へ解決されるパスも拒否する。書込後に再読込して照合する。
入力に重複・解析診断があれば既存CLI同様に終了コード1、読取・設定エラーは2。
unresolved件数と入力診断は別軸。PE/encodingエラーによる不完全入力では生成しない。

source・reviews・translations・distはCLIの解析前後にSHA-256を照合する。
`mod_build` から利用するのは既存のhash/snapshot検査関数だけで、prepare/generateは呼ばない。
全テストの一括実行には既存Mod生成テストが含まれるため、上記は今回の対象に絞ったテストコマンド。

## 概念とrelation

1. 一意なDE EN/JPと同じデータセット相対ファイルを要求する。
   同じbasenameでもサブディレクトリが異なるものは対応付けない。
2. 一意な英語Helpの先頭アクション、名称照合、既存分類・family、出現パス・行、
   `verified_offset_and_label` を確認する。
3. 一つのHelp出現を概念の基点にする。概念IDはfamily・ENファイル・分類・Help IDから得る安定した指紋。
   同じHelpに直接対応する正式名・短縮名を同じ概念へ結ぶ。
4. 名称に複数の有効なHelp基点があれば、その名称を保留する。
   別のHelp基点を同綴りだけで結合しない。ユニットと同名の進化技術も別概念になる。
5. 同名一致のみの `same_file_label` や未検証offsetはcandidate relationとして保持し、概念へ所属させない。
6. inventory外でも、同一ファイルの既存概念名と英語表記（大文字小文字差を含む）、
   保守的な単複形、または限定した操作語＋完全な概念名が一致する短いラベルは、
   `unclassified_name_candidate`とcoverageの`not_classified`に残す。
   この一致は候補発見専用で、supported membershipには使わない。

「概念」は資料上の構造的対応単位で、ゲーム内部object IDや実行時利用を検証した実体数ではない。
意味が似た複数Helpを統合しないため、実ゲーム概念に対して過分割となる可能性がある。
`runtime_identity_verified=false` を残す。

操作表示は、基点の実アクションと対象名に一致する英語表示（末尾の括弧付き効果説明を許容）だけが候補。
複数概念に該当する操作表示は保留。日本語は、対応Helpの先頭太字名称直後から観測した操作語尾を使い、
操作表示先頭の名称spanを切り出す。既知日本語訳の部分一致ではないので、別訳も抽出できる。
非標準の見出し、語尾が対応しない表示、技術構文を含む不確かな切出しはalignment unresolved。
本文や括弧内の効果説明は出力しない。

## データモデル

| オブジェクト | 主な情報 |
|---|---|
| concept | 概念ID、family、分類、ENファイル、Help基点、操作、英語名、所属出現ID |
| occurrence | 概念ID、String ID、名称/短縮名/操作/見出しのrole、日英term、alignment、日英出現位置・span・値/ファイルhash |
| relation | 名称→Helpまたは概念→操作/見出し、既存evidence、supported/candidate |
| finding | finding ID、種類、対象概念・出現ID、差分、証拠signature、人間記入欄 |
| unresolved | 保留ID、種類、理由、候補概念、元出現の位置・hash、人間記入欄 |
| baseline group | Phase 1Aの英語文字列群、所属ID、概念・finding・unresolvedへの対応 |
| history | 名称IDと概念の対応、6データセットの値/位置/状態、英語継続性の保留情報 |

spanは未展開の保存値に対するUnicode文字indexの半開区間。比較キーをsource位置として使わない。
原文字列・エスケープ・タグ・placeholderは変更しない。
concept/occurrence/finding IDは決定的な識別子。別のevidence signatureがルール・値・位置・hash等を拘束する。
証拠が変わったら以前のレビューを引き継がない。レビュー再取り込み・裁定適用は未実装。

unresolvedは保留レコード数で、String ID数や概念数ではない。同IDの名称対応とHelp基点が別々に保留されることもある。
候補Helpが概念を構成できない場合、その仮の基点IDを `unmaterialized_anchor_ids` に残す。
`candidate_concept_ids` は実際に存在する概念だけを参照する。candidate relationの
Help anchorから一意に既存概念を引ける場合もIDを記録するため、relation表の逆引きは不要。

## Findingsと比較の限界

| kind | 意味 |
|---|---|
| concept_jp_variation | 同じ構造的概念の所属出現で、空白・改行を除いてもJPが異なる |
| name_help_mismatch | 名称/短縮名とHelp見出しが異なる。上記と重複し得る |
| layout_only_variation | 全所属出現がlayout_keyで一致するが保存JPは異なる |
| jp_collision_candidate | 同じfamily・ファイル・分類で、異なる英語名の概念に同じJP比較キーがある |
| historical_jp_variation | HD→DEで英語が同一、旧世代日本語がHDを支持し、DE日本語だけが変化したレビュー候補。旧訳採用の裁定ではない |

衝突には名称だけでなく、確実に切り出せた操作表示・Help見出しも含む。
Phase 1Aの名称ラベルだけの2群と同数になるとは限らない。
短縮、省略、正当な同訳も候補になり得る。正誤や統一先は自動判定しない。異なるfamily間の照合は行わない。

差分タグはこの実装単位では `layout_difference`、`layout_only`、`wording_difference` に限定する。
語彙差と改行差は併記可能。既存 `scope.layout_key()` は比較専用に再利用する。
タグを除去したキーを技術的同値と見なさず、エスケープされたバックスラッシュと表示改行を区別する。
全角半角、カタカナ・漢字の等価判定や訳語の正規形は導入しない。

世代比較は同IDの資料比較で、同一概念の継続性の確定ではない。
HD/DE英語変更、Legacy英語未収集、missing / dataset_unavailable / ambiguousを明示する。
AoCにAoKを補完せず、DLLの優先順を決めない。原値の不一致は復元指示ではない。

## 出力とレビュー手順

| ファイル | 用途 |
|---|---|
| review.tsv | **概念単位の主レビュー表**。所属表示、finding、baseline対応、既存裁定参照、人間記入欄 |
| summary.md | 件数と語彙差等のある概念の表示一覧 |
| concepts.json / relations.json | 概念と根拠の構造 |
| findings.json / findings.tsv | finding単位の対象出現と差分 |
| occurrences.tsv | 日英term、出現・span・hash。Help/操作の本文は含まない |
| unresolved.json / unresolved.tsv | 対応を証明できなかった出現・群の保留表 |
| baseline-groups.tsv | 従来72群/152 IDを漏れなく追跡する照合表 |
| history.tsv | 名称の世代比較。旧ID再利用の長文は最大160文字＋hashに限定 |
| coverage.tsv | 既存名称候補とseedについてincluded/unresolved、未接続の完全一致・単複形・直接操作候補についてnot_classified。DE全体の文種分類ではない |
| diagnostics.json | 既存重複監査と解析診断。原文の大量抜粋は含めない |
| manifest.json | 基準commit、実装hash、ルールhash、source/既存reviews hash、成果物hash、件数・限界 |

1. baseline-groups.tsvで72群の概念対応を確認する。
2. review.tsvのfindingあり概念を優先する。語彙差とlayout差を区別する。
3. 複数概念の衝突はfinding IDで相互参照し、各概念のHelp基点と用途を確認する。
4. 証拠はoccurrences/history/relationsで確認する。unresolved原文は既存 `show ID` で局所的に読む。
5. reviewer、reviewed_on、reviewer_decision、reviewer_japanese、reviewer_scope、reviewer_notesを記入する。
   統一なら対象出現と採用訳、別概念なら分割根拠を明記する。

全件pending、人間欄はnullで生成する。記入用コピーは元runとは別に保管し、機械証拠の列は編集しない。
既存reviewsはID・署名・採用値hashに加え、decision、proposed_jp、authority、notes要約・参照を
`reference_only=true`で表示する。新監査による再承認・自動裁定ではない。
名称裁定と全文裁定の権限を変更せず、全文裁定を他の名称へ伝播しない。
reportsはGit対象外。この成果物をpatch/Mod入力として読み込む経路は設けていない。

## ローカル実測（Phase 2A-1 revision 2）

構造的概念866、所属出現3,377。既存2,032名称ID中1,659を所属として確認、373を保留。
レビュー済みseed 1件を追加し、inventory外の完全一致・単複形・直接操作候補33件を`not_classified`に保持した。
72群/152 IDのうち68群が一つの概念に対応し、4群は一部の対応を保留した。
4群はChroniclesのImperial Age、Academy、Incendiary Raft、Indian Tribesman。
確認できる出現は概念に保持し、未証明の別ラベルを強制追加しない。

findingsは651件（概念内語彙差171、名称/Help不一致158、layoutのみ231、衝突候補8、
安全条件を満たす世代間日本語差83）。unresolvedは731件（名称373、Help基点169、操作151、
Help見出し1、baseline群4、inventory外名称候補33）。
これらは初回入力の観測値で、プログラムの固定上限・期待母集団ではない。

Mounted Samuraiは5039/14039/6039/26039を同概念でレビューできる。
Composite Bowmanは5033/14033/6033/26033の名称・語彙差・改行差を保持する。
ChroniclesのTriremeとGalleyは別々のHelp基点を持つ概念のまま、訳語衝突で相互参照する。
Fire Shipの19279は候補概念1件、Fast Fire Shipの17242はunit/technologyの候補概念2件を
`candidate_concept_ids`に持つ。12441 Fire ShipsはFire Shipへの単複形候補として
`not_classified`に残る。Relic 5350はレビュー済み構造seedから`game_object`概念となり、
artifact、台詞、一般名詞、Relic Cartは所属させない。

テストはsynthetic fixtureを主体とし、sourceがある場合だけ72群と代表例のread-onlyテストを追加する。
ゲームデータ更新で基準が変わった場合は期待値だけを機械的に変更せずbaseline差を調査する。
