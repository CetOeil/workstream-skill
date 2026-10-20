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
  | `check` | validate every folder and the index; exit 1 on an error, warn on an overdue TODO |
  | `next` | overdue, due-soon, date-gated and operator-waiting TODOs, then every open folder's Next steps |
  | `new <slug> [--subject TEXT]` | scaffold a folder dated today and add it to the index |
  | `trim-status [folder …]` | move STATUS blocks beyond the newest five to `STATUS-ARCHIVE.md` |

- **A procedure.** [`SKILL.md`](skills/workstreams/SKILL.md) tells an agent how to start a workstream,
  record progress, close items and hand over; [`CONVENTIONS.md`](skills/workstreams/references/CONVENTIONS.md)
  is the full rule set.

## Install

As a skill directory, for agents that read `SKILL.md` folders (Claude Code, Codex, Copilot and
others):

```bash
git clone <this repository> ~/workstreams-skill
ln -s ~/workstreams-skill/skills/workstreams ~/.claude/skills/workstreams   # Claude Code, per user
ln -s ~/workstreams-skill/skills/workstreams ~/.agents/skills/workstreams   # agents that read ~/.agents
```

Or copy `skills/workstreams/` into a project's own skills directory (`.claude/skills/`,
`.agents/skills/`, `.github/skills/`).

As a Claude Code plugin, from a published copy of this repository:

```text
/plugin marketplace add <owner>/<repository>
/plugin install workstreams@workstreams
```

## Use

```bash
mkdir -p workstreams
cp skills/workstreams/assets/workstreams-README.md workstreams/README.md
python3 skills/workstreams/scripts/workstreams.py new first-feature --subject "the first feature"
python3 skills/workstreams/scripts/workstreams.py check
```

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

Keep the script standard-library only, and add a test for every new rule in
[`tests/test_workstreams.py`](tests/test_workstreams.py).

## License

[MIT](LICENSE)
