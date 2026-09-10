# Phase 2A wording正式裁定

## 正本

正式裁定は [reviews/phase1b-decisions.json](../reviews/phase1b-decisions.json) に記録する。従来104 recordsは順序・内容とも保持し、その後ろへPhase 2A core wording 64 conceptを追加した。

取り込み根拠はローカル監査成果物 `reports/phase2a/adjudication-final-set-20260910/final-adjudication-set.tsv` と `target-strings.tsv`。元の52件は `reviews/human/wording-review_reviewed.tsv` の採用訳・裁定・判断理由を正本provenanceとして保持する。family派生11件の一括承認とSavar unitの個別裁定は別のprovenance kindで記録する。

## concept-scoped binding

Phase 2A recordは `binding_mode: phase2a_concept_occurrences_v1` を持つ。

- `string_id`: conceptの主full name ID
- `concept_id` / `category` / `de_object`: gameplay identity
- `help_ids`: そのconcept自身のHelp heading ID。英語名が同じ別objectのHelpを含めない
- `signature`: 主IDとconcept固有Helpの従来方式source signature
- `target_bindings`: full name / compact name / action display / Help headingの全対象
- `binding_signature`: 各targetのrole、source位置、日英value hash、日本語名称span、採用訳、変更要否の指紋
- `target_scope_signature`: 一つのconceptに属するtarget集合全体の指紋
- `implementation_status`: `adjudicated_not_patch_enabled`。裁定は正式だが、role/span-aware patch実装は今回未承認

全文sourceはledgerへ保存しない。action displayとHelpは日本語名称spanだけを保持し、動詞、説明本文、別unitへの言及を裁定範囲に含めない。compact nameの改行を含む現行spanはsource hashと別に拘束する。

従来recordは従来どおりinventoryのlive Help集合と一致することを要求する。Phase 2A recordは、英語名だけからunitとtechnologyのHelpを混ぜないため、明示したconcept固有 `target_bindings` を検証する。いずれもsource drift時は `approved_requires_revalidation` となり、採用訳を自動的に別IDへ伝播しない。

## 件数と境界

Phase 2A追加分は64 concept、249 target ID。141 IDが変更必要で、108 IDは採用訳と既一致。target IDの重複、既存104件との主ID衝突、既存context/layout裁定との変更ID衝突は0件。

Eagle系はunit 751 → 753 → 752を別tierとして保持する。Elite SkirmisherとImperial Skirmisherは対象外。Hei Guang Cavalry、Fire Lancer、Savar、および同名のElite upgradeはunitとtechnologyを別conceptとして保持する。

## 検証

```powershell
python -m unittest discover -v
```

`tests/test_phase2a_wording_ledger.py` は従来104 recordsのhash、64 concept、249 target ID、141/108内訳、provenance区分、保護済み裁定、cross-concept境界を検証する。ローカルのcopyrighted sourceとreview資料が存在する場合は、全target signatureと52＋12裁定の一致も検証する。

この取り込みは正式裁定ledgerと検証コードだけを更新する。patchおよびModは生成しない。
既存の名称scope plannerはPhase 2A recordを実装対象から明示的に除外し、`deferred_adjudication_ids` に64主IDを報告する。これにより旧式の英語名・Help推論で249 targetへ波及することを防ぐ。将来patch対応を行う場合は `target_bindings` を直接消費し、別途承認された実装段階で `implementation_status` を更新する。

patch enable前の検証では `tools.localization.phase2a_patch_plan` が64 recordsの249 target bindingsを
直接消費する。compact nameのうち人間layout判断が必要な17 IDは
`reviews/phase1d-layout-decisions.json` のPhase 2A scoped recordsを照合し、残りへ類似名や
English名から伝播しない。これは仮想dry-run専用であり、`implementation_status` は
`adjudicated_not_patch_enabled` のまま、sourceへのapply APIも持たない。
