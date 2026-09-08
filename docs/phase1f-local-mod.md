# Phase 1F ローカルMod：手動導入と削除

ゲーム内表示検証用。自動インストール・ゲーム起動・公開は行わない。
構造とファイル整合性を検証したパッケージであり、実ゲームでの読込は未検証。
CHECKLIST.mdで結果を記録する。

## 調査した構造と根拠

- ローカルModは利用中のユーザープロファイルの `mods/local/<Mod名>/` に置き、
  その直下の `resources/` にゲームと同じ階層を作る。
  [hszemiによるAoE2DE UGC Guide](https://ugc.aoe2.rocks/mods/) のCreating a local modで確認した。
- 日本語文字列のoverrideは `resources/jp/strings/key-value/key-value-modded-strings-utf8.txt`。
  ゲーム由来の `source/de/jp/key-value/key-value-modded-strings-utf8.txt` のヘッダも
  このファイルに変更文字列を置く方式を説明している。
  [公式フォーラムの実作者の報告](https://forums.ageofempires.com/t/how-can-i-make-my-own-strings/275885)
  でも言語フォルダとファイル名を確認できる。案内はenの例だが、日本語はローカルsourceのjp構成に対応させた。
- 最小metadataとして `info.json` にAuthor / CacheStatus / Description / Titleを記録する。
  上記UGC Guideの例に従う。Workshop ID、サムネイル、datファイルは不要なため作らない。

ゲーム付属ファイルのヘッダは、既存文字列の変更では対象の文字列だけをmoddedファイルへ置き、
元ファイルから削除しないよう案内している。この明示的な指示に従い、**変更済み346 IDだけの差分方式**を採用する。
作者向け資料は同じmoddedファイル名・言語別ディレクトリを案内しており、この構造とも整合する。
以前の全文方式はファイル全体hash一致という当時の要件を満たしたが、未変更IDと既存重複IDまでoverride側へ持ち込んでいた。
今後は差分方式を使用し、旧 `dist/phase1f-local-mod` は過去の成果物として残す。両方式を同時に導入しない。
変更のない11ファイル、対象外ID、英語source、Legacy DLL、ゲームデータは収録しない。
全体hashではなく、対象ID集合と各valueの完全一致を検証する。

## 生成と検証

```powershell
python -m tools.localization mod-package
python -m tools.localization mod-package --verify-only
# 再生成する場合は別のディレクトリを指定
python -m tools.localization mod-package --output-dir dist/phase1f-local-mod-delta-next
```

入力は `dist/phase1e-mod`。Phase 1Eの検証処理を再実行してから、そのディスク上のファイルを読む。
Phase 1E自体のファイルhashを検証した上で、再検証済みplanの346 IDを選ぶ。
各IDはPhase 1Eの全翻訳ファイルを通して一意であることを要求し、同値の重複でも勝手に解決しない。
source occurrence（ファイル・行）とplanのafterも照合して最終valueを取得する。
UTF-8、LF、ID順で346行を生成し、保存値のescape・markup・改行を再エスケープ/正規化しない。
ID集合一致、missing=0、extra=0、duplicate=0、value mismatch=0、346件の完全一致を検証する。
manifest schema 2は差分ファイルSHA-256、Phase 1E manifest・plan・入力ファイルhash、
IDごとの元ファイル/行・operation ID・value hashと検証件数を記録する。
差分ファイル全体とPhase 1E全文ファイルのhash一致は要求しない。
生成後も全ファイルを再読込して期待するバイト列と照合する。source、reviews、Phase 1E、patch planは読み取り専用。

```text
dist/phase1f-local-mod-delta/
├── manifest.json                   検証情報（コピー不要）
├── INSTALL.md                      本書（コピー不要）
├── CHECKLIST.md                    検証票（コピー不要）
└── AoE2-Japanese-Localization-Phase1F/   ← このフォルダだけを手動コピー
    ├── info.json
    └── resources/jp/strings/key-value/
        └── key-value-modded-strings-utf8.txt
```

## Windows版への手動導入

1. ゲームを終了する。検証前のゲームbuild、UI言語、解像度、UIスケール、使用Mod一覧を記録する。
2. エクスプローラーで `%USERPROFILE%\Games\Age of Empires 2 DE\` を開く。
   利用しているプロファイルの数字フォルダを確認する。複数ある場合は推測せず、
   ゲーム内Mod管理画面でフォルダを開ける場合はその場所と照合する。
3. そのプロファイルの `mods\local\` に、上記の
   `AoE2-Japanese-Localization-Phase1F` フォルダだけを手動コピーする。
   同名の既存フォルダがあれば上書きせず、まず検証記録とバックアップを確認する。
4. 最終パスが次のようになっていることを確認する。`dist`や外側のパッケージフォルダを余分に挟まない。

```text
%USERPROFILE%\Games\Age of Empires 2 DE\<使用中プロファイルの数字>\mods\local\
  AoE2-Japanese-Localization-Phase1F\info.json
  AoE2-Japanese-Localization-Phase1F\resources\jp\strings\key-value\key-value-modded-strings-utf8.txt
```

5. ゲームを起動し、UI言語を日本語にする。Mod管理のローカルMod/My Mods一覧で
   `AoE2 Japanese Localization - Phase 1F Test` を探し、有効状態を確認する。
   UI表記はbuildで異なり得る。他の文字列・用語変更Modは検証中は無効にして条件を記録する。
6. ゲームを再起動し、まずメインメニュー、その後スカーミッシュ/技術ツリーを確認する。
   建物名の「射手育成所」「包囲攻撃訓練所」などを読込確認に使う。
7. CHECKLIST.mdに従って画面を記録する。表示が変わらない場合は、有効状態、jp、ファイル名、
   フォルダ階層、プロファイルを確認する。sourceやゲーム本体のファイルを書き換えて回避しない。

ゲームへの配置・有効化は以上をユーザーが手動で行う。このツールはユーザーのGamesディレクトリへアクセスしない。

## 無効化・削除

1. Mod管理画面でこのModだけを無効にし、ゲームを終了する。
2. 上記 `mods\local\AoE2-Japanese-Localization-Phase1F` の正確な位置を確認し、
   エクスプローラーでそのフォルダだけを削除する。他のModやプロファイルを削除しない。
3. ゲームを再起動して、通常のDE日本語表示に戻ることを確認する。
   検証中に無効化した他Modは必要に応じて元に戻す。

差分方式への変更後も今回はローカル検証物として扱い、公開やゲーム起動は自動実行しない。
ゲーム更新後にはsource取得と検証をやり直す。
