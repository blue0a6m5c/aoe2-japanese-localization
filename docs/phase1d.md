# Phase 1D dry-run patch plan

> Current pipeline: [context-bound overrides](context-overrides.md). 104 name + 29 direct decisions; 387 operations, conflicts 0, final blocked 0. Counts and default paths below document the original phase baseline. Use matching current scope/plan paths.

Phase 1B正本とPhase 1C normalized監査から変更計画を作る。source・正本・Mod用翻訳は変更しない。
適用API、applyコマンド、Modビルド機能は実装していない。

```powershell
python -m tools.localization patch-plan
python -m tools.localization patch-plan --scope-dir reports/phase1c-normalized --output-dir reports/phase1d-next
python -m unittest discover -v
```

既定の正本は `reviews/phase1b-decisions.json`（--ledgerで指定可能）。出力はreports/phase1d以下のpatch-plan.json、patch-plan.tsv、patch-summary.md、blocked.json。
既存出力を上書きしない。検証失敗があっても安全な位置の計画とblockedを出力する。
blockedがある場合、または既存の入力診断・重複が残る場合は終了コード1。入力読取・構成のエラーは2。

## 入力と対象

scope-audit.tsvのrequiredかつ実変更候補のみを採用する。
recommended/review/unrelated/already_consistentを自動適用候補へ昇格させない。
requiredと誤記されたnormalized-equivalentも実値から再判定してblockedにする。

監査metadataの全入力ファイルSHA-256を現在の解析結果と照合する。DE日英だけでなく、裁定signatureの根拠であるLegacy/HDの現行ローカル資料も検証に用いる。
入力ファイルに一つでも不一致・欠損があれば、監査全体が古いものとしてすべてのrequired位置をblockedにする。
正本の指紋、各裁定signature、現在の英語名、関連Help集合、採用訳・decisionも確認する。
Phase 1Dで新たな採用訳を作ったり、人間裁定を変更したりしない。

## 出現とspanの検証

- datasetはDE JPに限定。source_path / source_line / String IDで一意な出現を選ぶ。
- 同一IDの他出現を選択しない。同じ位置が複数回ロードされている場合もblocked。
- 対応するDE ENの出現位置とファイルを確認し、名称・共有Help・ボタン・Help見出しのrelationを再検証する。
- start/endは原文保存値に対するUnicode文字位置の半開区間。検索による代替箇所の選択を行わない。
- before[start:end]と監査のmatched_jpが完全一致し、保存されたレビュー抜粋も一致することを確認する。
- Phase 1Cの抜粋はfull beforeではないため、原文全体は監査時のファイルSHA-256一致を根拠に取得し、beforeとexpected_value_sha256として計画に保存する。
- 名称全体、Helpの最初の名前見出し、ボタンの括弧前の名称という対象位置も確認する。ボタンの動詞・説明文を名称として置換しない。

同じ語が本文中にもあること自体はエラーにしない。明示された出現位置とspanによって一つに特定できる場合、他の出現は保持する。
位置未指定、範囲外、値不一致、relationの根拠不一致、候補フラグ不一致をblockedとして記録する。

## 技術構文とレイアウト

afterはbeforeの指定spanだけをcanonical translationへ置換した文字列。残りの文字はそのまま保存する。
タグ、printf型placeholder、波括弧、引用符、バックスラッシュによるエスケープ、実改行・タブの並びが変わる場合はblocked。
この検査は形式保存の防御であり、未収集のゲーム構文まで解釈するものではない。

名称spanに表示用改行が含まれる場合、単純な採用訳への置換では改行を失うことがある。
この場合はtechnical_structure_changedとして保留し、採用訳のどこへ改行を置くかを推測しない。
normalized-equivalentの14112/14128等は元から対象外。
Royal Janissary 26115は最初の名称spanだけを変更し、Help本文・cost等を保持する。

## 統合と衝突

同一source出現・同一spanへの同じ置換は1 operationに統合し、全decision/relation/signatureをevidenceへ保存する。
異なる置換、重なるspan、いずれかの候補の検証失敗は、同じsource出現全体をblockedにする。
同じIDであっても別の出現は独立した位置として扱う。通常のPhase 1C監査では重複入力がreviewに留まるため、自動計画に入らない。

operationsは1つのspan編集ごとのbefore/afterを持つ。複数の非重複spanが同じ値を編集する場合、locations.afterに全操作後の値を保存する。
offsetは常に共通のbefore基準であり、直前操作のafterに対する位置ではない。
集計のblocked件数はsource出現位置数、blocked_candidate_rowsは統合前の監査行数。
decision/relation別件数は複数の根拠を含むため、足し合わせてもoperation総数にはならない。

## 次工程

レイアウトが必要なblocked位置の改行方針を人間が確認し、監査へ明示的なspan/置換根拠を追加する必要がある。
この計画を直ちにString IDだけのMod辞書へ平坦化してはならない。将来の適用時にも同じ出現・hash・beforeを再検証し、Mod側の重複ID解決・シリアライズ・ゲーム内表示を別Phaseで確認する。
