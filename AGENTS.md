# AGENTS.md

## Project Purpose

This repository develops a refined Japanese localization for Age of Empires II: Definitive Edition.

The project is not a generic machine-translation project.

Its objective is to construct a coherent Japanese localization based on:

- the terminology established by the Japanese releases of Age of Empires II: The Age of Kings (1999) and The Conquerors (2000);
- the historical evolution of the localization through HD Edition;
- the meaning and current gameplay represented by the English Definitive Edition strings;
- deliberate editorial review.

## Core Principles

### 1. Legacy terminology is an important baseline

Terminology established by the original Japanese AoE II releases should generally be preferred when the underlying concept has not changed.

Do not assume that newer terminology is automatically preferable.

However, do not mechanically restore old translations when they are demonstrably incorrect or unsuitable for the current game.

### 2. English DE strings are the semantic reference

When determining the current meaning of a string, use the current English Definitive Edition localization as the primary semantic reference.

Older Japanese strings are references for terminology and localization style, not authoritative descriptions of current gameplay.

### 3. HD Edition is a historical reference

HD localization data is primarily used to trace changes between classic AoE II and Definitive Edition.

Do not treat HD Japanese terminology as automatically authoritative.

### 4. New content should fit the established localization system

Units, buildings, technologies, civilizations, and other concepts introduced after the classic releases should be reviewed for consistency with established Japanese AoE II terminology.

Do not simply transliterate or directly translate new terminology without considering existing naming conventions.

### 5. Chronicles is a separate localization context

Chronicles content intentionally uses concepts and terminology that may differ from standard AoE II.

Do not mechanically normalize Chronicles terminology to standard AoE II terminology.

For example, intentionally distinct religious, military, political, or cultural terminology may need to remain distinct.

Context-specific glossaries and rules may be introduced for Chronicles.

### 6. Preserve technical syntax

Never alter placeholders, markup, formatting tokens, escape sequences, or other technical syntax unless the task specifically requires it and the change has been validated.

Examples include:

- `%s`
- `%d`
- formatting tags
- escaped characters
- String IDs

Validation tools should detect accidental changes to these elements.

## Source Data Policy

The `source/` directory contains copyrighted localization data copied from locally installed versions of Age of Empires II.

Treat everything under `source/` as **read-only reference data**.

Agents MUST NOT:

- modify source files;
- reformat source files;
- rename source files unless explicitly instructed;
- commit source files;
- copy substantial portions of source localization into tracked files;
- generate commits that include original game localization files.

Analysis tools may read files under `source/`.

Generated comparison data must be designed to avoid unnecessarily reproducing the complete original localization.

## Translation Changes

Do not make large-scale translation changes automatically.

Translation proposals should be reviewable and traceable.

Where practical, record:

- String ID
- current English
- current Japanese
- proposed Japanese
- category of change
- source/basis
- notes or rationale
- review status

Useful change categories may include:

- `legacy_restoration`
- `terminology_consistency`
- `translation_fix`
- `qa_fix`
- `style_refinement`
- `new_localization`
- `chronicles_specific`

The schema may evolve as the project develops.

## Historical Terminology

Do not invent historical Japanese terminology merely because a literal translation sounds plausible.

When a name depends on historical terminology, flag uncertain cases for research or human review.

Prefer established Japanese historical terminology where appropriate.

## Automation Philosophy

Automation should assist editorial work, not replace it.

Good uses of automation include:

- parsing String IDs;
- comparing versions;
- detecting changed strings;
- detecting suspiciously short or malformed translations;
- detecting untranslated English;
- identifying terminology inconsistencies;
- checking placeholders and formatting;
- generating review reports;
- building mod output.

Automated tools should not silently decide contested translation questions.

## Repository Structure

Expected high-level structure:

```text
docs/           Project documentation and translation policies
glossary/       Terminology and context-specific glossaries
source/         Local read-only source data; excluded from Git
tools/          Parsing, analysis, validation, and build tools
translations/   Project-owned translation overrides and review data
dist/           Generated mod output; normally excluded from Git
```

## Development Rules

Before implementing a tool:

1. Inspect the actual source format.
2. Avoid assumptions about String ID ranges or file layout.
3. Preserve source files exactly.
4. Prefer deterministic output.
5. Report malformed or duplicate input rather than silently discarding it.
6. Keep parsing, analysis, translation data, and mod generation logically separate.
7. Add documentation when introducing a new data format or workflow.

When requirements are ambiguous, prefer producing analysis or a report rather than modifying translation data.