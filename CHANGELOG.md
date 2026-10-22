# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org/).

## 0.3.0 - 2026-10-23

Breaking:

- `check --json` is `specVersion` 2: each finding is `{code, path, line, message}`, with `path`
  relative to the root and `line` a number or `null`, and the output is ASCII.
- `check` applies the same slug rule as `new`: lowercase ASCII words joined by single hyphens, at
  most 40 characters. A folder such as `2026-10-21-a--b` now fails `WS-LAYOUT`.
- Exit codes are reliable for every command: 2 (nothing on stdout, the reason on stderr) when no
  workstreams directory is found, `--root` is not a directory, a slug is bad, a folder exists,
  `trim-status` names an unknown folder, or `index` cannot read the README or find its markers.
  Previously several of these exited 1 or with a traceback.
- An `updated` stamp older than the newest STATUS block is `WS-FRONTMATTER`, not `WS-PHASE`.

Fixed:

- A file that is not UTF-8 is a `WS-ENCODING` finding with its line instead of a crash; `index`
  and `next` warn about it on stderr. CR-only line endings are normalized too.
- Every finding has its documented code (no internal `WS-GENERAL`), and text output is
  `path[:line]: level: [CODE] message` with paths relative to the current directory.
- Links: CommonMark escapes (`a\_b.md`), `<...>` targets and titled links are handled; every path
  component is matched case-exactly, `..` no longer reports a false positive, and paths in
  findings use `/` on Windows.
- `--root` and `--now` work before or after the command name.
- The console keeps its own encoding (errors are replaced) instead of being forced to UTF-8.
- The script parses on Python 3.7, so older interpreters reach the version check; it is
  executable again.
- `SKILL.md`: only Agent Skills spec fields (`user-invocable` removed, `compatibility` added), so
  spec-strict validators accept it; a narrower description that applies only where `workstreams/`
  exists or set-up is requested; the progress-recording procedure restored.
- `CONVENTIONS.md` describes what the checker enforces: project rules add to it but are not read
  by the checker; only `artifacts/` and `logs/` are checked at a folder's root.
- CI runs on pushes to `main` and on pull requests, with read-only permissions and the current
  action versions.

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
- `SKILL.md` rewritten: a 446-character description, `user-invocable: true` (removed in 0.3.0),
  a first-run path for projects without `workstreams/`, and a section for
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
