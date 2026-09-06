# Phase 1A: Core Gameplay Name Inventory / Audit

名称レビューの候補一覧を作成するPhaseです。採用訳の決定、翻訳の変更、Legacyへの復元、Modへの適用は行いません。
通常名を中心に、コンパクト表示や研究ボタンでの別表示を同じString ID軸で追跡できます。

## 対象範囲と重要な限界

DE EN/JPを起点として、HD EN/JP、AoC JP、AoK JPを並べます。
対象は作成・建設・研究・アップグレード・時代進化の説明から名称との対応を確認できた候補です。
unit / building / technology / age / unknownを主分類とし、固有ユニット、固有技術、
ユニットアップグレード、建物アップグレード、明示的Heroを副分類で区別します。

**ゲームの実データ（ユニット・建物・技術テーブル）を解析した完全なスカーミッシュ名簿ではありません。**
名称が現行の通常対戦で使用されること、未使用ではないこと、文明別の所属はこの資料だけでは保証しません。
すべての行に `gameplay_availability: review-needed` を記録しています。
英雄・シナリオ用で説明にその根拠がないもの、説明から参照されない名称、資源・装飾物の網羅抽出は未対応です。
キャンペーン本文や長文説明は分類根拠として参照する場合がありますが、翻訳レビュー一覧へ本文を出力しません。

## 分類方法

`tools/localization/gameplay.py` が既存Datasetを読み、以下の順に根拠を集めます。

1. 英語説明の先頭にある `Create/Train/Build/Research/Upgrade to/Advance to <b>名称<b>` を解析します。
2. **同じファイル内**に同じ英語名称を持つ短いラベルがあるか照合します。
   対応付けだけはタグを除き、`\n` と連続空白を表示上の空白へ寄せます。原文字列は変更しません。
3. 実測したID差21,000（通常名）、12,000/11,000（短縮名等）が名称一致でも裏付けられる場合、
   `verified_offset_and_label` として記録します。ID差だけでカテゴリーを断定しません。
4. ID差21,000の短いラベルが名称と一致しない場合は、未確認の対応候補として保持します。
   同名照合だけの別表示も含め、確度が低い場合はclassification_reviewです。
5. 複数のカテゴリー根拠が競合したり説明から決められない場合はunknownです。
   例えばユニットそのものの名称とアップグレード技術名は、同じ英語名でも役割が異なります。

名称候補は表示上80文字・12語以内で、説明文らしい句読点、制御記号、作成コマンド等を除外します。
この長さ制限による取りこぼしもあり得ます。数字IDの固定範囲を丸ごと「ユニット名」と扱う処理はありません。

Create/Trainはunit、Researchはtechnology、Upgradeはtechnologyのupgrade副分類、Advanceはageです。
Buildは移動ユニットにも使われます。説明の最初の文にあるunit、siege weapon、ship等と、
tower、wall、gate、food source、used to等の建物を示す表現を照合し、判定不能ならunknownです。
これらは英文のパターン検査であり、自由文を完全に理解する分類器ではありません。
固有技術は同じファイルの文明説明にある `Unique Techs` リストとの名称一致を追加根拠にします。

`gameplay_rules.json` はプロジェクト管理下の分類メタデータです。採用訳は含みません。
現在は観測したID差、少数の単複表記の対応、検証済みファイルの文脈、DLCの説明ID、系列IDを記録しています。
Blackwood Archers等の単複表記は照合用の例外で、英語原文を修正しません。
17490と28490の対応は隣接した短縮技術名の配置を調べたレビュー対象であり、正しい対応と断定していません。
ルールを拡張するときも、実際のラベル・説明・出現位置を確認してください。

## Content familyとChronicles

| family | 意味と根拠 |
|---|---|
| core | 本体ファイルで名称と説明が対応する標準側の候補。source-profileという推定区分で、発売時期や通常対戦への登場を保証しない |
| dlc | 明示的に確認したDLC説明IDまたは文明説明との対応。現時点ではThe Last Chieftainsの部分的なタグ付け |
| chronicles | paphos系・providenceキャンペーンの実データ内容を確認したファイル文脈 |
| scenario/hero | campaignファイルの候補、または説明にHeroが明示された候補 |
| review-needed | ファイルや名前だけでは文脈を決められない候補 |

coreは「1999年から存在する」「DLCではない」という意味ではありません。他DLCの名称もここに含まれ得ます。
familyの根拠の確度は `content_family_confidence` に分けて記録しています。
名称のカテゴリー確度 `confidence` とゲーム内使用可否は別です。

The Last Chieftainsの文明・固有ユニットは[公式紹介](https://www.ageofempires.com/games/aoeiide/the-last-chieftains/)とローカル説明を照合しました。
Champi・Settlementと関連技術は同じ追加部分の作成説明と、文明説明120206〜120208で参照されていることを確認しています。
Chroniclesの独立した文脈は[公式FAQ](https://support.ageofempires.com/hc/en-us/articles/31839163606932-Chronicles-Expansions-FAQ)も参照しました。
ファイルの開発コード名から商品名や発売順を一般化して推測しません。

同じ英語名でも異なるファイルをまたいで説明を流用しません。日本語衝突・表示揺れ検出は同一family・同一ファイル・同一主分類内に限定します。
系列も異なるfamily・ファイルをまたいで作りません。Chroniclesに通常ゲームの宗教用語等を適用するルールはありません。

## 歴史比較とID再利用

Legacyが欠けていればmissingです。空リソーススロットは存在する訳として補完しませんが、出現メタデータには残します。
AoCの異値重複は全出現を保持してambiguousとし、Legacy継続の根拠には使用しません。

The Last Chieftains周辺では、旧版の旗・橋・装飾物のIDが新しいユニット名へ再利用されています。
例えば5510のHD ENはFlag E、DE ENはGuecha Warriorです。
このようなケースを「昔の訳が変更されたので戻す候補」と誤認しないことが重要です。

- `de_new_id` はHD両言語・AoK/AoCにそのIDがないことです。新ユニットの数ではありません。
- `de_name_not_in_hd_en` は正規化した現在の英語ラベルが、HD ENの短いラベル集合に見当たらないことです。
  英語名称変更やID再利用も含む候補であり、新規コンテンツの確定判定ではありません。
- `historical_english_changed` は同じIDのHD/DE英語原表記が変化したことです。
- Legacy継続候補は、少なくとも一つの一意なLegacy JPとHD JPが完全一致し、DE JPが異なり、
  **HD/DE ENが完全一致する場合だけ**付けます。英語が変わったIDには付けません。

短縮表示のIDも独立して数えます。ID数をユニットの実体数やDLCの追加ユニット数と解釈しないでください。

## Flagsと優先度

すべて人間が確認するための候補です。「誤訳が確定した」という意味のflagはありません。

| flag | 意味 |
|---|---|
| jp_only_changed | HD/DE EN完全一致、JPのみ変更。基本4種類に曖昧さなし |
| legacy_stable_de_changed | 上述の保守的なLegacy＋HD継続条件を満たすJP変更 |
| de_new_id | 必要な歴史データセットが揃い、そのIDが過去資料にない |
| de_name_not_in_hd_en | 現在の英語名がHD EN短名称集合にない |
| historical_english_changed | 同IDのHD/DE EN原表記が異なる。ID再利用の可能性にも注意 |
| history_incomplete | AoK/AoC等のデータセット自体が利用不可。de_new_idを付けない |
| missing_de_jp | DE JPの正常な値がない |
| input_ambiguity | 比較対象に重複・不正等による未解決値がある |
| short_jp | 空白等を除くJPが1文字以下。城・港等も該当し得る低優先の検査 |
| latin_remaining | JPにASCII英字が3文字以上連続する |
| same_as_english | 表示正規化後のDE ENとJPが同じ |
| jp_collision | 同文脈・同分類で、異なる英語名に同じJPが付いている |
| jp_label_variation | 同文脈・同分類・同英語名で、名称ラベル間のJPが異なる |
| name_help_jp_mismatch | 名称ラベルと対応する作成・研究説明の先頭太字名称が一致しない |
| jp_heading_structure_review | JP説明が標準の先頭太字名称形式でない。別の太字部分を名称と推測しない |
| english_name_help_mismatch | ID配置上の対応候補と英語名が一致しない。英語側・ID対応も要確認 |
| classification_review | カテゴリー不明、競合、または名称照合だけで対応確度が低い |
| content_family_review | familyが不確定 |
| series_review | 明示系列／Elite系列で並べて確認する対象。異常を意味しない |
| series_stem_review | EliteのJPに基礎ユニットのJPがそのまま含まれない。語形成の違いもあるため人間が判断 |

JP表示の照合では空白・`\n`・タグを表示上の差として除きます。過去版のjp_only_changed等は原表記の完全一致です。
プレースホルダー整合性や意味対応を包括的に検証する機能は今回の対象外です。

`review_candidate` は新規性だけ・系列参加だけを除くflagのある行です。
`suspicious_candidate` は短さ、英字残留、衝突、表示揺れ、見出し不一致、系列語幹等の検査に該当する行です。
priorityはこれらのうちshort_jp以外をhigh、過去JP変更をmedium、それ以外をlowとしています。
これらはレビューの並べ替えの材料で、訳の正誤や重大度の確定値ではありません。

## CLI

```powershell
# 全体統計／通常名だけの統計（selected_statisticsに絞り込み後を表示）
python -m tools.localization names --stats
python -m tools.localization names --stats --primary

# 通常名のカテゴリー別表示、疑問候補、歴史的変化
python -m tools.localization names --primary --category building
python -m tools.localization names --primary --family core --review
python -m tools.localization names --primary --suspicious --limit 20
python -m tools.localization names --primary --flag jp_only_changed
python -m tools.localization names --primary --flag legacy_stable_de_changed
python -m tools.localization names --flag de_new_id
python -m tools.localization names --flag de_name_not_in_hd_en

# 名称一覧の根拠と各世代の値／既存の全出現表示
python -m tools.localization names --id 5131
python -m tools.localization names --id 17490
python -m tools.localization show 5131

# 文脈・系列
python -m tools.localization names --pack the_last_chieftains
python -m tools.localization names --family chronicles
python -m tools.localization names --series eagle
python -m tools.localization names --series ram
python -m tools.localization names --series champi

# 名前候補だけの全件TSV。既存ファイルは上書きしない
python -m tools.localization names --all --format tsv --output reports/names-review.tsv
python -m tools.localization names --primary --family core --review --all --format tsv --output reports/core-review.tsv
python -m tools.localization names --stats --output reports/names-statistics.json
```

各フィルターはANDです。既定50行、offsetは0始まり。標準出力は最大200行、`--all` はreports/内の出力ファイルが必要です。
`--primary` はfull_name（名称とID差21,000の両方が一致する行）を選びます。完全な正規名称リストという意味ではありません。
`--stats` は値の行を出さず、全体statisticsと絞り込み後selected_statistics、根拠未対応の見出し一覧、入力ハッシュを出します。
既存の終了コード0/1/2を維持し、現在の実データでは重複があるため解析完了でも1です。
PE/encodingエラーがあれば一覧生成を停止します。

## レポート形式と生成物

TSVはUTF-8で、ID、カテゴリー、副分類、family、pack、確度、6種類の値、Flags、Priority、
Label Role、Series、Related IDs、Evidence、Provenanceを並べます。
一意な値はJSON文字列としてセル内に表示し、改行・タブ・引用符を損失なく保持します。
値がない場合はmissing、データセット自体がなければdataset_unavailableです。
曖昧な値はstateと全出現を含むJSONオブジェクトなので、片方だけを採用しません。
セルの値を数式として評価させないよう、文字列をJSONで引用しています。
各世代の元ファイル・行／リソース位置はProvenance列、説明のIDと場所はEvidence列です。
JSON出力ではJP見出しの不一致、固有技術の文明説明出典、familyの確度なども詳細表示します。

今回のローカル生成物は以下です。いずれもGit管理対象外です。

| reports/phase1a/ 内 | 内容 |
|---|---|
| inventory.tsv | 全2,032候補ID。短縮名等も含む |
| core-review.tsv | 標準側の通常名レビュー候補219 ID |
| suspicious.tsv | 通常名の疑問候補175 ID。Chronicles/DLCも含む |
| last-chieftains.tsv | The Last Chieftains周辺63 ID |
| statistics.json | 集計、ルールSHA-256、全入力ハッシュ、対象範囲の限界 |
| findings.md | 特に確認しやすい20例、Eagle/Ram、Legacy比較の限定抜粋 |
| source-verification.json | 作業前後で一致したsource全30ファイルのSHA-256 |

公式全文やキャンペーン本文のダンプは作成しません。公開リポジトリに大きな生成物を追加しないでください。

## 実測結果（2026-09-06のローカルsource）

| 主分類 | 通常名full_name | 短縮・別表示等を含む全候補 |
|---|---:|---:|
| unit | 344 | 841 |
| building | 70 | 210 |
| technology | 439 | 881 |
| age | 6 | 45 |
| unknown | 5 | 55 |
| 合計 | 864 | 2,032 |

全候補中、unique_unitは299、unit_upgradeは244、unique_technologyは102、hero/scenario_unitは11 IDです。
副分類は主分類に含まれる数で、合計へ加算しません。
名称ラベルを照合できなかった作成等の説明見出しは33件あります。未抽出名称の総数は不明です。
分類不能55件は**抽出候補の内数**であって、DE全文中の未分類数ではありません。

全候補のレビュー対象は977、疑問候補は420。通常名に限ると326／175 IDです。
HD→DEでEN同一・JP変更は全候補250、通常名117 ID。
保守的なLegacy継続条件を満たすJP変更は全候補104、通常名80 IDです。
DE新設IDは全候補1,141、通常名440 ID。
HD ENに同じ名称を見つけられなかった候補は1,009／421 IDで、新規ユニット数とは区別します。

| flag | 全候補の件数 |
|---|---:|
| classification_review | 370 |
| content_family_review | 169 |
| de_name_not_in_hd_en | 1,009 |
| de_new_id | 1,141 |
| english_name_help_mismatch | 24 |
| historical_english_changed | 123 |
| input_ambiguity | 3 |
| jp_collision | 10 |
| jp_heading_structure_review | 2 |
| jp_label_variation | 152 |
| jp_only_changed | 250 |
| legacy_stable_de_changed | 104 |
| name_help_jp_mismatch | 284 |
| series_review | 176 |
| series_stem_review | 6 |
| short_jp | 40 |
| history_incomplete / missing_de_jp / latin_remaining / same_as_english | 各0 |

flagは重複するため合計しません。

The Last Chieftainsタグは63 ID（通常名31）です。レビュー対象24、疑問候補9、新設ID46、
HD/DE英語変更17で、63すべての現在英語名がHD EN短名称集合には見当たりませんでした。
目立つ確認点はGuechaの綴りに対するゲチュア／グエチャの揺れ、Temple Guardの助詞の差、
Champiのウォリア／戦士の差、17490と28490の対応疑義です。採用訳は決定していません。

## テスト・source保護・Phase 1B前の判断

`python -m unittest discover -v`：既存33件＋新規15件、計48件すべて成功。
新規テストはすべてsynthetic文字列を使い、分類、IDだけで断定しないこと、歴史比較、ID再利用、
AoCの曖昧さ、Chronicles分離、衝突・見出し・系列flag、TSVの復元性、CLIの絞り込み・出力を検証します。
元ゲーム文字列はfixtureへ追加していません。
source/全30ファイルの作業前後SHA-256はすべて一致しました。公式29ファイルはignoredで、tracked・stagedは0件です。
生成した4つのTSVを読み戻し、列構造・行数・出現情報を検証し、実CLIの統計との一致も確認しました。

Phase 1Bでは以下を人間が判断してください。

- ゲーム内データ・実画面で使用IDを確認し、通常対戦、固有、英雄、未使用を確定する。
- 翻訳の不一致と、意図的な表示差・省略・ID再利用を区別する。
- Blacksmith、Monastery等のLegacy継続候補について、現在の英語とゲーム内文脈を確認して採否を決める。
- Eagle等の系列で、段階名・接頭辞・語幹の方針を決める。Ramのように長期維持されている系列も比較対照にする。
- DLCの新語を、既存命名体系と歴史用語に照らして調査する。Chroniclesは別の文脈でレビューする。
- ルールの根拠が弱いunknownやID対応疑義を解決してから、翻訳overrideへ進む。
