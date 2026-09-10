# 人間裁定の永続記録

実機確認は [game-validation.json](game-validation.json) に別記録する。ユーザーが報告した7名称とString ID 170300 UI表示のPASSを現行387-entry翻訳hashへ結び付け、名称・全文・layout裁定のsignatureは変更しない。確認範囲と未提供情報は [実機確認記録](../docs/game-validation.md) を参照。

`phase1b-decisions.json` は2026-09-08にユーザーが明示した裁定を記録する正本。
自動生成レポートやMod用翻訳ファイルではない。採用訳はユーザー指定をそのまま保存し、新たな翻訳判断を追加していない。

現在は名称・concept裁定168件を保持する。内訳は従来の名称104件とPhase 2A core wording 64 concept。文脈付き全文裁定29件は `context-overrides.json` に分離し、合計197裁定を保持する。170300はUI文体の明示的人間裁定として、伝播しない `context_full_value` に記録する。
元の80候補と最初の追加5 IDは履歴上の基準。現在の仕様・件数・再生成手順は [文脈付きoverride](../docs/context-overrides.md) を参照。
一覧形式の records にすることで重複IDを読み込み時に検出できる。
review_id / reviewer / reviewed_on / authority に裁定の主体・日付を記録し、各項目はdecision、proposed_jp、notesを持つ。
expected_de_english と signature / help_ids でレビュー時の資料へ結び付ける。
baseline_ids と baseline_report_sha256 は元の80件との照合根拠であり、生成物が消えても裁定を復元できる。

Phase 2Aの追加64件は `binding_mode: phase2a_concept_occurrences_v1` を持つ。各recordは一つのfull name IDを主IDとし、`target_bindings` で同一gameplay conceptに属するfull name / compact name / action display / Help headingをrole単位に拘束する。249 target IDは全record間で一意で、141 IDが変更必要、108 IDが採用訳と既一致。actionとHelpは名称spanだけを拘束し、周辺全文をledgerへ複製しない。
64件は正式裁定だが、今回patch / Mod実装は行わないため `implementation_status: adjudicated_not_patch_enabled` とする。既存scope plannerはこれらを推論伝播せず、deferred adjudicationとして報告する。

同じ英語名を持つunitとupgrade technologyは別recordとし、各conceptで検証済みのHelp IDだけを `help_ids` に保持する。従来のinventoryが英語名から列挙するHelp集合を新規recordのconcept membershipには使用しない。各targetは日英sourceのpath・line・value hash、日本語名称span、role、採用訳を `binding_signature` で拘束し、concept全体を `target_scope_signature` で拘束する。source drift時は従来どおりfail closedとする。

元の52件は `reviews/human/wording-review_reviewed.tsv` のhash・行番号・人間裁定3列をprovenanceに保持する。family派生11件の明示承認と、Savar unitを「サヴァール」に統一する独立の明示裁定は異なるprovenance kindで記録する。取り込み根拠と検証結果は [Phase 2A wording ledger](../docs/phase2a-wording-ledger.md) を参照。

後発の明示的人間裁定は `historical_jp_variation` による旧訳復元方針より優先する。5105はkeep_de「イェニチェリ」、5455/7392はrevise「エリート イェニチェリ」、7432/17432はrevise「火箭術」を維持する。Rocketryのcontext全文裁定も「火箭術」を維持する。5350 Relicは今回追加したrestore「聖なる箱」。
未指定の関連IDへ裁定をコピーしない。

`context-overrides.json` は全文を確定したHelp・文明説明・シナリオ文章・改行付き表示の専用正本。
指定source出現位置の全文だけを所有し、名称への逆伝播・別文章への語句置換はしない。
元のsignatureに加え、JP/EN sourceの出現位置・hash・採用全文をbinding_signatureで拘束する。
無効なbindingでは名前伝播へフォールバックせず停止する。両正本への同一ID登録は禁止。
正本の分離で既存129件の採用訳・判断理由・signatureは変更していない。
その後、ユーザーがShinkichonの名称ID 7438 / 17438に「神機箭」を明示裁定したため、名称正本へreviseとして2件追加した。
研究Help 28438との対応をsourceで確認し、既存signature方式で拘束した。8438 / 28438 / 120167の全文裁定は変更しない。

資料更新により英語、関連Help、値、出現位置の指紋が変わった場合、人間裁定自体は消さない。
その行を approved_requires_revalidation とし、reviewer_* に指定値を保存したまま effective_* の適用候補を保留する。
古い裁定を自動案で上書きしたり、新しい用途へ自動適用したりしない。

## 今回の方針

1. 適切な場合、旧日本語版で確立された用語を維持する。
2. 後年の変更に明確な利点がない場合、定着した旧来の用語への復元を検討する。
3. 誤訳、訳抜け、用語の不統一、誤字、壊れた文字列などを修正する。
4. 英語原文の意味を維持し、不自然・不明瞭な日本語を改善する。
5. 旧訳自体に問題がある場合はDE維持またはreviseを選ぶ。
6. Eliteは旧版の「エリート」を基本とし、剣豪・重装亀甲船・強化戦車など個別裁定を優先する。

これは今回の人間裁定の方針の記録であり、未レビュー項目へ自動判断を追加する規則ではない。
