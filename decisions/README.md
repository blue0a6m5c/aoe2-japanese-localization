# 翻訳裁定の統一正本候補

`translations.json` は、人間が採用した翻訳、判断理由、concept境界、適用対象、明示レイアウトを、旧Phase/pipelineの実装状態から切り離して保存するための正本候補です。この移行では既存pipeline、source、Mod出力を変更していません。

## スキーマ

トップレベルは `schema_version` と `records` です。各recordは次のフィールドを持ちます。

- `id`: 安定した、人間が読めるconcept ID。英語表示そのものはidentityにせず、unit/technology等を接尾辞で区別します。
- `english`: 裁定時の英語名または全文。
- `category`: `unit | technology | building | ui | description | other`。
- `gameplay_object`: Phase 2A由来recordにだけ存在する、同名objectやtierを区別するための説明。
- `translation`: 採用する日本語。
- `decision`: `restore | keep_de | revise`。
- `reason`: 人間による判断理由。TSV由来52件では `判断理由` を原文のまま優先しています。
- `notes`: reasonだけでは失われるcontext限定条件など。追加情報がなければ `null`。
- `targets`: 適用対象。通常はrecordの `translation` を使用し、人間が全文またはlayoutを明示したtargetだけ `text` を持ちます。

target roleは `name | compact_name | action | help_heading | full_text` の5種だけを使用しています。旧 `full_name` は `name`、`action_display` は `action` へ正規化しました。

## 移行元と境界

正式な移行元は次の4ファイルです。

- `reviews/phase1b-decisions.json`
- `reviews/context-overrides.json`
- `reviews/phase1d-layout-decisions.json`
- `reviews/human/wording-review_reviewed.tsv`

`reports/phase1a/inventory.tsv` は旧104裁定のcategoryとname/compact_name roleの正規化にだけ補助参照し、翻訳・理由・対象を新しく決める根拠には使用していません。

旧104裁定のうち、Rocketryの7432/17432とShinkichonの7438/17438は、それぞれ同一technologyのname/compact_nameであり、各2裁定を1 concept recordへ統合しました。そのため、移行元の197裁定は新JSONでは195 recordsです。同名でもunitとtechnologyが異なるもの、normal/elite tier、別gameplay objectは統合していません。

旧名称裁定と後発のcontext全文裁定が重なる5 ID（26064、26065、28432、28438、28470）は、後発全文裁定の優先規則に従い `full_text` recordだけに所有させました。名称判断は採用全文中に保持されています。

## Migration audit

内容比較を含む監査結果です。

| 項目 | 結果 |
|---|---:|
| 新JSON records | 195 |
| 移行元の裁定表現数 | 197 |
| targets | 480 |
| `target.text` あり | 59 |
| context裁定 | 29 / 29 |
| layout裁定 | 30 / 30 |
| 旧layout / Phase 2A layout | 13 / 17 |
| Phase 2A concepts | 64 / 64 |
| Phase 2A targets | 249 / 249 |
| TSV reasons | 52 / 52 |
| duplicate String IDs | 0 |
| conflicting String IDs | 0 |
| unresolved / 要人間確認 | 0 |

category別: building 10、description 11、other 2、technology 71、ui 30、unit 71。

decision別: keep_de 32、restore 90、revise 73。移行元のrevise 75件との差2件は、RocketryとShinkichonの各name/compact_name裁定を1 recordへ統合した結果です。

role別targets: action 64、compact_name 72、full_text 29、help_heading 149、name 166。

監査A〜IはすべてPASSです。

- 旧名称裁定104件は、英語、採用訳、decision、reason、主String IDを内容比較しました。
- Phase 2Aは64 conceptをconcept単位で照合し、249 targetすべてのString IDと正規化後roleを比較しました。
- context 29件は英語全文、採用全文、decision、reason、target.textを比較しました。
- layout 30件はString IDとreplacement全文を比較しました。
- TSV 52件は採用訳、裁定、判断理由を対応recordと比較しました。
- unit/technology、tier、gameplay object境界を維持しました。
- 全targetを展開してString IDの重複と最終値の矛盾を検査しました。
- translationは正式移行元の採用値、target.textはcontext/layoutの明示値だけから作成しました。

## 意図的に移植しなかった情報

以下は翻訳裁定ではなく、旧実装・検証・証拠固定のmetadataなので新JSONへ移植していません。

- `signature`、`binding_signature`、`target_scope_signature`
- `source_sha256`、`current_value_sha256`、`en_value_sha256`、`jp_value_sha256`、各種ledger/report hash
- `source_path`、`source_line`、英語・日本語source位置、`jp_span`、`matched_span`
- `current_japanese_term`、`change_required`、`already_matching`、already-applied state
- `implementation_status`、binding mode、operation requirement、patch状態
- authorization、certificate、authority、reviewer、review ID、review日
- baseline IDs、baseline report、adjudication set、final-set reference
- Phase番号とpipeline固有provenance
- layout bindingのcurrent/matched/canonical/request情報

contextの出現限定という意味は `notes` と `full_text` targetに、layoutの人間指定値は `target.text` に残しています。Phase 2Aの `de_object` は実装metadataではなくconcept境界の情報なので、`gameplay_object` として保持しました。

