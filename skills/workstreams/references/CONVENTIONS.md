# Workstream conventions

A workstream is one folder under `workstreams/`, laid out as a handover: a reader, human or agent, can pick
up its outstanding work from the folder alone. [`scripts/workstreams.py`](../scripts/workstreams.py)
checks every rule marked **(checked)**.

Rules marked **(checked)** are enforced by the checker; the rest are conventions it cannot verify.
A project may add its own rules in `workstreams/README.md`. The checker does not read them, and they
cannot relax a checked rule.

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

Only the files above and the `artifacts/` and `logs/` directories may sit at a folder's root
**(checked)**; dotfiles and OS metadata files are ignored. What goes inside `artifacts/` and `logs/`
is a recommendation, not checked; a project that organizes them differently records its choice in
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
  **(checked: N exists)**, `operator` (waits on a human decision: an agent presents the evidence
  and stops), `OPEN-N` **(checked: exists)**. A trailing zone label such as `CST` is ignored.
- A new item ends with `**Acceptance:**`. Ongoing observation after a change is a `monitor` TODO,
  not a remark in STATUS.
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

Relative links in the Markdown files at a folder's root and in its `logs/` must resolve
**(checked)**. No secrets are stored under `workstreams/`.

## Platform

- Markdown is UTF-8 with LF. The checker reads `utf-8-sig` (a BOM is tolerated), normalizes CRLF
  and CR to LF before parsing, and writes LF on every OS. A file that is not UTF-8 is a
  `WS-ENCODING` finding at the line of the first bad byte.
- A slug is lowercase ASCII letters and digits in words joined by single hyphens, at most 40
  characters **(checked by both `check` and `new`)**: `probe-latency` passes; `probe--latency`,
  `probe-` and `Probe` fail.
- A link target uses `/`. CommonMark backslash escapes such as `a\_b.md` are allowed; any other `\`
  is an error. Every named component must exist with exactly that case, on every OS. Targets in
  `<...>` and targets followed by a title are checked too.
- Dotfiles and OS metadata files (`Thumbs.db`, `desktop.ini`, `*.swp`, `*~`) are ignored by the
  layout check.

## Diagnostics

`check` prints one line per finding, warnings first, as `path[:line]: level: [CODE] message`, with
the path relative to the current directory and `/` as the separator. Codes are stable: `WS-LAYOUT`,
`WS-FRONTMATTER`, `WS-PHASE`, `WS-TODO`, `WS-OPEN`, `WS-CONCLUSION`, `WS-STATUS`, `WS-INDEX`,
`WS-NEXT`, `WS-IDS`, `WS-REFS`, `WS-LINK`, `WS-ENCODING` and, as a warning, `WS-OVERDUE`.

Every command exits `0` on success (for `check`: no errors), `1` when `check` found an error, and
`2` when the command could not run: no workstreams directory, a bad option or slug, a folder that
already exists, an unknown folder for `trim-status`, or a README or STATUS file the command must
rewrite but cannot read. On `2` nothing is printed to stdout and the reason goes to stderr. `index`
and `next` warn on stderr about a file they could not parse.

`check --json` prints ASCII JSON for tools and CI:

```json
{"specVersion": 2, "root": "/abs/path/workstreams",
 "errors": [{"code": "WS-LINK", "path": "2026-10-21-probe/TODO.md", "line": 12, "message": "broken link x.md"}],
 "warnings": []}
```

`path` is relative to `root` and uses `/`; `line` is a number or `null`. `specVersion` changes only
when the shape changes incompatibly.
