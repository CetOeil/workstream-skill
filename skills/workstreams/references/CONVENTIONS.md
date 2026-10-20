# Workstream conventions

A workstream is one folder under `workstreams/`, laid out as a handover: a reader, human or agent, can pick
up its outstanding work from the folder alone. [`scripts/workstreams.py`](../scripts/workstreams.py)
checks every rule marked **(checked)**.

`MUST` and **(checked)** mean the checker enforces the rule; `SHOULD` is advice for humans and
agents, not checked. A project's own `workstreams/README.md` may narrow or extend these rules, but
it cannot relax a `MUST`; record project-specific choices there.

## Layout

```text
workstreams/
  README.md                      the index (generated) and any project-specific rules
  YYYY-MM-DD-<slug>/             one workstream (checked: name)
    README.md                    required: front matter, entry point, Next steps, artifacts
    STATUS.md                    required: dated blocks, newest first, at most five
    TODO.md                      required: outstanding items and the Done table
    PLAN.md                      optional: goal, decisions, rejected alternatives, chronology
    FINDINGS.md                  optional: evidence, each with how to reproduce it
    CONCLUSIONS.md               optional: claims with confidence and status
    OPEN-ISSUES.md               optional: risks, questions and accepted limitations
    SUBAGENTS.md                 optional: sub-agent and review history
    STATUS-ARCHIVE.md            optional: STATUS blocks beyond the newest five
    artifacts/docs/              specs and plans
    artifacts/analysis/          analysis scripts and their outputs
    logs/README.md               test commands and where the logs are
```

No other files or directories **(checked)**. The `artifacts/docs/`, `artifacts/analysis/` and
`logs/README.md` rows are the default layout; a project may choose another and record it in
`workstreams/README.md`. The artifact list is the README's `## Artifacts`
section; no machine-readable copy of the Markdown is kept, because the checker reads the Markdown
itself and a second copy goes stale.

Name the folder after its first spec or plan. Name specs and plans `YYYY-MM-DD-<slug>.md`; a design
ends in `-design.md`, and the plan that implements it reuses the slug without that suffix. Each carries
a `**Status:**` line (`Draft`, `In progress`, `Implemented in <commit>`, or `Superseded by <link>`).
Checkboxes inside a plan are not authoritative; commits are.

## README.md

```markdown
---
subject: one line, what the workstream is about
phase: active
state: one line, the facts a reader of the index needs
updated: 2026-10-21 09:00
---
```

- All four keys are required **(checked)**. `updated` is `YYYY-MM-DD HH:MM` local time and not older
  than the newest STATUS block **(checked)**.
- `phase` **(checked against TODO.md)**:

  | Phase | Outstanding TODOs |
  |---|---|
  | `active` | at least one, any state |
  | `monitoring` | only `monitor` items |
  | `blocked` | at least one, waiting on something outside the workstream |
  | `done` | none; the goal was met |
  | `closed` | none; stopped without meeting the goal |

- Body, in this order: what this is (the goal, verbatim if it was given), a status table,
  `## Next steps`, the reading order, `## Artifacts` (paths, purposes, what was not kept, known-stale
  references), the environment, and folder-specific conventions.
- `## Next steps` is required **(checked)**: one to three numbered items **(checked)** that cite
  outstanding TODOs **(checked: a cited TODO exists and is not done)**, or `None: <reason>` for a
  done or closed workstream.

## TODO.md

```markdown
## 4. Review the change in live data  [open; due 2026-10-22 18:30; after TODO 3; OPEN-2]

Why, the steps, and the evidence to collect.

**Acceptance:** what must be true for the item to be done.

## Done

| # | Item | Result |
|---|---|---|
| 3 | Ship the change | done 2026-10-20: `abc1234`, deployed |
| 2 | Try the alternative | dropped 2026-10-19: superseded by TODO 3 |
```

- The bracket's first token is the state **(checked)**: `open`, `monitor` (an ongoing check after a
  change, with nothing to build) or `blocked`.
- Optional tokens: `due YYYY-MM-DD[ HH:MM]`, `not before YYYY-MM-DD[ HH:MM]`, `after TODO N`
  **(checked: N exists)**, `operator` (waits on a human decision), `OPEN-N` **(checked: exists)**.
  A trailing zone label such as `CST` is ignored.
- A finished item leaves the list and becomes a Done row whose last cell starts with `done` or
  `dropped` **(checked)**. Cite the change id the project uses (commit, deployment, ticket) in the
  file's intro if its steps are worth keeping.

## OPEN-ISSUES.md

```markdown
## Open

### OPEN-2 — The probe shares its egress with production  [open; operator; TODO 4]

## Resolved or informational

### OPEN-1 — The old endpoint is retiring  [resolved 2026-10-16; TODO 1]
```

- States **(checked)**: `open`, `monitor`, `accepted` (a risk or limitation kept on purpose), `info`,
  or `resolved <date or commit>`.
- `open` and `monitor` issues sit under `## Open`; `resolved` ones do not **(checked)**.
- A table row `| OPEN-N | state | … |` is accepted as well as a heading.
- A cited `TODO N` must exist **(checked)**.

## CONCLUSIONS.md

```markdown
## C3. Exchange-info is the cheapest fresh channel (Medium)  [current]
## C1. The service must move before the cutover (High)  [superseded 2026-10-16: moved (TODO 1)]
```

- Each heading ends with `(confidence)  [status]` **(checked)**. Status is `current`, or `confirmed`,
  `revised`, `superseded` or `retracted` followed by a date **(checked)** and the reason.
- A claim is never rewritten silently: later evidence is a dated note under it.

## STATUS.md

- Blocks are `## YYYY-MM-DD HH:MM: summary` **(checked)**, newest first **(checked)**, at most five
  **(checked)**. `trim-status` moves older blocks to `STATUS-ARCHIVE.md` and adds a pointer.
- A block records what changed, the evidence (commit, deployment, test result) and what is blocked.
  It cites FINDINGS rather than repeating them.
- STATUS, TODO, OPEN-ISSUES, the front matter and the index change in the same commit as the work
  they record.

## IDs

- TODO, OPEN and C numbers belong to their folder and are never reused or renumbered; duplicates are
  errors **(checked)**. A new ID is the highest used, Done rows included, plus one.
- Cite an ID from another folder as `<folder>/OPEN-N` or `<folder>/TODO N`.

## The index

`workstreams/README.md` holds the index between `<!-- workstreams:index:start -->` and
`<!-- workstreams:index:end -->`. `index` regenerates it from each folder's front matter and TODO.md,
and `check` fails when it is stale **(checked)**. Never edit it by hand.

## Links and secrets

Relative links in a folder's Markdown must resolve **(checked)**. No secrets are stored under
`workstreams/`.

## Platform

- Markdown is UTF-8, LF. The checker reads `utf-8-sig` (a BOM is tolerated) and writes LF on every
  OS; CRLF input is normalized before parsing.
- Folder slugs are ASCII: `[a-z0-9-]`, no trailing hyphen, at most 40 characters.
- Links use `/`. A target containing `\` is an error, and existence is matched case-sensitively, so
  a link must spell the file name exactly.
- OS metadata files (`Thumbs.db`, `desktop.ini`, `*.swp`, `*~`) are ignored by the layout check.

## Diagnostics

`check` prints one line per finding as `path:line: [CODE] message`, and exits `0` (clean), `1`
(findings), or `2` (usage or environment error). Codes are stable: `WS-LAYOUT`, `WS-FRONTMATTER`,
`WS-PHASE`, `WS-TODO`, `WS-OPEN`, `WS-CONCLUSION`, `WS-STATUS`, `WS-INDEX`, `WS-NEXT`, `WS-IDS`,
`WS-REFS`, `WS-LINK`, `WS-OVERDUE`.

`check --json` prints `{"specVersion": 1, "root": "...", "errors": [{"code", "where", "message"}],
"warnings": [...]}` for tools and CI.
