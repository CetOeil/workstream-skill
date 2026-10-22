# workstreams

An agent skill that keeps project work in `workstreams/` as checkable handovers. Each workstream is one
folder whose README, STATUS, TODO and OPEN-ISSUES files follow a small grammar, so a script can
generate the index, list what is due, and reject a folder that has drifted. The next agent, human
or AI, picks up the outstanding work from the folder alone.

## What you get

- **A layout.** `workstreams/YYYY-MM-DD-<slug>/` with a required `README.md` (front matter: subject,
  phase, state, updated), `STATUS.md` (at most five dated blocks, older ones archived) and `TODO.md`
  (bracketed states, due dates, dependencies, a Done table), plus optional `PLAN.md`, `FINDINGS.md`,
  `CONCLUSIONS.md`, `OPEN-ISSUES.md`, `SUBAGENTS.md`, `artifacts/` and `logs/`.
- **A checker.** `workstreams.py` (Python 3.9+, standard library only):

  | Command | Effect |
  |---|---|
  | `index` | regenerate the table between the index markers in `workstreams/README.md` |
  | `check` | validate every folder and the index; exit 1 on an error, warn on an overdue TODO; `--json` for tools |
  | `next` | overdue, due-soon, date-gated and operator-waiting TODOs, then every open folder's Next steps |
  | `new <slug> [--subject TEXT]` | scaffold a folder dated today and add it to the index |
  | `trim-status [folder …]` | move STATUS blocks beyond the newest five to `STATUS-ARCHIVE.md` |

  Every command exits 0 on success, 1 when `check` finds an error, and 2 when it cannot run.

- **A procedure.** [`SKILL.md`](skills/workstreams/SKILL.md) tells an agent how to start a workstream,
  record progress, close items and hand over; [`CONVENTIONS.md`](skills/workstreams/references/CONVENTIONS.md)
  is the full rule set.

## Install

As a skill directory, for agents that read `SKILL.md` folders (Claude Code, Codex, Copilot and
others):

```bash
git clone https://github.com/CetOeil/workstream-skill.git ~/workstreams-skill
mkdir -p ~/.claude/skills ~/.agents/skills
ln -s ~/workstreams-skill/skills/workstreams ~/.claude/skills/workstreams   # Claude Code, per user
ln -s ~/workstreams-skill/skills/workstreams ~/.agents/skills/workstreams   # agents that read ~/.agents
```

On Windows, link or copy the same folder (a junction needs no administrator rights):

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.agents\skills" | Out-Null
New-Item -ItemType Junction -Path "$env:USERPROFILE\.agents\skills\workstreams" `
  -Target "<path>\workstreams-skill\skills\workstreams"
```

Or copy `skills/workstreams/` into a project's own skills directory (`.claude/skills/`,
`.agents/skills/`, `.github/skills/`).

As a Claude Code plugin:

```text
/plugin marketplace add CetOeil/workstream-skill
/plugin install workstreams@workstreams
```

## Use

```bash
mkdir -p workstreams
cp skills/workstreams/assets/workstreams-README.md workstreams/README.md
python3 skills/workstreams/scripts/workstreams.py new first-feature --subject "the first feature"
python3 skills/workstreams/scripts/workstreams.py check
```

On Windows run `py -3` in place of `python3`: a bare `python` may be the Microsoft Store alias, which
opens the Store instead of running the script (turn it off under *App execution aliases*). The script
requires Python 3.9+ and writes LF on every OS.

Add a line to the project's agent instructions so every agent loads the skill and runs `check`
before committing a change under `workstreams/`. A project may also copy the script into its own
`scripts/` directory and pin the version it validates against.

The script finds `workstreams/` by walking up from the current directory to the first one whose
`README.md` holds the index markers. A project that keeps its workstreams under another name passes
`--root <dir>` or sets `WORKSTREAMS_DIR`. The default is not `plans/` because other tools use that
name: Claude Code's `plansDirectory` setting, whose documented example is `./plans`, writes flat plan
files into the directory it names, which would mix two systems in one folder.

## Develop

```bash
python3 -m unittest discover -s tests -v
```

Use `py -3` on Windows. The suite covers the rules (`tests/test_workstreams.py`) and the
cross-platform and command-line contract (`tests/test_platform.py`: encodings, line endings, links,
slugs, exit codes, JSON output, and the skill's packaging metadata).

Keep the script standard-library only, and add a test for every new rule in
[`tests/test_workstreams.py`](tests/test_workstreams.py).

## License

[MIT](LICENSE)
