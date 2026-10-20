# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org/).

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
