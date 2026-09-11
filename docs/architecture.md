# Architecture

This document defines the target architecture of the AoE2:DE Japanese
localization project.

It describes the intended steady-state system, not the historical Phase
pipeline. Historical tools and documents may remain in the repository
during migration, but they do not define the future production
architecture.

For project goals and translation policy, see `README.md`. For concise
agent operating rules, see `AGENTS.md`.

------------------------------------------------------------------------

## 1. Design Goals

The architecture is built around one simple production workflow:

``` text
translation decision
        ↓
decision data change
        ↓
validate
        ↓
build
        ↓
Mod + generated documentation
```

The main goals are:

1.  **Human decisions are authoritative.** Research and automation
    support decisions but do not silently replace them.

2.  **Translation knowledge has one source of truth.** Approved
    translations, their reasons, concept boundaries, and targets live in
    `decisions/`.

3.  **Upstream game data is read-only.** Files under `source/` are
    reference inputs. Production does not patch them in place.

4.  **Routine translation changes are data-only.** Adding or revising an
    ordinary translation should not require new Python code, a new
    ledger, a new certificate, or a new pipeline stage.

5.  **Production is smaller than research.** Research may require
    complex analysis. Building the Mod from already approved decisions
    should remain simple and deterministic.

6.  **Generated data is not manually maintained.** Glossaries, reports,
    manifests, and Mod payloads are derived outputs.

7.  **The system should be efficient for both humans and AI agents.**
    Ordinary work should require only the relevant decision records and
    stable validation/build code, not the complete history of the
    project.

------------------------------------------------------------------------

## 2. System Model

The target architecture separates research, human adjudication,
authoritative decision data, validation, and generation.

``` text
                   ┌──────────────┐
                   │   Research   │
                   └──────┬───────┘
                          │ evidence
                          ▼
                   ┌──────────────┐
                   │ Human Review │
                   └──────┬───────┘
                          │ approved decision
                          ▼
                   ┌──────────────┐
                   │  decisions/  │
                   │ source of    │
                   │ truth        │
                   └──────┬───────┘
                          │
                ┌─────────┴─────────┐
                ▼                   ▼
          ┌──────────┐        ┌──────────┐
          │ Validate │        │ Generate │
          └────┬─────┘        └────┬─────┘
               │                   │
               │              ┌────┴────────────┐
               │              ▼                 ▼
               │          Mod output      Documentation
               │                         / glossary
               │
               ▼
       source/ reference checks
           (read-only)
```

The dependency direction is intentionally one-way:

``` text
source / research evidence
          ↓
     human decision
          ↓
      decisions/
          ↓
 validation / generation
          ↓
 generated outputs
```

Generated outputs must not become an independent source of translation
decisions.

------------------------------------------------------------------------

## 3. Authoritative Data

### 3.1 `decisions/`

`decisions/` is the authoritative store for approved translation
decisions.

A decision may contain information such as:

-   stable concept ID;
-   English reference term or text;
-   category;
-   gameplay-object distinction where necessary;
-   approved Japanese translation;
-   decision type;
-   human-readable reason;
-   notes and contextual restrictions;
-   one or more target String IDs;
-   target role;
-   explicit target text when a target requires wording different from
    the concept-level translation.

The current migrated decision set is stored in
`decisions/translations.json`.

The physical storage layout may change later. For example, decisions may
remain in one file or be divided by category or another stable boundary.

The architectural requirement is not "one record per file." The
requirement is:

> Approved decisions must remain canonical, uniquely identifiable,
> machine-validatable, and efficiently accessible without requiring
> unrelated historical pipeline data.

### 3.2 What does not belong in decision data

The following are implementation or historical verification metadata and
should not become required fields merely to reproduce the old pipeline:

-   source file hashes;
-   source line numbers;
-   patch-operation IDs;
-   before/after application state;
-   certificates;
-   authorization gates;
-   Phase numbers;
-   report hashes;
-   temporary review IDs;
-   planner-specific signatures;
-   migration-only provenance.

Such information may exist in historical or generated artifacts when
useful, but it is not part of the semantic translation decision unless
it conveys information required to understand the decision itself.

------------------------------------------------------------------------

## 4. Upstream Source Data

### 4.1 `source/` is read-only

`source/` contains upstream reference data collected from the game or
other project inputs.

It must never be used as the destination of the production build.

Production tools may read `source/` to:

-   resolve String IDs;
-   verify that expected targets exist;
-   inspect current Japanese or English values;
-   preserve required technical syntax;
-   construct a Mod payload;
-   compare upstream changes after a game update.

They must not modify, normalize, reformat, or patch `source/`.

### 4.2 Upstream updates

When the game changes, upstream source data may be refreshed from the
game installation.

The correct response to an upstream update is:

``` text
refresh source reference
        ↓
validate decisions against new source
        ↓
report missing/conflicting/changed targets
        ↓
human review only where necessary
        ↓
build new Mod
```

The system should not assume that a historical source hash must remain
unchanged forever.

Historical hashes may be useful evidence, but they are not the identity
of a translation decision.

------------------------------------------------------------------------

## 5. Validation

Validation is a permanent, reusable layer.

Routine validation must be implemented in the standard validator or
permanent test suite rather than in newly created one-off scripts.

### 5.1 Decision validation

The validator should check at least:

-   supported schema version;
-   required fields and types;
-   unique decision IDs;
-   valid categories and target roles;
-   valid String IDs;
-   duplicate target ownership;
-   conflicting final values;
-   internally consistent concept/target relationships;
-   explicit target text where required.

### 5.2 Source-aware validation

Where source data is available, validation should also check relevant
invariants such as:

-   target String IDs exist;
-   target resolution is unambiguous;
-   placeholders are preserved where required;
-   markup and formatting tokens are preserved where required;
-   escapes and technical syntax remain valid;
-   meaningful line-break/layout requirements are respected.

These checks should validate the final intended output, not recreate the
historical chain by which the decision was originally approved.

### 5.3 Fail closed

If the validator cannot safely determine the intended result, it must
fail and report the problem.

Validation must not silently:

-   guess a missing target;
-   resolve conflicting decisions;
-   weaken placeholder or markup checks;
-   invent a translation;
-   rewrite unrelated source text.

Human adjudication is required when semantic intent is unclear.

------------------------------------------------------------------------

## 6. Build

The builder consumes approved decisions and read-only upstream reference
data and produces a separate Mod.

Conceptually:

``` text
decisions/
    +
source/ (read-only)
    ↓
validate
    ↓
resolve approved target values
    ↓
construct Mod payload
    ↓
verify output
    ↓
dist/
```

### 6.1 Build properties

The steady-state builder should be:

-   deterministic;
-   non-destructive;
-   independent from historical Phase state;
-   independent from review ledgers and certificates;
-   safe to run repeatedly;
-   explicit about conflicts and unsupported input;
-   limited to approved targets.

The same decision data and same upstream input should produce the same
localization payload.

### 6.2 Delta Mod

The production artifact should be a Mod, not a modified copy of
`source/`.

Only files required by the game's Mod structure should be emitted.
Within those files, the builder should apply only approved target
changes while preserving unrelated upstream content as required by the
game format.

The builder must never install the Mod into the game automatically
unless installation is explicitly requested as a separate operation.

### 6.3 Output verification

Before publication, the build should verify that:

-   every intended target has the approved final value;
-   no unapproved target changed;
-   required technical tokens remain valid;
-   the output has the expected file structure;
-   source/reference inputs were not modified.

A generated manifest may record build metadata and hashes for
reproducibility. Such a manifest is an output, not an authority for
translation decisions.

------------------------------------------------------------------------

## 7. Generated Documentation and Glossary

`decisions/` and manually maintained glossary data must not become two
competing sources of truth.

Human-readable documentation should be generated from approved
decisions.

Possible generated views include:

-   English → Japanese glossary;
-   category-specific term lists;
-   decision/reason tables;
-   changed-translation summaries;
-   String ID mappings;
-   review-oriented Markdown.

The intended relationship is:

``` text
decisions/
    ↓
documentation generator
    ↓
glossary / Markdown / reports
```

Generated documentation may be committed to Git when doing so improves
GitHub readability and reviewability.

If committed, it must remain reproducible from authoritative decision
data and must not be manually edited as an independent translation
database.

------------------------------------------------------------------------

## 8. Research Layer

Research is intentionally separate from production.

Research may include:

-   AoK/AoC/HD/DE localization comparison;
-   legacy Japanese extraction;
-   English/Japanese inventory generation;
-   gameplay-object identification;
-   terminology audits;
-   duplicate-term analysis;
-   context analysis;
-   historical and linguistic investigation;
-   candidate generation;
-   web research;
-   game-data exploration.

Research tools may be specialized or complex when the research question
requires it.

Their output is evidence, not automatically an approved translation.

The transition from evidence to authority occurs only through human
adjudication and an update to `decisions/`.

------------------------------------------------------------------------

## 9. Legacy Pipeline

The repository currently contains substantial machinery created during
the historical Phase workflow.

This includes, among other things, systems for:

-   review ledgers;
-   occurrence bindings;
-   context overrides;
-   layout plans;
-   patch plans;
-   source-state reconstruction;
-   certificates and authorization;
-   source application;
-   Phase-specific validation;
-   historical reports.

These mechanisms were useful for establishing and verifying the migrated
decision set. They do not automatically belong in the steady-state
production architecture.

### 9.1 Migration classification

Legacy assets should be classified during cleanup into four broad
groups.

**Retain as reusable research infrastructure**

Tools that answer continuing research questions may remain, even if they
are not part of production.

Examples may include parsers, legacy extraction, comparative analysis,
gameplay inventory, and terminology analysis.

**Retain temporarily for migration verification**

Some old tools may be useful to prove that the new decision-driven
validator and builder reproduce the already approved result.

Once equivalence has been established and recorded, these tools should
not remain permanent production dependencies solely for historical
verification.

**Retire from production**

Phase-specific planners, certificates, authorization layers,
source-state reconstruction, and source-application mechanisms should be
removed from the production dependency graph when their required safety
properties have been transferred into the new validator/builder.

**Keep as historical documentation**

Phase reports and review artifacts may remain for provenance and future
investigation without being loaded or executed during ordinary work.

### 9.2 Do not delete safety properties

Simplification does not mean discarding useful safety checks.

The migration should distinguish between:

``` text
historical mechanism
```

and:

``` text
general safety property
```

For example, a complex historical patch certificate may be retired while
the general requirements it protected---unique targets, expected final
values, token preservation, and no unrelated modifications---remain
enforced by the new validator and builder.

------------------------------------------------------------------------

## 10. Production vs. Research Dependencies

A core architectural rule is:

> Production may depend on stable parsing and validation primitives, but
> it must not depend on the historical research process that produced an
> approved decision.

For example:

``` text
Good:

decisions
   ↓
validator ──→ parser
   ↓
builder

Acceptable research:

source
  ↓
legacy comparison
  ↓
term audit
  ↓
human decision
  ↓
decisions

Avoid:

decisions
  ↓
old review ledger
  ↓
Phase planner
  ↓
certificate
  ↓
source-state reconstruction
  ↓
authorization gate
  ↓
builder
```

The final chain adds no semantic value once the approved decision itself
is canonical.

------------------------------------------------------------------------

## 11. Efficient Context and Token Use

The repository should support narrow, task-specific work.

For an ordinary translation change, an agent should normally need only:

-   the relevant decision record or records;
-   the relevant source String IDs when verification is needed;
-   translation policy;
-   stable validator/build interfaces.

It should not normally need:

-   all historical Phase documents;
-   all review ledgers;
-   all reports;
-   every decision in the project;
-   old certificates;
-   source-state histories;
-   repository-wide recomputation.

### 11.1 Decision storage

If the canonical decision file becomes too large for efficient targeted
access, it may be split along stable boundaries such as category.

Any split must preserve:

-   stable decision IDs;
-   one logical source of truth;
-   deterministic loading;
-   global duplicate/conflict validation.

Storage optimization must not create multiple manually synchronized
databases.

### 11.2 Generated views

Large human-readable summaries should be generated rather than embedded
into the production decision schema solely for convenience.

This keeps authoritative records compact while preserving good GitHub
readability.

------------------------------------------------------------------------

## 12. Testing Strategy

Tests should protect reusable behavior rather than historical Phase
procedure.

Permanent tests should focus on:

-   decision schema validation;
-   duplicate/conflict detection;
-   parsing correctness;
-   placeholder/markup/token preservation;
-   deterministic target resolution;
-   deterministic build output;
-   source immutability;
-   absence of unapproved output changes;
-   generated documentation consistency.

Migration-specific equivalence tests may temporarily compare the new
system against the old approved output.

After migration is complete, tests whose only purpose is to reproduce
obsolete Phase internals should be archived or removed unless they
continue to protect a real invariant.

------------------------------------------------------------------------

## 13. Repository Roles

The target meaning of the major repository areas is:

``` text
README.md
    Project purpose, user-facing overview, translation principles.

AGENTS.md
    Short operational rules for coding agents.

docs/architecture.md
    Technical architecture and dependency rules.

docs/localization-policy.md
    Detailed linguistic/localization policy.

decisions/
    Authoritative human-approved translation decisions.

source/
    Read-only upstream reference data.

tools/
    Stable validation/build tools plus clearly separated research utilities.

tests/
    Permanent tests for current architecture and temporary migration tests.

glossary/
    Generated human-readable terminology views where retained.

reports/
    Generated analysis/research outputs where applicable.

reviews/
    Historical review/migration evidence; not the steady-state source of truth.

dist/
    Generated Mod/build artifacts.
```

The exact directory structure may evolve, but these responsibility
boundaries should remain clear.

------------------------------------------------------------------------

## 14. Normal Workflow

### 14.1 Ordinary translation change

``` text
Identify translation issue
        ↓
Research only what is necessary
        ↓
Human adjudication
        ↓
Update decisions/
        ↓
Run standard validation
        ↓
Build Mod and generated documentation
        ↓
Review diff/output
        ↓
Verify in game when needed
```

No new production code should normally be required.

### 14.2 Game update

``` text
Refresh upstream reference data
        ↓
Run standard validation
        ↓
Inspect only reported incompatibilities
        ↓
Update decisions if human judgment is required
        ↓
Build
```

### 14.3 Architecture change

Repository-wide analysis, migration scripts, and broader audits are
appropriate when the architecture itself is being changed.

They are exceptional maintenance operations, not the default translation
workflow.

------------------------------------------------------------------------

## 15. Migration Target

The current repository is in transition from the historical Phase
pipeline to the decision-driven architecture defined here.

Migration should proceed incrementally:

``` text
1. Preserve approved decisions
2. Define the canonical decision schema
3. Implement one standard validator
4. Implement one decision-driven Mod builder
5. Generate glossary/documentation from decisions
6. Prove equivalence with the approved historical result
7. Remove old machinery from the production dependency graph
8. Classify and archive/retain research and historical assets
9. Simplify commands and documentation
```

The migration must not require changing approved translations merely to
fit a new implementation.

------------------------------------------------------------------------

## 16. Architectural Invariants

The following invariants define the intended steady state:

1.  `decisions/` is the sole manually maintained authority for approved
    translation decisions.
2.  `source/` is read-only.
3.  Production creates a separate Mod.
4.  Generated glossary/report data does not compete with `decisions/`.
5.  Routine translation changes are data changes, not code changes.
6.  Standard validation replaces recurring ad-hoc audit scripts.
7.  Production does not require historical Phase state.
8.  Research complexity does not leak into routine production.
9.  Human adjudication remains the authority for semantic translation
    choices.
10. Technical integrity checks fail closed.
11. Build output is deterministic and limited to approved targets.
12. Agents can work from narrow relevant context instead of loading the
    complete project history.

The desired steady-state workflow is therefore:

``` text
new translation decision
        ↓
update canonical data
        ↓
validate
        ↓
build
```

not:

``` text
new translation decision
        ↓
new Python
        ↓
new ledger
        ↓
new certificate
        ↓
new pipeline stage
        ↓
build
```

------------------------------------------------------------------------

# アーキテクチャ

この文書は、AoE2:DE
日本語ローカライズプロジェクトの目標アーキテクチャを定義します。

ここで定義するのは過去のPhase
pipelineそのものではなく、今後維持していく定常的なシステムです。移行期間中は旧ツールや旧文書がリポジトリに残る場合がありますが、それらが将来のProduction
architectureを定義するわけではありません。

プロジェクトの目的と翻訳方針の概要は
`README.md`、AIエージェント向けの簡潔な作業規則は `AGENTS.md`
を参照してください。

------------------------------------------------------------------------

## 1. 設計目標

目標とするProduction workflowは単純です。

``` text
翻訳判断
   ↓
decision dataを変更
   ↓
validate
   ↓
build
   ↓
Mod + 自動生成文書
```

基本原則は次の通りです。

1.  **人間の裁定を最終的な権威とする。**
    Researchや自動処理は判断材料を提供しますが、人間が承認した裁定を暗黙に上書きしません。

2.  **翻訳知識の正本を一つにする。**
    採用訳、判断理由、concept境界、適用対象は `decisions/`
    に保存します。

3.  **ゲーム由来データはread-onlyとする。** `source/`
    は参照入力であり、Production buildの書き込み先ではありません。

4.  **通常の翻訳変更をdata-onlyにする。**
    一般的な訳語の追加・変更のために、新しいPython、ledger、certificate、pipeline
    stageを作る必要がない構造にします。

5.  **ProductionをResearchより小さくする。**
    Researchは必要に応じて複雑でも構いません。しかし、既に決まった翻訳からModを作る処理は単純かつ決定論的であるべきです。

6.  **生成物を手動管理しない。** glossary、report、manifest、Mod
    payloadは正本から導出される成果物です。

7.  **人間とAIの双方にとって省コンテキストな構造にする。**
    通常作業では関係する裁定と安定したvalidator/builderだけを読めば済むようにします。

------------------------------------------------------------------------

## 2. システムモデル

Research、人間の裁定、正本、Validation、Generationを明確に分離します。

``` text
Research
   ↓ evidence
Human Review
   ↓ approved decision
decisions/  ← 正本
   ↓
 ┌─┴────────────┐
 ↓              ↓
Validate      Generate
 ↓              ↓
source/       Mod + documentation
(read-only)
```

依存方向は原則として一方向です。

``` text
source / research evidence
          ↓
       人間の裁定
          ↓
      decisions/
          ↓
 validation / generation
          ↓
       生成物
```

生成物から翻訳裁定を逆生成して、別の正本として扱ってはいけません。

------------------------------------------------------------------------

## 3. 翻訳裁定の正本

### 3.1 `decisions/`

`decisions/` は、人間が承認した翻訳裁定の唯一の正本です。

裁定には必要に応じて、安定したconcept ID、英語参照名、category、gameplay
objectの区別、採用訳、裁定種別、判断理由、context上の注意、String
ID、target role、target固有の明示文などを保持します。

現在の移行済み裁定は `decisions/translations.json` に保存されています。

将来、ファイルをcategory等で分割することはできます。ただし「1裁定1ファイル」はarchitecture上の必須条件ではありません。

必要なのは、

> 裁定が一意で、機械検証可能で、必要な部分だけ効率よく参照でき、旧pipeline
> metadataを読まなくても意味が完結すること

です。

### 3.2 正本に不要なもの

source hash、source line、patch operation
ID、適用前後state、certificate、authorization、Phase番号、report
hash、planner
signature等は、原則として翻訳そのものではなく実装・履歴metadataです。

歴史的証拠や生成manifestとして保存することはできますが、過去pipelineを再現するためだけにdecision
schemaの必須情報にはしません。

------------------------------------------------------------------------

## 4. `source/`

`source/` はゲーム等から取得した上流参照データです。

Production toolは、String IDの存在確認、現在値の確認、technical
syntaxの検査、Mod payload構築等のために読み取ることができます。

ただし `source/`
自体を変更、normalize、reformat、patchしてはいけません。

ゲーム更新時は、

``` text
sourceを更新
   ↓
decisionsとの互換性をvalidate
   ↓
問題があるtargetだけ報告
   ↓
必要なものだけ人間が再裁定
   ↓
Modを再build
```

とします。

過去のsource
hashは証拠にはなりますが、翻訳裁定そのもののidentityではありません。

------------------------------------------------------------------------

## 5. Validation

Validationは恒常的な共通機能として実装します。

毎回新しい検査Pythonを書くのではなく、繰り返し必要になる検査は標準validatorまたは恒久test
suiteへ入れます。

最低限、schema、必須field、decision ID、category、target role、String
ID、target重複、最終値のconflict、conceptとtargetの整合性を検査します。

sourceを利用できる場合は、targetの存在、placeholder、markup、formatting
token、escape、technical syntax、意味のある改行・layout等も検査します。

重要なのは、**最終的に出力しようとしている値が安全かを検査すること**です。

その裁定が過去にどのPhase、ledger、certificateを経由して成立したかをProduction時に再証明することではありません。

安全に判断できない場合はfail
closedとし、推測によるtarget選択、conflict解消、translation生成、検査弱体化は行いません。

------------------------------------------------------------------------

## 6. Build

builderは、

``` text
decisions/
    +
source/ (read-only)
    ↓
validate
    ↓
承認済みtargetを解決
    ↓
Mod payload構築
    ↓
出力検証
    ↓
dist/
```

という構造にします。

builderは決定論的、非破壊的、反復可能で、旧Phase state、review
ledger、certificateに依存しないことを目標とします。

Production成果物は `source/` の変更版ではなく、別個のModです。

builderは承認済みtargetだけを変更し、ゲーム形式上必要な範囲でその他の内容を保持します。

ゲームへの自動installはbuildとは分離し、明示的に要求された場合だけ別操作として扱います。

出力前には、全targetが承認値になっていること、未承認targetが変化していないこと、technical
tokenが有効であること、出力構造が正しいこと、sourceが変更されていないことを検証します。

------------------------------------------------------------------------

## 7. Glossaryと自動生成文書

`decisions/` と手動glossaryを二重管理しません。

glossary、category別一覧、判断理由一覧、String ID対応表、変更一覧等は
`decisions/` から生成します。

``` text
decisions/
   ↓
documentation generator
   ↓
glossary / Markdown / reports
```

GitHub上の可読性を高めるため生成Markdownをcommitすることはできます。

ただし、それらは常に再生成可能な成果物であり、独立した翻訳DBとして手動編集しません。

------------------------------------------------------------------------

## 8. Research

ResearchはProductionから分離します。

AoK/AoC/HD/DE比較、旧日本語訳抽出、inventory、gameplay object解析、term
audit、duplicate解析、context調査、歴史・言語調査、web
research等はResearchに属します。

Research toolは必要なら複雑でも構いません。

ただしResearchの結果はevidenceであり、自動的に正式翻訳にはなりません。

正式なauthorityへ変わるのは、

``` text
evidence
   ↓
人間の裁定
   ↓
decisions/
```

の時点です。

------------------------------------------------------------------------

## 9. 旧Phase pipeline

現在のrepositoryには、review ledger、occurrence binding、context
override、layout plan、patch plan、source-state
reconstruction、certificate、authorization、source
apply、Phase固有validation等の仕組みが残っています。

これらは既存裁定を確立・検証する過程では有用でしたが、そのこと自体は将来のProduction
dependencyであり続ける理由にはなりません。

整理時には次の4分類を使います。

**Research infrastructureとして残す**

parser、legacy extraction、比較分析、gameplay inventory、term
analysis等、今後もResearchに利用できるもの。

**Migration verification用に一時保持する**

新validator/builderが既存の承認済み結果を正しく再現することを証明するために必要なもの。

**Productionから退役させる**

Phase固有planner、certificate、authorization、source-state
reconstruction、source
application等。これらが守っていた一般的な安全性を新validator/builderへ移した後、Production
dependencyから外します。

**Historical documentationとして残す**

旧Phase文書、review、report等。将来調査のため残してもよいですが、通常作業では読み込みません。

重要なのは、旧機構を消すことと、安全性を消すことを混同しないことです。

たとえばcertificateという歴史的機構を退役させても、

-   targetの一意性
-   expected final value
-   technical token preservation
-   unrelated modificationの禁止

といった一般的安全性は新システムに残します。

------------------------------------------------------------------------

## 10. ProductionとResearchの依存関係

中心原則は、

> Productionは安定したparserやvalidator
> primitiveには依存してよいが、承認済み裁定を生み出した過去のResearch
> processには依存しない

というものです。

望ましい構造は、

``` text
decisions
   ↓
validator ──→ parser
   ↓
builder
```

です。

Research側は、

``` text
source
   ↓
legacy comparison
   ↓
term audit
   ↓
human decision
   ↓
decisions
```

のように独立して構いません。

避けるべきなのは、

``` text
decisions
   ↓
old review ledger
   ↓
Phase planner
   ↓
certificate
   ↓
source-state reconstruction
   ↓
authorization gate
   ↓
builder
```

という依存です。

------------------------------------------------------------------------

## 11. コンテキスト・トークン効率

通常の翻訳変更でAIエージェントが必要とする情報は原則として、

-   関係するdecision record
-   必要なら該当String IDのsource
-   localization policy
-   validator/build interface

だけにします。

旧Phase全文書、全review
ledger、全report、全decision、certificate、source-state
history等を毎回読む構造にはしません。

`translations.json`
が将来大きくなり、部分参照の効率が悪くなった場合はcategory等の安定した境界で分割できます。

ただし、分割によって複数の手動正本を作ってはいけません。

------------------------------------------------------------------------

## 12. Test方針

恒久testは、過去のPhase手順ではなく、現在も意味のある性質を保護します。

主な対象は、

-   decision schema
-   duplicate/conflict detection
-   parser
-   placeholder/markup/token preservation
-   target resolution
-   deterministic build
-   source immutability
-   unapproved changeの禁止
-   generated documentation consistency

です。

移行期間中は旧pipelineとのequivalence testを置いても構いません。

移行完了後、旧Phase内部の再現だけを目的とするtestは、現在の安全性を保護していない限りarchiveまたは削除対象です。

------------------------------------------------------------------------

## 13. Repository各領域の責任

``` text
README.md
    プロジェクト目的、利用者向け概要、翻訳原則。

AGENTS.md
    AI coding agent向けの短い作業規則。

docs/architecture.md
    技術architectureとdependency rule。

docs/localization-policy.md
    詳細な翻訳・言語方針。

decisions/
    人間が承認した翻訳裁定の正本。

source/
    read-onlyの上流参照データ。

tools/
    安定したvalidator/builderと、明確に分離されたResearch utility。

tests/
    現architectureの恒久testと、移行期間限定test。

glossary/
    必要に応じて保持する自動生成の可読用語集。

reports/
    Research/analysisの生成結果。

reviews/
    歴史的review・migration evidence。定常Productionの正本ではない。

dist/
    生成されたMod/build成果物。
```

具体的なdirectory layoutは今後変えられますが、責任境界は維持します。

------------------------------------------------------------------------

## 14. 通常workflow

通常の翻訳変更は、

``` text
問題を特定
   ↓
必要な範囲だけResearch
   ↓
人間が裁定
   ↓
decisions/を変更
   ↓
標準validation
   ↓
Mod + 文書をbuild
   ↓
diff/output確認
   ↓
必要ならゲーム内確認
```

です。

通常、新しいProduction codeは不要です。

ゲーム更新時は、

``` text
source更新
   ↓
標準validation
   ↓
非互換だけ確認
   ↓
必要なものだけ再裁定
   ↓
build
```

とします。

repository全体の解析やmigration
scriptはarchitecture変更時には適切ですが、通常の翻訳作業では例外です。

------------------------------------------------------------------------

## 15. Migration目標

現在は旧Phase pipelineからdecision-driven architectureへの移行期間です。

推奨順序は、

``` text
1. 承認済み裁定を保存
2. canonical decision schemaを確定
3. 標準validatorを1つ実装
4. decision-driven Mod builderを1つ実装
5. decisionsからglossary/documentationを生成
6. 旧承認済み結果とのequivalenceを一度証明
7. 旧機構をProduction dependencyから除去
8. Research/歴史資産を分類・整理
9. commandとdocumentationを簡素化
```

です。

新実装へ合わせるためだけに既存の承認済み翻訳を変更してはいけません。

------------------------------------------------------------------------

## 16. Architecture上の不変条件

最終的に次を維持します。

1.  `decisions/` が人間管理する翻訳裁定の唯一の正本である。
2.  `source/` はread-onlyである。
3.  Productionは別個のModを生成する。
4.  glossary/reportは`decisions/`と競合する正本にならない。
5.  通常の翻訳変更はcode changeではなくdata changeである。
6.  毎回のad-hoc scriptではなく標準validationを使う。
7.  Productionは旧Phase stateを必要としない。
8.  Researchの複雑さを日常Productionへ持ち込まない。
9.  semanticな翻訳判断は人間の裁定をauthorityとする。
10. technical integrity checkはfail closedとする。
11. buildは決定論的で、承認targetだけを変更する。
12. AIはproject全履歴ではなく、必要な狭いcontextで作業できる。

目標とする定常workflowは、

``` text
新しい翻訳裁定
    ↓
canonical data更新
    ↓
validate
    ↓
build
```

です。

次のようなworkflowへ戻さないことが重要です。

``` text
新しい翻訳裁定
    ↓
新しいPython
    ↓
新しいledger
    ↓
新しいcertificate
    ↓
新しいpipeline stage
    ↓
build
```
