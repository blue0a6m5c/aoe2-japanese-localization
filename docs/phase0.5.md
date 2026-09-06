# Phase 0.5: AoK / AoC Legacy Localization Extraction

AoK/AoC日本語版のDLLを一次資料として抽出し、Phase 0の検索・ID比較・統計へ統合しました。
翻訳文字列の修正、評価、復元、DEへの自動適用は実装していません。

## 原資料と事前調査

2026-09-06、workspaceから3ファイルを実際に読み取り、ユーザー提示のSHA-256と一致することを確認しました。
取得元情報はユーザー申告によります。CD-ROM自体の構成やゲームのDLLロード順を確認したものではありません。

| 世代 | source相対パス | 取得元 | バイト数 |
|---|---|---|---:|
| AoK | legacy/aok/jp/LANGUAGE.DLL | 日本語版Gold Edition Disc 1 | 499,712 |
| AoC | legacy/aoc/jp/LANGUA_1.DLL | 日本語版Gold Edition Disc 2 | 339,968 |
| AoC | legacy/aoc/jp/LANGUA_2.DLL | 日本語版Gold Edition Disc 2 | 45,056 |

```text
LANGUAGE.DLL
5732E637AF649F8A349C876EBDD9916E05A0A398493BC17C444933B286CDD851
LANGUA_1.DLL
027DE69D54BB9079E054715FD8D21637B52C893BCC5F379E2F72AE089C8510A4
LANGUA_2.DLL
63975B897A5ABDF86D0217A37EBC0FD1A71090DF18A5A0FA6EA2809122145823
```

3 DLLともMZ/PE署名を持つPE32、machine=0x014c（x86）、DLL属性ありでした。
リソース種別は6（RT_STRING）と16（RT_VERSION）、文字列のLANGIDはすべて0x0411（日本語）です。
今回はRT_STRINGのみ抽出します。RT_VERSIONの内容は解析していません。

## リソース構造と空スロット

PEのリソースツリーは、今回のデータでは `種別6 → ブロック番号 → LANGID → データ` です。
各STRINGTABLEブロックは16スロットを持ち、各スロットは16ビットの文字数とUTF-16LEデータから成ります。
文字数はUTF-16コード単位数で、終端NULを探して切り出す形式ではありません。
String IDは `(block_id - 1) * 16 + slot`（slotは0〜15）で求めます。
根拠はMicrosoftの[PE仕様](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format)と
[string resourceの形式説明](https://devblogs.microsoft.com/oldnewthing/20040130-00/?p=40813)です。

長さ0のスロットは「明示的な空文字列」と「ブロック内の未使用ID」を区別できません。
そのため、通常のString数・ID集合・重複判定には非空エントリだけを使用します。
空スロットも値 `""` と出現情報を別に保持し、showでは `empty_resource_slot` として確認できます。
空スロットを削除命令や他DLLの値を上書きする命令として解釈しません。
HD/DEの明示的な `ID ""` は従来どおり存在するStringです。この差は記録形式に由来します。

| DLL | ブロック数 | 全スロット | 非空String／一意ID数 | 空スロット | 非空最小ID | 非空最大ID | DLL内重複ID |
|---|---:|---:|---:|---:|---:|---:|---:|
| LANGUAGE.DLL | 628 | 10,048 | 4,952 | 5,096 | 98 | 50,004 | 0 |
| LANGUA_1.DLL | 275 | 4,400 | 1,635 | 2,765 | 1,006 | 62,617 | 0 |
| LANGUA_2.DLL | 22 | 352 | 29 | 323 | 8,022 | 30,177 | 0 |

非空エントリの合計は6,616件です。抽出エラーは0件でした。

## AoC 2 DLLの実測上の関係

| 指標 | ID数 |
|---|---:|
| 非空IDの和集合（aoc_jp） | 1,650 |
| LANGUA_1だけに非空値があるID | 1,621 |
| LANGUA_2だけに非空値があるID | 15 |
| 両方に非空値があるID | 14 |
| 共通ID・同一値 | 0 |
| 共通ID・異なる値 | 14 |
| 空スロットも含めた共通スロットID | 272 |
| 両方が長さ0 | 167 |
| LANGUA_1が非空、LANGUA_2が長さ0 | 82 |
| LANGUA_1が長さ0、LANGUA_2が非空 | 9 |

異なる値を持つ14 IDは以下です。

```text
8415 8438 20152 20154 20155 20156 20163
20164 20167 26094 26289 28415 28438 30133
```

`aoc_jp` は両DLLの資料集合です。非空エントリ数は1,664、比較可能な一意IDは1,636です。
14件の重複は `ambiguous` のまま、両方の値と出現情報を保持します。
同じ値の重複が将来見つかった場合も自動解決しません。

ファイルサイズや差分の形から2 DLLの役割・優先順位は断定できません。
AoKの値をAoCへ補完する処理もありません。例えばAoC欄でID 5131が欠落していても、
AoCの実行時にその概念や表示が存在しなかったことを意味しません。
`LANGUA_2` をパッチ、最終版、優先DLLなどと見なすルールは未導入です。

## パーサーとデータモデル

`tools/localization/legacy.py` はPython標準ライブラリの `struct` とバイト列読み取りで解析します。
DLLをロード・実行せず、外部依存やWindows APIへの実行時依存もありません。
Python 3.10以上で利用でき、テスト用PEもPythonで生成します。実際の動作検証環境はWindowsです。

- PE32とPE32+に対応。DOS/PE署名、DLL属性、Optional Header、Resource Directoryを検査します。
- RVAをSection Tableでファイルオフセットに変換し、範囲外や複数候補を拒否します。
- リソースの相対ポインター、深さ、循環、16スロットの長さ、UTF-16LEを検査します。
- 不明な形式、末尾の余分なバイト、破損は推測で補正しません。
- 解析不能なDLLはファイル単位で原子的に除外し、`pe_error` を診断に残します。
- 複数言語や重複リソースを黙って選別しません。LANGIDと全出現を保持し、同じIDの非空値が複数なら曖昧とします。
- 実際の日本語LANGIDは0x0411。英語0x0409は `en`、その他は `langid:0x....` と表示します。
  データセット名が `jp` であってもリソース内の言語を書き換えません。

EntryはPhase 0の `string_id`、`value`、`path` を共用し、以下を追加しています。

| フィールド | Legacyでの値 |
|---|---|
| line | null（架空の行番号を付けない） |
| generation | aok / aoc |
| language | リソースのLANGID由来 |
| value_format | utf16_resource |
| resource | type_id、block_id、slot、language_id、codepage、data_entry_offset、block_offset、byte_offset、length_utf16、zero_length |

pathはデータセット相対のDLL名です。byte_offsetは長さWORDのファイル先頭からの位置です。
ParsedFileには format、metadata、empty_slotsを追加し、SHA-256とバイト数も保持します。
Datasetのentriesは非空リソース、empty_slotsは長さ0の出現をID別に保持します。
重複・欠落・存在の判定にゲームのロード順は使用しません。

HD/DEの値はエスケープ未展開の `key_value_raw`、DLLの値はデコード済みUnicodeです。
LegacyとHD/DEの値を比較する場合、結果は**保存表現のliteral比較**です。
例えばDLLの実改行とHDの `\n` は異なります。正規化や描画上の同一性判定は今回行いません。
HD/DEの既存変更カテゴリーと基本4ロールの比較統計は変更していません。

## CLI

既定ではPhase 0の4データセットに加え、存在する `source/legacy/aok/jp/` と
`source/legacy/aoc/jp/` の全 `.dll`（大文字小文字不問）を再帰探索します。
この2ディレクトリがなければ従来の4種類だけで動きます。
存在するのにDLLが一つもない場合はエラーです。ファイルの黙示的な優先順位はありません。

```powershell
# Legacyの各DLL・合計統計、AoCファイル間比較、世代間ID共通部分
python -m tools.localization legacy-stats

# 従来の統計にLegacyとDLLインベントリも追加
python -m tools.localization stats

# 全データセットを横断検索。値を付ける場合は --values
python -m tools.localization search "鉄工所"
python -m tools.localization search "鉄工所" --values --limit 5
python -m tools.localization search "鉄工所" --dataset aok_jp --dataset aoc_jp --values --limit 5

# AoK JP / AoC JP / HD JP / DE JP / HD EN / DE ENの全出現を表示
python -m tools.localization show 5131
python -m tools.localization show 8415
python -m tools.localization show 8022

# Legacyにも対応した欠落・重複確認
python -m tools.localization compare --missing aoc_jp --limit 10
python -m tools.localization compare --category duplicate --limit 10 --values
python -m tools.localization issues

# 限定レポート（値は既定では含まない。sourceへは書き込まない）
python -m tools.localization report --query "鉄工所" --dataset aok_jp --limit 5 --output reports/legacy-smith-index.json
```

`show 5131` の実測値を抜粋すると以下です（JSON全体にはパス・出現位置も含まれます）。

| データセット | 値 |
|---|---|
| aok_jp | 鉄工所 |
| aoc_jp | missing（今回の2 DLLに非空値なし） |
| hd_jp | 鉄工所 |
| de_jp | 鍛冶場 |
| hd_en | Blacksmith |
| de_en | Blacksmith |

「鉄工所」の部分一致検索では、AoK 72 ID、AoC 74 ID、HD JP 141 ID、DE JP 0 IDでした。
これは検索結果であって訳語の評価ではありません。`show 8415` はAoC欄で2つの異なる値を
`ambiguous` として表示します。`show 8022` は6種類すべてに非空値があります。

JSONはschema_version=2です。値形式は各出現のvalue_formatで区別できます。
`legacy-stats` の `within_generation_file_pairs` に同一値／異なる値と空スロットの関係、
`generation_pairs` に世代ペアの共通・片側のみ・literal一致／不一致・未解決数を表示します。
`id_intersections` はLegacy和集合とHD/DEとのID共通部分です。

Phase 0の終了コード規則を継続し、重複ありの解析完了は1、設定・入出力エラー等は2です。
現在の全データでは重複は59データセット・ID組（既存45＋AoC 14）です。
PE/encodingエラー時は `incomplete: true`。stats、legacy-stats、issuesで診断でき、比較系は停止します。
既存の `all_four`、`jp_only_changed`、`changes` はHD/DE基本4ロールの意味を維持します。
`duplicate` と `ambiguous` はLegacyを含む全データセットに適用します。

明示configを指定した場合は自動追加せず、指定したデータセットのみを使用します。
基本4ロールは引き続き必須です。既存の文字列形式に加え、次のオブジェクト形式に対応します。

```json
{
  "hd_en": "hd/en",
  "hd_jp": "hd/jp",
  "de_en": "de/en/key-value",
  "de_jp": "de/jp/key-value",
  "aok_jp": {"path": "legacy/aok/jp", "format": "pe_rt_string", "generation": "aok"},
  "aoc_jp": {"path": "legacy/aoc/jp", "format": "pe_rt_string", "generation": "aoc"}
}
```

予約名aok_jp/aoc_jpでは、文字列のディレクトリ指定だけでもDLL形式と解釈します。
別名のデータセットではformatを明示してください。HD/DEへの混入を避けるため拡張子から形式を推測しません。

## 世代間のID共通部分

| 比較 | 共通ID | 左だけ | 右だけ |
|---|---:|---:|---:|
| AoK JP / AoC JP（2 DLL集合） | 368 | 4,584 | 1,282 |
| AoK JP / HD JP | 4,730 | 222 | 7,098 |
| AoK JP / DE JP | 4,437 | 515 | 33,986 |
| AoC JP / HD JP | 1,461 | 189 | 10,367 |
| AoC JP / DE JP | 1,421 | 229 | 37,002 |
| HD JP / DE JP | 8,603 | 3,225 | 29,820 |

AoK/AoC資料の和集合は6,234 ID。うちHD JPとの共通は5,878、DE JPとの共通は5,553です。
日本語4世代すべての共通IDは300です。
これらは保存資料のID集合の比較であり、同じ意味・用語の継承やAoCの実行時全体像の保証ではありません。

## 検証

`python -m unittest discover -v` で既存20件＋Legacy 13件、計33件が成功しました。
Microsoftの文字列やDLLをfixtureへコピーしていません。tests/pe_fixture.pyで小さなPEを生成します。
正常値、日本語、空スロット、複数ID、欠落、DLL間同値／異値重複、複数言語、
PE32+、境界外・循環・不正UTF-16・不正長、CLI統合・終了コード・元データ不変性を検証します。

実データについては、静的パーサーとは独立にWindows APIでも全件照合しました。
`LoadLibraryExW` に `LOAD_LIBRARY_AS_DATAFILE | LOAD_LIBRARY_AS_IMAGE_RESOURCE`（0x22）を指定し、
`LoadStringW` の長さ付き値と比較後、必ず `FreeLibrary` で解放しました。
全6,616非空エントリおよび全8,184空スロットが一致しました。
この照合のみWindows固有です。通常のCLIと自動テストはWindows APIを呼びません。
フラグとAPI仕様はMicrosoftの[LoadLibraryExW](https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-loadlibraryexw)、
[LoadStringW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-loadstringw)を参照しました。

作業前後にsource内の全30ファイル（公式29ファイル＋README）のSHA-256を比較し、すべて一致しました。
公式29ファイルはすべてignoredで、tracked/stagedは0件です。
統計やハッシュ検証結果はreports/に置き、Git管理しません。
source/README.mdも含め、原資料は変更・整形・移動・Git追加をしていません。

## 既知の制約とPhase 1前の検討事項

- AoCの2 DLLとAoK DLLの実行時ロード関係・優先順位は未確認。実行時有効値の合成は行いません。
- 空スロットは意図的空文字列と未定義を区別できません。
- PEの一般的な全形式を扱うライブラリではありません。RT_STRINGが標準の3階層・16スロット構造でない場合、
  named block、リソース範囲を越えるペイロードなどは診断して停止します。
- PE32+はsyntheticテスト済みで、今回の原資料はすべてPE32です。
- HD/DEのエスケープとDLL Unicodeの差、改行・書式・プレースホルダー比較を別工程として検討してください。
- IDの再利用、文脈、ゲーム内フォールバック、パッチの出自を確認してから翻訳判断へ進んでください。
- Legacyは歴史的な一次資料です。現在の英語原文、追加文明やユニット、ゲーム内一貫性、
  Chronicles等の異なる命名体系と照らして人間がレビューし、昔の表記を無条件で正解にしないでください。
