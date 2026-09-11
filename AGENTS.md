# AGENTS.md

## Project Rules

This repository develops a Japanese localization Mod for **Age of
Empires II: Definitive Edition**.

For project goals and translation policy, see `README.md`. For
architecture details and rationale, see `docs/architecture.md`.

Follow explicit user instructions first, then this file.

## Architecture

Keep these responsibilities separate:

``` text
Research
   ↓
Human decision
   ↓
decisions/
   ↓
validate
   ↓
build
   ├── Mod
   └── generated documentation
```

-   `decisions/` is the authoritative source for approved translation
    decisions.
-   `source/` is upstream reference data and is **read-only**.
-   `glossary/`, `reports/`, and `dist/` are generated or derived data,
    not translation sources of truth.
-   `reviews/` and the old Phase pipeline are legacy/migration material
    unless explicitly needed.

Do not modify, patch, reformat, or normalize files under `source/`.
Production output must be generated separately as a Mod.

## Translation Decisions

Human-approved decisions in `decisions/` are authoritative.

Research and automation may provide evidence but must not silently
override an approved decision.

If new evidence conflicts with an existing decision, report the conflict
for human adjudication.

Preserve required technical elements such as String IDs, placeholders,
formatting tokens, markup, escapes, and meaningful line breaks.

## Development Rules

Routine translation work should be:

``` text
decision data change → validate → build
```

Adding or revising a normal translation must not require new Python
code.

Do not create:

-   ad-hoc validation scripts for routine checks;
-   new ledgers, certificates, authorization layers, or intermediate
    formats without a genuine architectural need;
-   new legacy-pipeline machinery merely because similar machinery
    already exists.

Reusable checks belong in the standard validator or permanent test
suite.

Research tools may be complex when necessary. Production should remain
small, deterministic, and independent from unnecessary research
machinery.

Do not make the future build depend on legacy ledgers, certificates,
hashes, or Phase state solely to reproduce historical verification.

## Efficient Agent Work

Prefer the smallest relevant context and change set.

-   Read only the files needed for the current task first.
-   Do not load historical Phase documentation unless the task requires
    it.
-   Do not regenerate large reports unless required.
-   Do not recompute research already captured in an approved decision
    unless that decision is being reconsidered.
-   Prefer existing stable commands over bespoke Python snippets.
-   Do not rewrite unrelated files or decisions.
-   Do not commit, push, publish, or modify an external game
    installation unless explicitly instructed.

Repository-wide analysis is appropriate for architecture work,
migrations, and broad audits, but should not be the default for ordinary
translation changes.

## Legacy Pipeline

Historical Phase code and documentation remain useful for research and
migration verification.

Do not extend the legacy production chain---review ledgers, occurrence
bindings, patch plans, certificates, authorization gates, source-state
reconstruction, or source application---unless the user explicitly
requests legacy maintenance or an approved migration step requires it.

One-time migration verification must not become a permanent production
dependency.

## Stop Conditions

Stop and report the issue instead of inventing additional pipeline
machinery if:

-   the task would require modifying `source/`;
-   approved decisions conflict and the intended resolution is unclear;
-   the decision schema cannot represent the requested translation;
-   validation would need to be weakened or bypassed;
-   a translation requires unsupported historical or linguistic
    judgment;
-   generated data would become a second manually maintained source of
    truth;
-   substantial unrelated architecture work becomes necessary.

## Default Workflow

For ordinary translation work:

``` text
Research only what is needed
        ↓
Human adjudication
        ↓
Update decisions/
        ↓
Standard validation
        ↓
Build
        ↓
Review generated diff
        ↓
Game verification when needed
```

The desired steady state is:

**new translation decision → data change → validate → build**

not:

**new translation decision → new Python → new ledger → new certificate →
new pipeline**
