# Source patch pipeline の冪等性

基準は `16faebd8c8e77d101d4c6cfda1b706eb8be3e2e1`。実sourceへの適用やMod生成を行わず、正規のscope → layout planとPhase 2A planへメモリ内sourceを再入力して検証する。

## 原因と検証方式

従来は `human_reviews.source_bindings_match`、`context_overrides.validate_source`、`adoption.signature` がbeforeの値・hashしか認識せず、後段の `already_consistent` / `already_matching` へ到達できなかった。layout裁定もbeforeのspanと証拠を参照するため同じ問題があった。

`source_states.py` は既存の検証を削除せず、その手前で次の状態を区別する。

| 状態 | 認証 | 計画 |
|---|---|---|
| `VALID_BEFORE` | 元の全文SHAと一致 | 元のplannerで検証しoperationを生成 |
| `ALREADY_APPLIED` | 正式afterの全文SHAと一致し、逆差分から復元したbefore全文SHA・ファイル全体SHAも一致 | 元のplannerで同じoperationを再証明しno-op |
| `STALE_OR_CONFLICT` | 第三の値、位置・出現数・source・証拠の不整合 | reject / blocked |

Full-value、spanともに全文を認証する。replacementのsubstring検索による受理はしない。span外のprefix/suffix、placeholder、tag、escape、formatting tokenの変化は全文SHAで拒否する。ファイル全体の復元SHAは、対象外の文字列、コメント、空白、BOM、物理改行も保護する。逆差分はメモリ内でのみ使用し、sourceを書き換えるAPIは追加していない。

解析済みentriesだけを変更してraw bytesやindexを据え置く入力も拒否する。仮想適用テストでは、メモリ内の正確な物理行を更新して再parseし、実ファイルの再読み込みと同じ入力を作る。

## 追加証拠

`reviews/source-patch-states.json` は既存ledgerとは別の機械的な証拠certificate。528件のbefore/after全文SHA、path/line/ID、operation全フィールドのSHA、最小限の逆差分、review JSON内容SHA、sourceファイルSHAを保存する。全文の原文コピーは含まず、逆差分の原文断片は全件合計1,368文字。コード内でcertificateのJSON内容SHAを固定する。review/certificateはGitのLF/CRLF checkout差で失効しないようcanonical JSONをhash化し、ゲームsourceは引き続き完全なraw bytesのSHAで照合する。

これは新しい訳語裁定ではない。既存104件、Phase 2Aの64 concepts / 249 bindings、layout 13 + 17件の内容・provenance・署名は変更しない。certificateは修正前のverified planから生成した。署名やhashを現在sourceに合わせて更新する自動処理は設けない。別の正式裁定・source revisionに移行する場合は、承認されたbefore planから証拠を再生成し、旧新operationの全フィールド差分と新しい証拠をレビューする必要がある。

## 各層の役割

- `adoption.signature` は認証されたafter値だけをbefore証拠へ戻し、従来と同じ署名payloadを計算する。第三の値は元署名に一致しない。
- Phase 1Bの裁定、Phase 2Aのbinding、context overrideは同じbefore証拠で従来のidentity・signature検証を維持する。contextのlive値は正式proposed_jpと完全一致するため、既存の `already_consistent` に到達する。
- scopeは元のspan証拠を保持し、認証された適用済みのrequired行を `already_consistent` と表示する。推論で見つかった本文・別conceptへの伝播候補はno-op認証しない。
- plannerはafter時のscopeを再生成して全行とmetadataを比較する。編集されたno-opフラグ、古いscopeの再利用、改変されたsuppressionは信用しない。sourceを変更した場合はscopeも再生成する。
- layout plannerは元の30件のlayout裁定を再検証してから適用済みoperationを取り除く。14594と17481もこの経路を通る。`tokens()`の意味は変更していない。newline変更は従来の明示的人間layout裁定の条件に従う。
- Phase 2A plannerは249 bindingsを検証し、適用済み141件を `already_matching` にする。Eagle tier / Skirmisher / Hei Guang / Iron Pagoda / Fire Lancer / Savarの概念・role境界は既存の署名で維持する。
- 下位の `patch_plan` は通常operationのafterを扱うが、layout裁定が必要なblocked項目は引き続き `layout_plan.integrate` で処理する。正式な最終baseline判定にはlayout統合後planを使う。

after / mixed時は安全のため元の証拠から再計画するので、beforeのみの場合より処理時間が増える。証拠・scope・plannerの入力は変更せず、新しい構造を返す。

返却operationの `expected_source_sha256` は、再証明した元のbefore証拠のSHAを保持する。このplanはdry-run結果であり、after/mixed sourceへ直接書き込むapply形式ではない。

## 再現テスト

```powershell
python -m unittest tests.test_source_states -v
python -m unittest discover -v
```

ローカルsourceが必要な回帰テストはsource不在時のみskipする。仮想適用と再計画は全てメモリ内で行い、Mod/dist生成テストは既存のPhase 2A authorization gateによってskipする。

テストは修正前の387 + 141件の全フィールドSHA、528 unique IDs、全afterの2回連続0件、264件適用のmixed-state、第三の値、span内外、技術記号、英語identity、concept、出現数・位置・index、対象外ファイルbytesのdrift拒否を確認する。既存の裁定・layout・概念境界テストも継続実行する。

## 変更ファイル

- `tools/localization/source_states.py`: 三状態の認証、証拠復元、scope再検証、no-op除外。
- `tools/localization/parser.py`: 元bytesをメモリ内で保持。
- `tools/localization/adoption.py`: afterから認証されたbefore署名payloadを計算。
- `tools/localization/human_reviews.py`: after証拠と元concept裁定を検証。
- `tools/localization/context_overrides.py`: after証拠と正式proposed_jpの完全一致を検証。
- `tools/localization/scope.py`: 認証済みのrequired行をno-opとして表示。
- `tools/localization/patch_plan.py`: 通常operationのafter対応。
- `tools/localization/layout_plan.py`: layout裁定を再検証しafterを除外。
- `tools/localization/phase2a_patch_plan.py`: wording/layoutのafter対応。
- `reviews/source-patch-states.json`: 修正前planのhashと最小逆差分証拠。
- `tests/test_source_states.py`: 実sourceのメモリ内回帰・合成技術記号テスト。
- `docs/source-patch-idempotence.md`: 設計、制約、再現手順と検証結果。

## 最終検証結果（2026-09-11）

| 検証 | 結果 |
|---|---|
| before baseline | 387 operations、修正前の全フィールドSHAと一致 |
| before Phase 2A | 141 operations、修正前の全フィールドSHAと一致 |
| before merged | 528 operations / 528 unique IDs、full-value 287 / span 241 |
| before conflict / duplicate / blocked | 全て0 |
| 全528件のメモリ内適用後 | baseline 0 / Phase 2A 0 operations、stale / conflict / duplicate / blocked 全て0 |
| 同じafterで2回目の再計画 | 引き続き0 operations、入力のentries・source bytes/hashは不変 |
| afterの裁定認識 | baseline 387件 already_applied、context 29件 already_consistent（変更27件を含む）、Phase 2A 249件 already_matching（変更141件＋既一致108件） |
| mixed（264件適用） | 残り264 operationsが修正前の該当operationと全フィールド一致、blocked 0 |
| drift拒否 | full-value、span内、prefix、suffix、placeholder、markup、technical escape、English identity、concept付け替え、出現数・位置・path・indexの不整合を拒否 |
| 追加のfail-closed検証 | otherwise-beforeの第三値、対象外コメント変更、scope改変、context提案不一致、certificate内容改変も拒否 |
| layout | 既存13＋Phase 2A 17＝30裁定を保持。14594「鉄浮屠」・17481「虎蹲砲」のafterを認証。tokens()は未変更 |
| 全テスト | 209件実行、205成功、4 skip、failure 0、error 0（292.929秒） |
| Git差分検査 | `git diff --check` 成功 |
| source / dist保護 | 開始時と終了時の全ファイルSHA一覧が完全一致。source 30ファイル、既存dist 188ファイル |
| 禁止操作 | sourceへの実patch、Mod/dist生成、commit、pushはいずれも実施せず。HEADは16faebdのまま |

全件ログはローカルの `reports/idempotence-final-verified.log`。修正前operationのローカル保存は `reports/idempotence-before.json`、保護対象の開始時SHA一覧は `reports/idempotence-protected.json`。これらはGit対象外。永続回帰テストの全フィールド不変性は、tracked certificate内のoperation SHAで検証する。

途中で発生した既存合成fixtureへのsnapshot検証の過剰適用は、raw bytesを持つ実snapshotとの区別を修正して解消した。上記全件結果は修正後の最終コードによるもの。
