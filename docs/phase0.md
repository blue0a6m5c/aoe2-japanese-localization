# Phase 0: ローカライズ解析基盤

この文書はPhase 0時点の形式・統計を記録しています。
AoK/AoC DLLの自動検出、schema_version=2、Legacy統計などの追加仕様は
[Phase 0.5](phase0.5.md)を参照してください。HD/DEの比較定義は維持しています。

Python 3.10 以上、標準ライブラリのみで動作します。リポジトリのルートで実行してください。
翻訳の修正・評価・Mod生成は行いません。

## 実データの調査（2026-09-06）

README.md、AGENTS.md、source/README.md と、対象ディレクトリ内の全26ファイルを読み取りました。
以下はローカルに配置されていたデータについての観測であり、ゲームのビルド番号やロード順は未確認です。
source/README.md の配置例と矛盾はなく、同ファイルを含め source/ 以下は変更していません。

| データセット | ディレクトリ | ファイル数 |
|---|---|---:|
| hd_en | source/hd/en/ | 1 |
| hd_jp | source/hd/jp/ | 1 |
| de_en | source/de/en/key-value/ | 12 |
| de_jp | source/de/jp/key-value/ | 12 |

HDは `key-value-strings-utf8.txt` のみです。DEは両言語とも以下の構成です。

- `key-value-strings-utf8.txt`
- `key-value-modded-strings-utf8.txt`（コメントのみ、エントリ0件）
- `key-value-paphos-strings-utf8.txt`
- `paphos-campaign-key-value-strings-utf8.txt`
- `paris-campaign-key-value-strings-utf8.txt`
- `PDLC2-campaign-key-value-strings-utf8.txt`
- `PDLC3-campaign-key-value-strings-utf8.txt`
- `PDLC4-campaign-key-value-strings-utf8.txt`
- `PDLC6-campaign-key-value-strings-utf8.txt`
- `peru-campaign-key-value-strings-utf8.txt`
- `providence-campaign-key-value-strings-utf8.txt`
- `tournament-key-value-strings-utf8.txt`

共通する実形式は `ID "value"` です。全ファイルはUTF-8、BOMなし、物理改行はCRLFでした。
空行、`//` コメント行、閉じ引用符の後ろの `//` コメントが存在します。
HDにもDEにも数字以外の記号IDがあります。DEには `426071_perth` のような接尾辞付きIDもあります。
したがって、String IDを整数や既知の数値範囲に限定してはいけません。
DEでは本体以外に15,838エントリ／言語があり、本体だけの解析では欠落します。

値には日本語、空文字列、書式タグ、プレースホルダー、スクリプト風の文字列があります。
値内で観測したバックスラッシュ表記は `\n`、`\t`、`\"`、`\\` です。
コメント内のバックスラッシュ表記は値のエスケープとして数えません。
今回の全データに対し、未解釈エスケープ・malformed・UTF-8エラーはいずれも0件でした。

## パーサーの仕様

`tools/localization/parser.py` はファイルの解析のみを担当し、比較や出力生成から分離しています。

- UTF-8をstrictで読み、先頭BOMがあれば受け付けます。デコード不能ならファイル全体を除外し、バイト位置を報告します。
- 物理行はCRLF/LF/CRで分割します。値内のUnicode行区切り文字は分割しません。
- キーは観測されたASCII英数字と `_` の1文字以上。大文字小文字・先頭ゼロを維持します。
- キーと開始引用符の間には半角スペースまたはタブが必要です。行頭のスペースとタブも許容します。
- バックスラッシュとその次の文字を一組として走査し、`\"` を終端引用符と誤認しません。
- **値は外側の引用符だけを除いた原表記を保持します。** `\n` を実改行に展開するなどの変換はしません。
  エスケープのゲーム内表示仕様までは推測しません。JSON出力ではJSON自体のエスケープが追加されます。
- 未知のエスケープは値を保持しつつ `unknown_escape` として報告し、そのIDを値比較から除外します。
- 閉じ引用符の後ろはスペース、タブ、`//` コメントのみ許容します。
- 未閉鎖引用符、余分な後続文字、不正キーなどは `malformed` として行番号付きで報告します。
  物理複数行の値を推測して連結することはありません。次の行から解析を継続します。
- 全出現を保持し、同一値でも重複は重複です。first/last-winsは採用しません。
  不正行からキーを読み取れた場合、そのキーの別の正常行も自動的には解決しません。
- Python APIのIssueには元の不正行を保持しますが、CLIの診断には元の行全文を含めません。

`analysis.py` は選択した各ディレクトリの `.txt`（大文字拡張子も可）を再帰的に探索します。
ファイル名やID範囲による除外はありません。それ以外の拡張子は対象外です。
存在しないディレクトリや `.txt` が一つもないデータセットはエラーとします。
空・コメントのみのファイルもインベントリに記録します。
各エントリにはデータセット相対パスと1始まりの行番号を持たせます。

ファイルは相対パスの順、IDは数値キーを数値順（同値なら原キー順）、その後に記号キーを辞書順で出力します。
時刻や絶対パスをレポートへ混入させず、入力ごとのSHA-256で再現性を確認できます。

## 比較の定義

キーの存在は「正常に構文解析できたエントリが1件以上あること」です。空文字列も存在として数えます。
malformed行から得たキーは問題一覧に残りますが、正常なString数には加えません。
問題のある入力に対する存在・欠落の分類は、この構文上の定義によるものであり、ゲーム内の有無の断定ではありません。
エンコーディングエラーがある場合、stats/issuesには `incomplete: true` を表示し、比較系コマンドを停止します。

| カテゴリー | 条件 |
|---|---|
| all_four | HD EN/JP、DE EN/JPのすべてに存在（重複の有無とは独立） |
| en_changed | HD ENとDE ENがそれぞれ一意で問題がなく、値が不一致 |
| jp_changed | HD JPとDE JPがそれぞれ一意で問題がなく、値が不一致 |
| jp_only_changed | 4種類が一意で問題がなく、英語は一致、日本語は不一致 |
| de_added | DEのいずれかの言語に存在し、HDの両言語には存在しない |
| hd_only | HDのいずれかの言語に存在し、DEの両言語には存在しない |
| missing | 4種類のいずれかに欠落。新規・HDのみも含む |
| duplicate | いずれかのデータセットで同じキーが複数回出現 |
| parse_error | キーを特定できたmalformed行が存在 |
| ambiguous | 重複、malformed、未知エスケープによって値を一意に比較できない |

カテゴリーは重なります。件数を合計して全体件数と解釈しないでください。
HD/DE共通IDは `(HD EN ∪ HD JP) ∩ (DE EN ∪ DE JP)`、全4種類共通とは別です。
言語別の変更数は、その言語の両版が比較可能な場合に数えます。他方の言語に問題があっても判定できます。
比較は空白、大小文字、Unicode、タグ、エスケープを正規化しない完全一致です。
英語が異なっていても意味が同じ可能性はあり、逆に同じIDでも文脈が変化する可能性があります。
`jp_only_changed` は人間によるLegacy terminology調査の候補であって、復元すべき翻訳の一覧ではありません。

## CLI

すべてUTF-8 JSONで出力し、4種類を同一IDの `datasets` オブジェクトに並べます。
終了コードは **0: 問題なし、1: 解析完了だが重複または入力診断あり、2: 入出力・設定などのエラー** です。
実データには重複があるため、現在は正常に解析できても1を返します。stderrにも要約を出します。

```powershell
# ヘルプ、統計、1つのIDの全出現と値
python -m tools.localization --help
python -m tools.localization stats
python -m tools.localization show 10319

# 日英検索：literal substring。指定データセットはOR、未指定なら全データセット
python -m tools.localization search "町の人" --dataset hd_jp --dataset de_jp --values
python -m tools.localization search "archer" --dataset de_en --ignore-case --values

# 両言語いずれかのHD→DE変更。各行に4種類の比較を表示
python -m tools.localization changes --limit 20 --values
python -m tools.localization changes --query "archer" --dataset de_en --values

# 英語は同一、日本語だけ変化した候補
python -m tools.localization compare --category jp_only_changed --limit 20 --values

# カテゴリーの繰り返しはAND。欠落言語、数値／記号ID、ページ指定
python -m tools.localization compare --category all_four --category en_changed
python -m tools.localization compare --missing hd_jp --id-type symbolic
python -m tools.localization compare --category jp_only_changed --offset 50 --limit 50

# 重複の全出現位置と診断。文字列値の確認には show ID を使う
python -m tools.localization issues
python -m tools.localization compare --category duplicate --values

# 条件、件数、出現位置、入力ハッシュを付けた限定レビュー用JSON
python -m tools.localization report --category jp_only_changed --limit 20 --values --output reports/legacy-candidates.json
```

showは指定IDの全値を表示します。それ以外では既定で値を含めず50行まで、`--values` 指定時は最大200行です。
`total` は絞り込み後の全件数、`offset` は0始まりです。issuesでは診断または重複IDを1項目と数えます。
キーを特定できない診断はIDフィルターで隠しません。issuesは常に値を含めず、診断と出現位置を表示します。
検索は重複値も対象にしますが、それによって重複が解決されるわけではありません。

reportだけがファイルを書きます。出力先は作業ディレクトリの `reports/` 内に限定し、
source内への出力、既存ファイルの上書きを拒否します。シンボリックリンクも解決して検査します。
`reports/` はGit管理対象外です。公式全文のJSON/CSVへの自動ダンプは行いません。
シェルのリダイレクト先はツールでは制御できないため、`> source/...` 等は絶対に使用しないでください。

## 拡張と責務

別の配置には `--source-root PATH` を指定します。`--config FILE.json` はデータセット名とディレクトリの対応です。
相対パスはsource-root基準、絶対パスも使用できます。4つの基本ロールは必須です。

```json
{
  "hd_en": "hd/en",
  "hd_jp": "hd/jp",
  "de_en": "de/en/key-value",
  "de_jp": "de/jp/key-value",
  "aoc_jp": "aoc/jp"
}
```

追加データセットはインベントリ・統計・show・検索に参加します。
HD/DEの比較統計は基本4ロールのままです。compareの存在・変更カテゴリーも基本4ロールを指し、
追加データセットのみにあるIDは4ロールすべて欠落となります。
重複・診断の表示には追加データセットも含まれます。
AoK/AoCが異なるファイル形式なら、形式を調査して専用パーサーを追加してください。
このPhaseには翻訳データやModビルドとの結合はありません。

## 検証と今回の統計

```powershell
python -m unittest discover -v
python -m tools.localization stats
```

tests/fixtures/ とテスト内の文字列はすべて専用のsyntheticデータです。
通常値、日本語、空値、引用符・バックスラッシュ、未知エスケープ、重複、複数ファイル、
不正行、UTF-8エラー、片版のみのID、欠落、厳密比較、CLIフィルター、終了コード、
決定的な出力、レポートの出力範囲・上書き拒否を検証します。

| データセット | 正常エントリ数（重複込み） | 一意ID数 | 重複ID数 |
|---|---:|---:|---:|
| HD EN | 11,871 | 11,868 | 3 |
| HD JP | 11,828 | 11,828 | 0 |
| DE EN | 38,444 | 38,423 | 21 |
| DE JP | 38,444 | 38,423 | 21 |

| 比較 | ID数 |
|---|---:|
| HD/DE共通（言語の和集合間） | 8,642 |
| 全4種類共通 | 8,603 |
| DE新規 | 29,781 |
| HDのみ | 3,226 |
| 英語変更 | 3,726 |
| 日本語変更 | 5,877 |
| 英語同一・日本語のみ変更 | 2,249 |
| いずれかに欠落 | 33,046 |
| 全体の一意ID | 41,649 |
| 重複（データセット・IDの組数） | 45 |
| 重複（全体の異なるID数） | 24 |
| malformed / encoding error / unknown escape | 0 / 0 / 0 |

DEの重複は言語ごとに同値6件、異なる値15件。このうち4件はファイル間重複です。
HD ENの重複3件はすべて異なる値です。ゲームの上書き順は未確認なので、同値も含め自動解決していません。
DEには数値ID34,806件・記号ID3,617件／言語があり、HDにも記号IDがあります。

## 次のPhaseで検討すること

- 重複IDのゲーム内ロード順とコンテンツ別スコープの確認。
- 入力ビルド番号・入手元・コピー日時などのローカル来歴の記録。
- 抽出候補を限定したレビュー形式と、AoK/AoCの原資料による用語の確認。
- プレースホルダー・タグの比較検証、Chronicles等の文脈の識別。

sourceは読み取り専用です。整形、移動、修正、Git追加をしないでください。
レポートを共有する前には含まれる公式文字列の量を確認し、全文や不要な大量抜粋をコミットしないでください。
