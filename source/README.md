# Source Localization Data

This directory is used for local reference copies of original Age of Empires II localization files.

The files are used for comparison and analysis during development and are **not part of this repository**.

Original game localization files must not be committed.

## Suggested Layout

```text
source/
├── hd/
│   ├── en/
│   │   └── key-value-strings-utf8.txt
│   └── jp/
│       └── key-value-strings-utf8.txt
│
└── de/
    ├── en/
    │   └── key-value/
    │       └── ...
    └── jp/
        └── key-value/
            └── ...
```

The HD source files are obtained from a local installation of Age of Empires II HD Edition.

The DE source files are obtained from a local installation of Age of Empires II: Definitive Edition.

For example, Steam installations may contain localization data under paths similar to:

```text
Age2HD/resources/en/strings/
Age2HD/resources/jp/strings/

AoE2DE/resources/en/strings/
AoE2DE/resources/jp/strings/
```

Exact installation paths vary between systems.

## Rules

Files placed here are reference data only.

- Do not modify original source files.
- Do not commit original localization files.
- Do not use this directory for project-owned translations.
- Tools may read these files for parsing, comparison, and validation.
- Project-owned localization changes belong under `translations/`.

The repository's `.gitignore` is expected to exclude source data while allowing this README to remain tracked.