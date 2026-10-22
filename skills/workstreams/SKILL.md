---
name: workstreams
description: "Maintains the handover folders under a project's workstreams/ directory (README front matter and Next steps, STATUS, TODO, OPEN-ISSUES, CONCLUSIONS, and the generated index) and validates them with scripts/workstreams.py. Use only when the project already has workstreams/ (or sets WORKSTREAMS_DIR) or the user asks to set it up: starting a workstream, recording progress or a decision in one, closing or dropping one of its TODOs, resolving one of its open issues, revising a conclusion, handing a workstream over, fixing a failing workstreams check, or listing outstanding or due workstream items. Not for TODO comments in code, a standalone TODO.md or task list, issue trackers, an agent's plan mode, or general project planning."
compatibility: Requires Python 3.9 or newer (standard library only) to run scripts/workstreams.py.
---

# Workstreams

Keep project work in `workstreams/` as folders a stranger can pick up. The rules are in
[references/CONVENTIONS.md](references/CONVENTIONS.md); [scripts/workstreams.py](scripts/workstreams.py)
enforces the ones marked **(checked)**.

`WS` below means `python3 <this skill's directory>/scripts/workstreams.py`. On Windows use `py -3`
for `python3`; a bare `python` may be the Microsoft Store alias. If the project keeps its own copy of
the script, for example `scripts/workstreams.py`, run that copy instead. Every command accepts
`--root DIR` and `--now 'YYYY-MM-DD HH:MM'`.

## Before you act

1. Find the root: `--root`, else `WORKSTREAMS_DIR`, else the nearest `workstreams/` at or above the
   current directory whose `README.md` holds the index markers.
2. If there is none:
   - the user asked to set workstreams up → `mkdir workstreams`, copy
     `assets/workstreams-README.md` to `workstreams/README.md`, run `WS check`, and add one line to
     the project's agent instructions (`AGENTS.md`, `CLAUDE.md` or similar) that names this skill and
     requires `WS check` to pass before any commit touching `workstreams/`;
   - the user asked about workstreams without asking for set-up → say the project has none and
     offer to set it up; create nothing;
   - otherwise this skill does not apply: do not create `workstreams/`.
3. Read the project rules in `workstreams/README.md`, and CONVENTIONS.md before your first write to
   a workstream in this session.

## Actions

| Request | Do |
|---|---|
| what is due or outstanding | `WS next` |
| start a workstream | `WS new <slug> --subject "<one line>"`; write the goal in its README, real TODOs with acceptance criteria, and any design in `artifacts/docs/` with a `**Status:**` line |
| record progress or a decision, close or drop a TODO, resolve an issue | follow *Record progress* below |
| hand over | a fresh STATUS block and the README's Next steps, as below |
| validate | `WS check`; `--json` for tools |

## Record progress, in the same commit as the change

1. **STATUS.md:** add a block on top, `## YYYY-MM-DD HH:MM: <summary>` in local time, saying what
   changed, the evidence (commit, deployment, test result) and what is blocked. Over five blocks,
   run `WS trim-status <folder>`.
2. **TODO.md:**
   - Heading `## N. Title  [state; tokens]`; state `open`, `monitor` or `blocked`; tokens `due …`,
     `not before …`, `after TODO N`, `operator`, `OPEN-N`. End each item with `**Acceptance:**`.
   - A new ID is the highest used in the folder, Done rows included, plus one.
   - A finished item leaves the list and becomes a Done row, `| N | Item | done YYYY-MM-DD: <result> |`
     or `dropped YYYY-MM-DD: <reason>`.
   - Ongoing observation after a change is a `monitor` TODO, not a remark in STATUS.
3. **OPEN-ISSUES.md:** `### OPEN-N — Title  [state; refs]`, state `open`, `monitor`, `accepted`,
   `info` or `resolved <date or commit>`. Move a resolved issue out of `## Open`; keep its text.
4. **CONCLUSIONS.md:** never rewrite a claim. Change `[current]` to
   `[confirmed|revised|superseded|retracted YYYY-MM-DD: reason]` and add a dated note under it.
5. **README.md:** set `updated` (not older than the newest STATUS block), and `state` and `phase`
   when they change: `active` or `blocked` while work remains, `monitoring` when only `monitor`
   TODOs remain, `done` or `closed` when none remain. `## Next steps` holds one to three numbered
   items citing outstanding TODOs, or `None: <reason>` once done or closed. List new files under
   `## Artifacts`.
6. Run `WS index`, then `WS check`.

## Non-negotiables

- A TODO tagged `operator` waits on a human decision: present the evidence and stop.
- Never edit the table between the index markers by hand.
- IDs are never reused or renumbered.
- `WS check` exits 0 before you report the work done. Exit 1: fix the findings it prints. Exit 2:
  the command could not run; the reason is on stderr.
- Workstream files change in the same commit as the work they record.
- Only the files CONVENTIONS.md lists sit at a folder's root.
- Cite another folder's IDs as `<folder>/TODO N` or `<folder>/OPEN-N`.
- No secrets under `workstreams/`.

## When invoked directly

`/workstreams` alone: if the root exists, run `WS next` and report. Otherwise ask once whether to
set it up, and create it only after a yes, or at once when the message says `init`.
`/workstreams <request>`: handle the request under the rules above.

## Platform notes

- Markdown is UTF-8 with LF. The script tolerates a BOM and CRLF on input and writes LF on every OS.
- A slug is lowercase ASCII letters and digits in words joined by single hyphens, at most 40
  characters.
- Link targets use `/` and spell every path component with its exact case.
- Without Python 3.9+, follow CONVENTIONS.md by hand and say that `check` did not run.
