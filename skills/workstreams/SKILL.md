---
name: workstreams
description: 'Manage workstream folders under plans/ as checkable handovers: README front matter (subject, phase, state, updated) and Next steps, TODO and OPEN-ISSUES bracket grammar, CONCLUSIONS status tags, dated STATUS blocks with an archive, never-reused IDs, and a generated index in plans/README.md, enforced by scripts/workstreams.py (index, check, next, new, trim-status). Use when starting a workstream, recording progress or a decision, finishing or dropping a TODO, resolving an issue, revising a conclusion, handing work over, or asking what work is outstanding or due.'
---

# Workstreams

The rules are in [CONVENTIONS.md](CONVENTIONS.md); [scripts/workstreams.py](scripts/workstreams.py)
enforces them (Python 3.9+, standard library only). In the commands below, `WS` stands for
`python3 <this skill's directory>/scripts/workstreams.py`. If the project keeps its own copy of the
script, for example `scripts/workstreams.py`, use that copy and its `plans/README.md` rules instead.

The script finds the plans directory from `--root`, else `$WORKSTREAMS_DIR`, else the first `plans/`
walking up from the current directory. `--now 'YYYY-MM-DD HH:MM'` overrides the clock.

## Set up a project once

```bash
mkdir -p plans
cp <this skill's directory>/templates/plans-README.md plans/README.md
WS check
```

Then point the project's agent instructions (`AGENTS.md`, `CLAUDE.md` or similar) at this skill and
require `WS check` to pass before any commit that touches `plans/`.

## Find outstanding work

```bash
WS next     # overdue, due within 7 days, date-gated, waiting on the operator, then Next steps
WS check    # every folder and the index; exit 1 on an error
```

A TODO tagged `operator` waits on a human decision: present the evidence and stop.

## Start a workstream

```bash
WS new <slug> --subject "<one-line subject>"
```

It creates `plans/<today>-<slug>/` with `README.md`, `STATUS.md` and `TODO.md` and adds the index row.
Write the goal in "What this is", the design in `artifacts/docs/<date>-<slug>-design.md` with a
`**Status:**` line, and real TODOs with acceptance criteria. Add `PLAN.md`, `FINDINGS.md`,
`CONCLUSIONS.md`, `OPEN-ISSUES.md` or `SUBAGENTS.md` only when they have content.

## Record progress in the same commit as the change

1. **STATUS.md:** add a block on top, `## YYYY-MM-DD HH:MM: <summary>` in local time from `date`.
   Say what changed, the evidence (commit, deployment, test result) and what is blocked.
2. **TODO.md:**
   - A new item takes the highest ID used in the folder, Done rows included, plus one. IDs are never
     reused or renumbered.
   - Heading: `## N. Title  [state; tokens]`, state `open`, `monitor` or `blocked`, tokens
     `due …`, `not before …`, `after TODO N`, `operator`, `OPEN-N`.
   - End each item with `**Acceptance:**`.
   - A finished item leaves the list and becomes a Done row,
     `| N | Item | done YYYY-MM-DD: <result> |` or `dropped YYYY-MM-DD: <reason>`.
   - Ongoing observation after a change is a `monitor` TODO, not a remark in STATUS.
3. **OPEN-ISSUES.md:** `### OPEN-N — Title  [state; refs]`, state `open`, `monitor`, `accepted`,
   `info` or `resolved <date or commit>`. Move a resolved issue out of `## Open`; keep its text.
4. **CONCLUSIONS.md:** never edit a claim silently. Change `[current]` to
   `[confirmed|revised|superseded|retracted YYYY-MM-DD: reason]` and add a dated note under it.
5. **README.md:**
   - Set `updated`, and `state` and `phase` when they change.
   - Phase: `active` while any TODO is `open` or `blocked`; `monitoring` when only `monitor` TODOs
     remain; `done` or `closed` when none remain, with `## Next steps` reading `None: <reason>`.
   - Keep `## Next steps` to three numbered items that cite outstanding TODOs.
   - List a new file under `## Artifacts`.
6. Regenerate and validate:

   ```bash
   WS trim-status <folder>   # when STATUS.md has more than five blocks
   WS index
   WS check
   ```

## Rules

- Never edit the table between the `workstreams:index` markers by hand.
- No other top-level files in a workstream folder; evidence goes in `artifacts/analysis/`, log and
  test pointers in `logs/README.md`.
- Cite an ID from another folder as `<folder>/OPEN-N` or `<folder>/TODO N`.
- No secrets under `plans/`.
