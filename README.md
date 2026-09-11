# AoE2 Japanese Localization

A comprehensive refinement project for the Japanese localization of
**Age of Empires II: Definitive Edition**.

This project aims to improve the consistency, accuracy, readability, and
overall quality of the Japanese localization while respecting the
terminology and localization style established by the original Japanese
releases of **Age of Empires II: The Age of Kings (1999)** and **The
Conquerors (2000)**.

The final output is intended to be distributed as an **Age of Empires
II: Definitive Edition localization Mod** containing only the
localization overrides required by this project.

## Goals

The Japanese localization of Age of Empires II has changed considerably
over its long history.

Some terminology established in the original Japanese releases was later
replaced despite the underlying game concept remaining unchanged. At the
same time, newer expansions contain inconsistent terminology, awkward
translations, abbreviations, omissions, and other localization issues.

This project systematically reviews these strings and builds a coherent
Japanese localization for the modern game.

The general principles are:

-   Preserve established terminology from the original Japanese releases
    of Age of Empires II where appropriate.
-   Use official AoK/AoC Japanese terminology as an important baseline;
    record specific reasons before preferring changed terminology where
    the distinction matters.
-   Correct mistranslations, omissions, inconsistent terminology,
    typographical errors, and malformed strings.
-   Improve awkward or unclear Japanese while preserving the meaning of
    the English source.
-   Apply the localization conventions of classic AoE II consistently to
    content introduced in later expansions where appropriate.
-   Research historical terminology, names, transliterations, and
    cultural context where direct translation is insufficient.
-   Respect intentionally distinct terminology used by separate game
    systems such as **Chronicles**, rather than mechanically forcing all
    content into the standard AoE II vocabulary.
-   Preserve gameplay-relevant information, formatting codes,
    placeholders, markup, and other technical elements of the original
    strings.

The goal is **not** to mechanically revert every string to an older
translation.

The original localization serves as an important stylistic and
terminological foundation, but accuracy, historical context, gameplay
context, later official usage, and the current game design must also be
considered.

## Architecture

The project separates **research**, **human translation decisions**, and
**production**.

The intended data flow is:

``` text
Research
   ↓
Human adjudication
   ↓
decisions/
   ↓
Validation
   ↓
Build
   ├── localization Mod
   └── human-readable glossary
```

### Research

Research tools and historical datasets exist to provide evidence for
translation decisions.

They may:

-   compare AoK, AoC, HD, and DE localization data;
-   extract legacy Japanese strings;
-   inventory gameplay names and related strings;
-   identify terminology inconsistencies;
-   group related occurrences by gameplay concept;
-   locate candidate strings requiring human review.

Research output is evidence, not an automatic translation decision.

The project does not mechanically adopt a translation merely because it
appears in an older release, occurs more frequently, or is detected by
an audit.

### Decisions

Human-approved translation decisions are the authoritative localization
data of the project.

The current consolidated decision dataset is stored under:

``` text
decisions/
```

`decisions/translations.json` currently consolidates the human
translation decisions recovered from the earlier review and Phase-based
workflow.

This decision data records not only the selected Japanese wording, but
also the reason for the decision and the relevant target strings where
applicable.

The project is migrating toward keeping translation decisions in small,
independently readable records so that routine work does not require
loading or modifying a large monolithic dataset.

The **decision data**, rather than historical reports, patch plans,
generated glossaries, or build artifacts, is the source of truth for
approved translations.

### Production

Production consumes approved decision data and generates the
localization Mod.

Production must not determine translations on its own.

The intended production path is deliberately small:

``` text
decisions
   ↓
validate
   ↓
build
   ├── Mod
   └── generated documentation
```

Adding or revising an ordinary translation decision should be a **data
change**, not a Python code change.

Routine validation should be implemented in stable reusable validators
and tests rather than one-off scripts written for each translation
change.

## Source of Truth and Generated Data

The repository follows a one-way data model.

``` text
source/       upstream reference data; read-only
decisions/    authoritative approved translation decisions
glossary/     human-readable generated documentation
dist/         generated Mod/build output
reports/      generated research and audit output
docs/         policies, architecture, research notes, and historical documentation
```

### `decisions/`

`decisions/` is the authoritative source for approved translation
decisions.

Translation wording and its rationale should not be independently
maintained in multiple locations.

### `source/`

`source/` contains local copies of upstream game localization data used
for research, comparison, validation, and building.

Files under `source/` are **reference inputs and must be treated as
read-only**.

Localization tools must not patch or rewrite the upstream source files
as part of the normal workflow.

Generated localization changes must be written to separate Mod/build
output.

The directory is excluded from Git tracking because original game
localization files are not distributed by this repository.

### `glossary/`

The glossary is intended to be a human-readable representation of the
approved decision data.

It is **not** an independent translation database.

The target architecture generates the glossary from `decisions/` during
the normal build process so that GitHub retains a readable terminology
reference without requiring duplicate manual maintenance.

Generated glossary data must not become a second source of truth.

### `dist/`

`dist/` contains generated Mod or build artifacts.

The intended final localization Mod contains only the String IDs
overridden by this project, rather than modified copies of the complete
official localization dataset.

## Development Principles

The project favors a small, data-driven production workflow.

### Translation changes should be data changes

Adding or revising a normal translation decision should not require new
Python implementation code.

Code should change only when the localization data model, validation
rules, research capabilities, or build format itself needs to change.

### Avoid ad-hoc validation scripts

Routine checks belong in the standard validator or permanent test suite.

Do not create a new temporary Python program every time a translation
decision needs to be checked.

If a validation rule is generally necessary, implement it once as part
of the reusable validation system.

### Keep production independent from research complexity

Research may be sophisticated because localization research sometimes
requires historical comparison, structural inference, or concept
discovery.

Production should remain simple.

Building the Mod should not require replaying the complete research
process or reconstructing how every decision was originally discovered.

### Do not duplicate authoritative data

Approved translations and their rationale should have one authoritative
representation.

Human-readable glossaries, reports, Mod files, and other views should be
derived from that data wherever practical.

### Prefer targeted operations

Tools and automated agents should read and modify only the data relevant
to the current task whenever possible.

Repository-wide analysis should be reserved for tasks that genuinely
require it.

This keeps routine development easier to audit, faster to execute, and
less expensive for automated tooling.

### Preserve technical correctness

Generated strings must preserve required technical syntax such as
placeholders, formatting tokens, markup, and gameplay-relevant
information.

Validation should fail clearly when a decision cannot be applied safely.

## Reference Sources

During research, the project may compare localization data from several
generations of Age of Empires II:

1.  **Age of Empires II: The Age of Kings (1999)**
2.  **Age of Empires II: The Conquerors (2000)**
3.  **Age of Empires II HD Edition (2013)**
4.  **Age of Empires II: Definitive Edition**
5.  The current English localization of Definitive Edition

These sources allow the project to trace how terminology has changed
over time and distinguish intentional improvements from unnecessary,
inconsistent, or erroneous changes.

Legacy Japanese localization is treated as historical and terminological
evidence, not as an unconditional replacement for current localization.

## Historical Phase Documentation

Earlier development was organized into numbered Phases.

Those Phases produced important research tools, review data, validation
techniques, and Mod-building experiments. Their documentation remains
under `docs/` as project history and as reference material for research
functionality.

Broadly:

-   **Phase 0** established safe parsing and String ID based comparison
    of localization files.
-   **Phase 0.5** added extraction of Japanese AoK/AoC RT_STRING
    resources from local game DLLs.
-   **Phase 1A** created an evidence-linked gameplay name inventory and
    review candidates.
-   **Phase 1B** introduced explicit human translation adjudication.
-   **Phase 1C** audited where approved terminology appeared in
    gameplay-related strings.
-   **Phase 1D** converted approved changes into occurrence-bound
    dry-run patch plans.
-   **Phase 1E** generated an independent verification payload without
    modifying source data.
-   **Phase 1F** demonstrated a practical delta Mod containing only
    changed String IDs.
-   **Phase 2A** expanded structural terminology auditing and later
    human adjudication to additional concepts.

The project is now simplifying the production architecture.

Useful historical comparison, inventory, and terminology-audit
capabilities remain valuable as **research tools**. Human translation
decisions are being consolidated under `decisions/`, while the legacy
multi-stage patch, certificate, authorization, and source-application
machinery is not intended to define the future routine production
workflow.

Historical Phase documentation describes how the project reached its
current state; it should not be interpreted as requiring every future
translation change to pass through the complete historical pipeline.

## Current Status

The project has completed a consolidation of existing human translation
decisions into:

``` text
decisions/translations.json
```

The consolidated dataset preserves approved translations, rationales,
categories, and target information recovered from the earlier review
workflow.

The project is currently simplifying its architecture around three
responsibilities:

1.  retain useful research and historical-comparison capabilities;
2.  maintain approved translation decisions as a clear and compact
    source of truth;
3.  generate and validate the localization Mod from those decisions
    through a small reusable production workflow.

The next architectural work is expected to include:

-   organizing decision data into smaller independently readable
    records;
-   establishing permanent reusable validation for decision data;
-   generating the localization Mod directly from approved decisions
    without modifying `source/`;
-   generating the human-readable glossary from the same decisions;
-   separating legacy production machinery from research functionality
    that remains useful.

Until that migration is complete, historical tools and documents may
still describe the previous Phase-based workflow.

They should not be extended merely to preserve the old architecture
unless legacy maintenance is explicitly required.

## Intended Workflow

For ordinary localization work, the intended workflow is:

1.  Research a term or localization issue using the evidence appropriate
    to that case.
2.  Make an explicit human translation decision.
3.  Record or update that decision under `decisions/`.
4.  Run the standard validation/build workflow.
5.  Review the generated changes.
6.  Test the resulting Mod in Age of Empires II: Definitive Edition
    where appropriate.
7.  Revise the decision if gameplay context or further research shows
    that a change is needed.

The desired steady-state workflow is intentionally simple:

``` text
research
   ↓
decision
   ↓
validate
   ↓
build
   ↓
game verification
```

A new translation decision should not require a new pipeline, a new
ledger format, or a new validation script.

## Repository Policy

Original localization files distributed with Age of Empires II are **not
distributed through this repository**.

Local copies may be placed under `source/` for development, comparison,
validation, and build purposes. These files must come from the
contributor's own legitimate game installation and remain outside Git
tracking.

The repository instead contains project-created material such as:

-   approved localization decisions;
-   translation policies;
-   generated or human-readable terminology documentation;
-   research and validation tools;
-   build tools;
-   tests;
-   architecture and historical documentation.

## Disclaimer

This is an unofficial fan project and is not affiliated with or endorsed
by Microsoft, Xbox Game Studios, World's Edge, Forgotten Empires, or
other rights holders.

Age of Empires and related names and assets are trademarks and/or
copyrighted materials of their respective owners.

------------------------------------------------------------------------

# AoE2 日本語ローカライズ

**Age of Empires II: Definitive Edition**
の日本語ローカライズを包括的に改善するプロジェクトです。

本プロジェクトでは、**Age of Empires II: The Age of
Kings（1999）**および**The
Conquerors（2000）**の日本語版で確立された用語や翻訳スタイルを尊重しつつ、現行Definitive
Editionの日本語について、一貫性・正確性・可読性・翻訳品質の向上を目指します。

最終的な成果物は、本プロジェクトで必要なローカライズ差分のみを収録した
**Age of Empires II: Definitive Edition用日本語ローカライズMod**
とすることを想定しています。

## 目的

Age of Empires
IIの日本語ローカライズは、長い歴史の中で大きく変化してきました。

旧日本語版で定着していた用語の中には、ゲーム上の概念自体には変化がないにもかかわらず、後のバージョンで別の訳語へ変更されたものがあります。一方、近年追加されたコンテンツには、既存用語との不整合、不自然な翻訳、省略、訳抜け、その他のローカライズ上の問題も見られます。

本プロジェクトでは、これらを体系的に検証し、現代のAoE2全体で一貫性のある日本語ローカライズを構築することを目指します。

基本方針は以下の通りです。

-   適切な場合、AoE2旧日本語版で確立された用語を維持する。
-   AoK/AoC日本語版の公式用語を重要な基準とし、異なる訳語を採用する場合は、必要に応じてその理由を明示する。
-   誤訳、訳抜け、用語の不統一、誤字、壊れた文字列などを修正する。
-   英語原文の意味を維持しながら、不自然・不明瞭な日本語を改善する。
-   後発の拡張コンテンツについても、適切な場合は旧来のAoE2日本語版の命名規則との整合性を確保する。
-   単純な直訳では不十分な場合、歴史的な用語、名称、音写、文化的背景を調査する。
-   **Chronicles**など独自のゲーム体系・命名体系を持つコンテンツについては、その意図的な差異を尊重し、通常のAoE2用語へ機械的に統一しない。
-   ゲーム上必要な情報、書式コード、プレースホルダー、マークアップなどの技術的要素を維持する。

本プロジェクトの目的は、**すべての文字列を機械的に旧訳へ戻すことではありません**。

旧日本語版を重要な用語・スタイル上の基礎としながら、翻訳の正確性、歴史的背景、ゲーム内文脈、後年の公式用例、現在のゲーム仕様についても考慮します。

## アーキテクチャ

本プロジェクトでは、**調査**、**人間による翻訳裁定**、**Mod生成**を分離します。

想定するデータの流れは次の通りです。

``` text
調査
 ↓
人間による裁定
 ↓
decisions/
 ↓
検証
 ↓
ビルド
 ├── ローカライズMod
 └── 人間向け用語集
```

### 調査

調査ツールや歴史的データセットは、翻訳を判断するための根拠を提供します。

たとえば次のような用途があります。

-   AoK、AoC、HD、DEのローカライズ比較
-   旧日本語版文字列の抽出
-   ゲーム内名称と関連文字列のinventory
-   用語不整合の検出
-   同一ゲーム概念に属する出現の構造的な整理
-   人間による確認が必要な候補の抽出

調査結果そのものは、自動的な翻訳裁定ではありません。

旧版に存在する、出現頻度が高い、監査ツールが検出した、といった理由だけで訳語を機械的に採用することはしません。

### 翻訳裁定

人間が承認した翻訳裁定を、本プロジェクトの正式なローカライズデータとします。

現在、統合された裁定データは次の場所に保存されています。

``` text
decisions/
```

`decisions/translations.json`
には、従来のレビューおよびPhaseベースの作業から回収・統合した人間の翻訳裁定が保存されています。

裁定データには採用した日本語だけでなく、その理由や、必要に応じてゲーム内の適用対象も記録します。

今後は、通常の作業で巨大な単一データセット全体を読み書きする必要がないよう、翻訳裁定を小さく独立して読める単位へ整理していく方針です。

承認済み翻訳の正本は、過去のレポート、patch
plan、生成用語集、ビルド成果物ではなく、**裁定データそのもの**です。

### Mod生成

Production側は承認済みの裁定データを入力として、ローカライズModを生成します。

Production側が独自に訳語を決定することはありません。

目標とする生成経路は意図的に小さく保ちます。

``` text
decisions
   ↓
validate
   ↓
build
   ├── Mod
   └── 自動生成ドキュメント
```

通常の翻訳裁定の追加・修正は、**データの変更**で完結し、Pythonコードの変更を必要としないことを原則とします。

日常的な検証は、翻訳変更のたびに作成する一時的なスクリプトではなく、恒常的なvalidatorとtest
suiteへ集約します。

## 正本と生成データ

リポジトリでは、データの流れを一方向にします。

``` text
source/       公式ゲーム由来の参照データ。read-only
decisions/    承認済み翻訳裁定の正本
glossary/     人間向けの自動生成ドキュメント
dist/         生成されたMod / build成果物
reports/      調査・監査による生成物
docs/         方針、設計、調査記録、開発史
```

### `decisions/`

`decisions/` を、承認済み翻訳裁定の正式な正本とします。

訳語とその理由を複数の場所で独立して手動管理しません。

### `source/`

`source/`
には、調査・比較・検証・ビルドのために各自のゲーム環境から取得した公式ローカライズデータを配置します。

`source/` 以下のファイルは**参照入力であり、read-onlyとして扱います**。

通常のローカライズ作業で、ツールが公式sourceをpatchしたり書き換えたりしてはいけません。

翻訳変更は、必ず別のMod / build出力として生成します。

公式ゲーム由来のローカライズファイルを本リポジトリで配布しないため、このディレクトリはGitの追跡対象外です。

### `glossary/`

用語集は、承認済み裁定データを人間が読みやすい形で表現するためのものです。

独立した翻訳データベースではありません。

目標とするアーキテクチャでは、通常のビルド時に `decisions/`
から用語集を自動生成します。これにより、GitHub上では可読性の高い最新の用語集を参照できる一方、同じ翻訳情報を二重に手動管理する必要をなくします。

生成された用語集を第二の正本として扱ってはいけません。

### `dist/`

`dist/` には生成されたModまたはbuild成果物を出力します。

最終的なローカライズModは、公式ローカライズデータ全体の変更済みコピーではなく、**本プロジェクトが上書きするString
IDだけを含む差分Mod**とする方針です。

## 開発原則

本プロジェクトのproduction workflowは、小さくデータ駆動型に保ちます。

### 翻訳変更はデータ変更とする

通常の翻訳裁定を追加・修正するために、新しいPython実装コードを必要としない設計を維持します。

コードを変更するのは、データモデル、検証規則、調査能力、ビルド形式そのものを変更する必要がある場合に限ります。

### ad-hocな検証スクリプトを増やさない

日常的に必要な検査は、標準validatorまたは恒常的なtest
suiteに実装します。

翻訳裁定を確認するたびに、新しい一時Pythonプログラムを作成する運用は行いません。

一般的に必要な検証規則であれば、一度だけ再利用可能な検証機構として実装します。

### ProductionをResearchの複雑さから分離する

翻訳研究には、歴史比較、構造推論、concept
discoveryなど複雑な処理が必要になる場合があります。

Research側が高度になること自体は問題ありません。

一方、Mod生成は単純に保ちます。

Modを生成するために、すべての調査過程を再実行したり、各裁定が発見された歴史的経路を再構築したりする必要はありません。

### 正本を重複させない

承認済みの訳語とその理由は、一つの正式な表現を持つようにします。

用語集、レポート、Modファイルなどの別表現は、可能な限り正本から生成します。

### 必要な範囲だけを扱う

ツールや自動化エージェントは、可能な限り現在の作業に必要なデータだけを読み、変更します。

リポジトリ全体の解析は、本当に必要な作業に限定します。

これにより、通常の開発を監査しやすくし、実行コストと自動化ツールのコンテキスト消費を抑えます。

### 技術的整合性を維持する

生成される文字列では、プレースホルダー、書式トークン、マークアップ、ゲーム上必要な情報などの技術的要素を維持します。

安全に適用できない裁定が存在する場合、検証処理はその問題を明確に報告します。

## 参照資料

調査時には、AoE2の複数世代のローカライズデータを比較します。

1.  **Age of Empires II: The Age of Kings（1999）**
2.  **Age of Empires II: The Conquerors（2000）**
3.  **Age of Empires II HD Edition（2013）**
4.  **Age of Empires II: Definitive Edition**
5.  Definitive Editionの現行英語版

これらを比較することで、用語がどの時点で変更されたのかを追跡し、意図的な改善と、不必要・不整合・誤りのある変更を区別します。

旧日本語版は歴史的・用語的な重要資料として扱いますが、現行訳を無条件に置き換えるものではありません。

## 旧Phaseの位置づけ

これまでの開発は、番号付きのPhaseに分けて進めてきました。

各Phaseからは、現在も有用な調査ツール、レビュー情報、検証手法、Mod生成に関する知見が得られています。各Phaseの詳細な文書は、開発史およびResearch機能の参考資料として
`docs/` に残します。

大まかな役割は次の通りです。

-   **Phase 0** --- ローカライズファイルの安全なparseとString
    ID単位の比較基盤
-   **Phase 0.5** --- AoK/AoC日本語版のRT_STRING resource抽出
-   **Phase 1A** --- ゲーム内名称inventoryとレビュー候補の抽出
-   **Phase 1B** --- 明示的な人間による翻訳裁定
-   **Phase 1C** --- 採用した用語がゲーム内のどこに現れるかのscope監査
-   **Phase 1D** --- 裁定をoccurrence-boundなdry-run patch planへ変換
-   **Phase 1E** --- sourceを変更せず独立した検証用payloadを生成
-   **Phase 1F** --- 変更String IDだけを含む実用的な差分Modの検証
-   **Phase 2A** ---
    構造的な用語監査を拡張し、追加conceptについて人間裁定を実施

現在はproduction architectureの簡素化を進めています。

歴史比較、inventory、terminology
auditなど有用な機能は**Researchツール**として今後も価値があります。一方、人間による翻訳裁定は
`decisions/`
に集約し、後期に増加した多段patch、certificate、authorization、source-application機構を将来の日常的なproduction
workflowの前提とはしません。

旧Phase文書は、本プロジェクトが現在地点へ至った経緯を記録するものです。今後の翻訳変更すべてについて、歴史上のpipeline全体を再実行しなければならないという意味ではありません。

## 現在の状況

既存の人間による翻訳裁定は、現在、

``` text
decisions/translations.json
```

へ統合されています。

この統合データには、従来のreview
workflowから回収した承認済み訳語、理由、category、適用対象などが保存されています。

現在は、次の3つの責務を中心にアーキテクチャを簡素化しています。

1.  有用な調査・歴史比較機能を維持する。
2.  承認済み翻訳裁定を明確で小さな正本として管理する。
3.  その裁定から、小さく再利用可能なproduction
    workflowでModを検証・生成する。

今後の移行作業として、次の内容を予定しています。

-   裁定データを小さく独立して読める単位へ整理する。
-   裁定データ用の恒常的なvalidationを整備する。
-   `source/`
    を変更せず、承認済み裁定から直接ローカライズModを生成する。
-   同じ裁定から人間向け用語集を自動生成する。
-   有用なResearch機能と、退役対象となる旧production機構を分離する。

この移行が完了するまでは、旧Phaseベースのworkflowを前提としたツールや文書がリポジトリ内に残っています。

明示的にlegacy
maintenanceが必要な場合を除き、旧architectureを維持するためだけにそれらを拡張しない方針です。

## 想定ワークフロー

通常の翻訳作業では、次の流れを目標とします。

1.  必要な資料を用いて用語またはローカライズ上の問題を調査する。
2.  人間が明示的に翻訳を裁定する。
3.  `decisions/` に裁定を追加または更新する。
4.  標準のvalidation / build workflowを実行する。
5.  生成された差分を確認する。
6.  必要に応じてAoE2:DE上でModを目視確認する。
7.  ゲーム内文脈や追加調査から問題が判明した場合は、裁定データを修正する。

目標とする定常運用は意図的に単純です。

``` text
調査
 ↓
裁定
 ↓
validate
 ↓
build
 ↓
ゲーム内確認
```

新しい翻訳裁定のために、新しいpipeline、新しいledger形式、新しい検証スクリプトを作る必要がない状態を目指します。

## リポジトリの方針

Age of Empires
IIに含まれる**公式ローカライズファイルそのものは、本リポジトリでは配布しません**。

開発・比較・検証・ビルドのため、各自の環境にある公式ファイルを `source/`
以下へ配置することがあります。これらは各自が正規に入手したゲームから取得し、Gitの追跡対象外とします。

GitHubで管理するのは、原則として本プロジェクトが作成した以下のようなデータです。

-   承認済み翻訳裁定
-   翻訳方針
-   自動生成または人間向けの用語資料
-   調査・検証ツール
-   ビルドツール
-   テスト
-   設計文書および開発史

## 免責事項

本プロジェクトは非公式のファンプロジェクトであり、Microsoft、Xbox Game
Studios、World's Edge、Forgotten
Empiresその他の権利者とは関係ありません。

Age of
Empiresおよび関連する名称・素材の権利は、それぞれの権利者に帰属します。
