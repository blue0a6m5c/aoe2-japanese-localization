# Phase 1E: verified Mod payload generation

> Current pipeline: [context-bound overrides](context-overrides.md). 103 name + 28 direct decisions; 385 operations, conflicts 0, final blocked 0. Counts and default paths below document the original phase baseline. Use matching current scope/plan paths.

確定した `reports/phase1d-layout/patch-plan.json` だけを入力計画として使用し、
公式sourceから独立したローカル成果物を生成する。ゲームへのインストール機能はない。
source、人間裁定、プロジェクトの翻訳データは変更しない。

```powershell
python -m tools.localization mod-build --dry-run
python -m tools.localization mod-build
python -m tools.localization mod-build --verify-only
# 再生成は必ず新しいディレクトリへ
python -m tools.localization mod-build --output-dir dist/phase1e-mod-next
python -m unittest discover -s tests -q
```

既定出力は `dist/phase1e-mod/`。既存ディレクトリを上書きしない。
出力先はworkspaceの `dist/` 内の独立したディレクトリに制限し、symlink経由のリダイレクトは拒否する。
dry-runはメモリ内で全検証を行い、出力ディレクトリ・ファイルを生成しない。
verify-onlyは現在のsource・裁定・scope・planから期待する全バイトを再構成し、
既存成果物、ファイル集合、manifestを照合する。いずれの不一致も非0で終了する。

`--plan`、`--scope-dir`、`--ledger`、`--layout-ledger`を指定可能。
検証済みの既定dataset構造だけを対象とし、`--config`による独自マッピングは受け付けない。

## 検証と適用

Phase 1B・layoutの正本とPhase 1C監査を使って統合planを再計算し、入力planの全フィールドとの完全一致を必須とする。
これにより署名の偽装・古い資料・operationsの欠落/追加・改変されたreplacementを拒否する。
source path、line、ID、ファイルSHA-256、現在値のSHA-256と文字列、matched span、before/after、
full-value/span区分も各operationについて検証する。
同じ物理行への複数operationは、非重複spanでもこのgeneratorでは拒否する。
現行planの385位置はいずれも1 operation。

UTF-8値の引用符内だけを変更し、BOM、CRLF/LF/CR、コメント、インデント、末尾空白、
他のString ID、別出現の同じIDは保存する。
変更しない物理行と行区切りはバイト一致を検証する。
全文置換も引用符内だけ、span置換は名称spanだけを対象とする。
全before/afterで技術token列を検証し、生成値を再parseして全entryを照合する。
解析diagnostic、entry数、出現位置、IDが変わる出力も拒否する。

全ファイルをメモリ上で検証してから一時ディレクトリに保存し、
ディスク上のバイト・manifestを再検証して完成ディレクトリをrenameで公開する。
Windowsの一時的なファイルロックにはrenameだけを有限回再試行し、部分コピーには切り替えない。
生成失敗時は一時ディレクトリを除去する。既存source・reviewsの全ファイルSHA-256と入力の不変性も検査する。

## 成果物

`resources/jp/strings/key-value/` 以下にDE JPのローカル12ファイルを元の構成で収録する。
現在のplanでは `key-value-strings-utf8.txt` のみが変更される。
残る11ファイルは元のバイト列と完全一致する。
公式データを含むローカル検証用成果物なので、`dist/` はGit対象外。
配布用の最小override構成への整理や、ゲーム内ロード動作の検証は別工程とする。
このgeneratorはゲームのロード順や重複IDの優先順位を推測しない。

`manifest.json` は以下を記録する。標準serializer、UTF-8、Unicode escapeを使用する。

- generator version/schema
- patch-plan、裁定、scopeの入力hash
- DE JP各sourceファイルのhash
- Phase 1B/layout ledgerの検証済みhash
- 適用operations、full/span件数、変更ID数、変更ファイル数
- 全payloadファイルのSHA-256
- 適用漏れ・余分な変更・conflict・二重適用の検証結果

時刻・出力先絶対パス等の非決定的情報はmanifestへ入れない。同じ入力パスとバイト列からは、
出力先を変えてもpayloadとmanifestの全バイトが一致する。
manifest自身のhashは循環するためmanifestには含めないが、verify-onlyで内容を完全照合する。

現行結果: 385 operations、385 ID、全文227 / span158、変更ファイル1 / 12。
ユーザーによる10名称の[ゲーム内表示確認](game-validation.md)を記録した。他Modとの競合検証の詳細は未報告。
