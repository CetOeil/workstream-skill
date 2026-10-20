# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org/).

## 0.2.0 - 2026-10-21

- Cross-platform contract: `check` reads `utf-8-sig` (a BOM is tolerated), normalizes CRLF input,
  and writes LF on every OS; paths in output use `/`.
- Stable diagnostics: each finding is `path:line: [CODE] message`, the codes are documented in
  `references/CONVENTIONS.md`, `check --json` emits `{specVersion, root, errors, warnings}`, and
  exit codes are 0 (clean), 1 (findings) and 2 (usage or environment error).
- `--version`; a Python 3.9+ guard; UTF-8 console output on Windows.
- Slug limits: ASCII, at most 40 characters, no trailing hyphen.
- OS metadata (`Thumbs.db`, `desktop.ini`, `*.swp`, `*~`) no longer trips the layout check; links
  must use `/` and match the file name exactly (case included).
- `SKILL.md` rewritten: a 446-character description that fits the 500-character catalog cap,
  `user-invocable: true`, a first-run path for projects without `workstreams/`, and a section for
  direct `/workstreams` invocation.
- Docs: normative `MUST` / **(checked)** wording, project overrides, the artifact layout as a
  default rather than a requirement, a Windows junction install, and `python` / `python3` / `py -3`
  guidance.
- Added `.gitattributes` (LF), a three-OS CI matrix (Python 3.9 and 3.13), and
  `tests/test_platform.py` covering BOM, CRLF, metadata files, backslash links, slug limits and
  JSON output.

## 0.1.0 - 2026-10-21

- First release, forked from a production repository that manages eight workstreams with it.
- `workstreams.py` with `index`, `check`, `next`, `new` and `trim-status`.
- `SKILL.md` procedure, `references/CONVENTIONS.md` rule set, and an
  `assets/workstreams-README.md` template for the index.
- The default directory is `workstreams/`, found by walking up from the current directory to the
  first one whose `README.md` holds the index markers; `--root` or `WORKSTREAMS_DIR` selects another
  (the original used `plans/`).
- Due dates accept any trailing zone label of two to five capital letters (the original accepted
  only `CST`).
