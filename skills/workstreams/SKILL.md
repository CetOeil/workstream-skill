---
name: workstreams
description: 'Checkable handovers for project workstreams: README front matter, STATUS, TODO, OPEN-ISSUES, CONCLUSIONS, enforced by scripts/workstreams.py (index, check, next, new, trim-status). Use when starting a workstream (including first-time setup of workstreams/), recording progress or a decision, closing or dropping a TODO, resolving an issue, handing over, or reporting what is due. Not for general planning, one-off notes, or unrelated directories.'
user-invocable: true
---

# Workstreams

Keep project work in `workstreams/` as folders a stranger can pick up. The normative rules are
[references/CONVENTIONS.md](references/CONVENTIONS.md); `scripts/workstreams.py` enforces the
checkable ones. `WS` below means running that script with Python 3.9 or newer (`python`,
`python3`, or `py -3` on Windows).

## Before you act

- Find the folder: `--root`, else `WORKSTREAMS_DIR`, else the nearest `workstreams/` whose
  `README.md` holds the index markers.
- No folder exists? That is a first run, not a reason to stop:
  - the request starts, records, closes, or hands over work → create `workstreams/`, copy
    `assets/workstreams-README.md` to `workstreams/README.md`, run `WS check`, then continue;
  - the request only reads state ("what is due") → say the project has no `workstreams/` yet
    and offer to initialize; do not create.
- Creating or repairing a folder: read CONVENTIONS.md first.
- `WS next` and `WS check` fail without an indexed README; never run them before the folder exists.

## Actions

| Request | Do |
|---|---|
| what is due / outstanding | `WS next` |
| start one | `WS new <slug> --subject "<line>"`, then fill the README goal and TODOs with acceptance criteria |
| record progress or a decision | update the workstream's files, then `WS index` and `WS check` |
| close or drop an item, resolve an issue | move it to Done / Resolved per CONVENTIONS, then `WS index` and `WS check` |
| hand over | leave the README's Next steps and a fresh STATUS block |
| validate everything | `WS check` (exit 1 on an error; `--json` for machine-readable findings) |

## Non-negotiables

- Never edit the table between the index markers by hand.
- IDs are never reused or renumbered.
- `WS check` passes before you report the work done.
- A workstream folder changes together with the work it records.
- Only the files CONVENTIONS.md lists may sit at a folder's root.

## When invoked directly

`/workstreams` with no request: if the folder exists, run `WS next` and report. If it does not,
ask once whether to initialize, and create only after a yes — or immediately when the message
says `init`.
`/workstreams <request>`: treat the rest of the message as the request under the rules above.

## Platform notes

- Markdown is UTF-8 without BOM and uses LF; the script writes LF on every OS.
- Folder slugs are ASCII: lowercase letters, digits and hyphens, at most 40 characters.
- Links use `/`, never `\`, and must match the file name exactly (case included).
- If Python 3.9+ is unavailable, follow CONVENTIONS.md by hand and say that `check` did not run.
