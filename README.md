# AoE2 Japanese Localization

A comprehensive refinement project for the Japanese localization of **Age of Empires II: Definitive Edition**.

This project aims to improve the consistency, accuracy, readability, and overall quality of the Japanese localization while respecting the terminology and localization style established by the original Japanese releases of **Age of Empires II: The Age of Kings (1999)** and **The Conquerors (2000)**.

## Goals

The Japanese localization of Age of Empires II has changed considerably over its long history.

Some terminology established in the original Japanese releases was later replaced despite the underlying game concept remaining unchanged. At the same time, newer expansions contain inconsistent terminology, awkward translations, abbreviations, and other localization issues.

This project aims to systematically review these strings and produce a coherent Japanese localization for the modern game.

The general principles are:

- Preserve established terminology from the original Japanese releases of Age of Empires II where appropriate.
- Use official AoK/AoC Japanese terminology as the default baseline; record specific exceptions before preferring changed DE terminology.
- Correct mistranslations, omissions, inconsistent terminology, typographical errors, and malformed strings.
- Improve awkward or unclear Japanese while preserving the meaning of the English source.
- Apply the localization conventions of classic AoE II consistently to content introduced in later expansions.
- Research historical terminology where a direct translation is insufficient.
- Respect intentionally distinct terminology used by separate game systems such as **Chronicles**, rather than mechanically forcing all content into the standard AoE II vocabulary.
- Preserve gameplay-relevant information, formatting codes, placeholders, and other technical elements of the original strings.

The goal is **not** to mechanically revert every string to an older translation. The original localization serves as an important stylistic and terminological foundation, but accuracy, context, and the current game design must also be considered.

## Reference Sources

During development, the project may compare localization data from several generations of Age of Empires II:

1. Age of Empires II: The Age of Kings (1999)
2. Age of Empires II: The Conquerors (2000)
3. Age of Empires II HD Edition (2013)
4. Age of Empires II: Definitive Edition
5. Current English localization of Definitive Edition

These sources allow us to trace how terminology has changed over time and distinguish intentional improvements from unnecessary or inconsistent changes.

## Repository Policy

Original localization files distributed with Age of Empires II are **not intended to be distributed through this repository**.

Local copies may be placed under `source/` for development and comparison purposes. The directory is excluded from Git tracking.

The repository instead contains materials created for this project, such as:

- localization overrides
- terminology and glossaries
- translation policies
- analysis and validation tools
- build tools
- documentation

Users and contributors must obtain original game data from their own legitimate installation where required.

## Project Status

Phase 0 parsing and comparison tools are available (Python 3.10+, no external dependencies).
See [Phase 0 documentation](docs/phase0.md) for source-format findings, CLI usage, comparison definitions, and tests.

Phase 0.5 also extracts AoK/AoC Japanese RT_STRING resources from local DLLs without executing them.
Legacy datasets join the existing search and String ID views automatically when present; no external dependencies are required.
See [Legacy extraction documentation](docs/phase0.5.md) for counts, duplicate handling, and limitations.

Phase 1A adds an evidence-linked gameplay name inventory and audit reports, preserving source ambiguity and separating Chronicles contexts.
See [Name inventory documentation](docs/phase1a.md) for classification limits, review flags, and TSV export.

Phase 1B preparation documents the [localization adoption policy](docs/localization-policy.md).
`python -m tools.localization restoration --output-dir reports/phase1b` generates evidence-linked proposals without changing translations.

Phase 1B adds [unapproved editorial review sheets](docs/phase1b.md), linked button/help evidence, and separate ID-reuse findings via `python -m tools.localization adoption --output-dir reports/phase1b/review`.

Explicit human adjudications are retained in [reviews/](reviews/README.md) and take precedence when reports are regenerated. Use a new output directory, such as `reports/phase1b/human-review-next`, to preserve earlier reports.

Phase 1C adds a [read-only application scope audit](docs/phase1c.md): `python -m tools.localization scope-audit` and `scope-review --class required --limit 10`. It reports name/button/help occurrences and conflicts without applying translations.

Phase 1D adds an [occurrence-bound dry-run patch plan](docs/phase1d.md): `python -m tools.localization patch-plan`. It preserves technical syntax, merges identical requests, and blocks unsafe edits without writing translations.

The [blocked audit](docs/phase1d-blocked-audit.md) proposes conservative layout-preserving replacements via `python -m tools.localization blocked-audit`, without applying or altering the existing plan.

The [verified Mod payload generator](docs/phase1e-mod-build.md) builds an independent local artifact via `python -m tools.localization mod-build`, with `--dry-run` and `--verify-only` modes. It never modifies source or installs into the game.

Phase 1F creates a [local display-test delta package](docs/phase1f-local-mod.md) containing only the 346 changed IDs via `python -m tools.localization mod-package`, with a [game verification checklist](docs/phase1f-checklist.md). Installation and in-game checks remain manual.

```powershell
python -m tools.localization stats
python -m tools.localization legacy-stats
python -m tools.localization show 5131
python -m tools.localization names --primary --family core --review
python -m tools.localization compare --category jp_only_changed --limit 20 --values
python -m unittest discover -v
```

This project is currently in its early development stage.

The initial work focuses on:

- establishing the translation policy
- comparing HD and Definitive Edition localization data
- reconstructing legacy Japanese terminology
- identifying suspicious or inconsistent strings
- developing tools for String ID based comparison and validation

The final output is intended to be distributed as an **Age of Empires II: Definitive Edition localization mod**.

## Disclaimer

This is an unofficial fan project and is not affiliated with or endorsed by Microsoft, Xbox Game Studios, World's Edge, or Forgotten Empires.

Age of Empires and related names and assets are trademarks and/or copyrighted materials of their respective owners.

---

# AoE2 日本語ローカライズ

**Age of Empires II: Definitive Edition** の日本語ローカライズを包括的に改善するプロジェクトです。

本プロジェクトでは、**Age of Empires II: The Age of Kings（1999）**および**The Conquerors（2000）**の日本語版で確立された用語や翻訳スタイルを尊重しつつ、現行Definitive Editionの日本語について、一貫性・正確性・可読性・翻訳品質の向上を目指します。

## 目的

Age of Empires IIの日本語ローカライズは、長い歴史の中で大きく変化してきました。

旧日本語版で定着していた用語の中には、ゲーム上の概念自体には変化がないにもかかわらず、後のバージョンで別の訳語へ変更されたものがあります。一方、近年追加されたコンテンツには、既存用語との不整合、不自然な翻訳、省略表現、その他のローカライズ上の問題も見られます。

本プロジェクトでは、これらを体系的に検証し、現代のAoE2全体で一貫性のある日本語ローカライズを構築することを目指します。

基本方針は以下の通りです。

- 適切な場合、AoE2旧日本語版で確立された用語を維持する。
- 後年の変更に明確な利点がない場合、定着した旧来の用語への復元を検討する。
- 誤訳、訳抜け、用語の不統一、誤字、壊れた文字列などを修正する。
- 英語原文の意味を維持しながら、不自然・不明瞭な日本語を改善する。
- 後発の拡張コンテンツについても、可能な限り旧来のAoE2日本語版の命名規則との整合性を確保する。
- 単純な直訳では不十分な場合、歴史的な用語や背景を調査する。
- **Chronicles**など独自のゲーム体系・命名体系を持つコンテンツについては、その意図的な差異を尊重し、通常のAoE2用語へ機械的に統一しない。
- ゲーム上必要な情報、書式、プレースホルダーなどの技術的要素を維持する。

本プロジェクトの目的は、**すべての文字列を機械的に旧訳へ戻すことではありません**。

旧日本語版を重要な用語・スタイル上の基礎としながら、翻訳の正確性、文脈、現在のゲーム仕様についても考慮します。

## 参照資料

開発時には、AoE2の複数世代のローカライズデータを比較します。

1. Age of Empires II: The Age of Kings（1999）
2. Age of Empires II: The Conquerors（2000）
3. Age of Empires II HD Edition（2013）
4. Age of Empires II: Definitive Edition
5. Definitive Editionの現行英語版

これらを比較することで、用語がどの時点で変更されたのかを追跡し、意図的な改善と、不必要または不整合な変更を区別します。

## リポジトリの方針

Age of Empires IIに含まれる**公式ローカライズファイルそのものは、本リポジトリでは配布しません**。

開発・比較のため、各自の環境にある公式ファイルを `source/` 以下へ配置することがありますが、このディレクトリはGitの追跡対象外とします。

GitHubで管理するのは、原則として本プロジェクトが作成した以下のようなデータです。

- ローカライズ修正差分
- 用語集
- 翻訳方針
- 解析・検証ツール
- ビルドツール
- ドキュメント

公式ゲームデータが必要な場合は、各自が正規に入手したゲームから取得してください。

## 現在の状況

本プロジェクトは現在、開発初期段階です。

まず以下の作業から開始します。

- 翻訳方針の策定
- HD版とDefinitive Editionのローカライズ比較
- 旧日本語版における用語体系の整理
- 不自然・不整合な文字列の検出
- String ID単位で比較・検証するためのツール開発

最終的な成果物は、**Age of Empires II: Definitive Edition用の日本語ローカライズMod**として公開することを想定しています。

## 免責事項

本プロジェクトは非公式のファンプロジェクトであり、Microsoft、Xbox Game Studios、World's Edge、Forgotten Empiresその他の権利者とは関係ありません。

Age of Empiresおよび関連する名称・素材の権利は、それぞれの権利者に帰属します。
