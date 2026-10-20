#!/usr/bin/env python3
"""Maintain the workstream folders under plans/.

Commands:
  index         regenerate the workstream table in plans/README.md
  check         validate every workstream folder and the index; exit 1 on an error
  next          list what is overdue, due, waiting on the operator, or next, across workstreams
  new SLUG      scaffold plans/<today>-SLUG/ and add it to the index
  trim-status   move STATUS.md blocks beyond the newest five to STATUS-ARCHIVE.md

The plans directory is --root, else $WORKSTREAMS_DIR, else the first plans/ directory found
walking up from the current directory. Times are local wall-clock times; a trailing zone label
such as 'CST' or 'UTC' on a due date is accepted and ignored. Standard library only.

The conventions it enforces are in ../CONVENTIONS.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

REQUIRED_FILES = ("README.md", "STATUS.md", "TODO.md")
OPTIONAL_FILES = (
    "PLAN.md",
    "FINDINGS.md",
    "CONCLUSIONS.md",
    "OPEN-ISSUES.md",
    "SUBAGENTS.md",
    "STATUS-ARCHIVE.md",
)
ALLOWED_DIRS = ("artifacts", "logs")
FRONT_MATTER_KEYS = ("subject", "phase", "state", "updated")
PHASES = ("active", "monitoring", "blocked", "done", "closed")
FINISHED_PHASES = ("done", "closed")
TODO_STATES = ("open", "monitor", "blocked")
OPEN_STATES = ("open", "monitor", "accepted", "info", "resolved")
CONCLUSION_STATES = ("current", "confirmed", "revised", "superseded", "retracted")
MAX_STATUS_BLOCKS = 5
MAX_NEXT_STEPS = 3
DUE_SOON_DAYS = 7
INDEX_START = "<!-- workstreams:index:start -->"
INDEX_END = "<!-- workstreams:index:end -->"

FOLDER_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*$")
STAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})$")
WHEN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?: (\d{2}:\d{2}))?(?: [A-Z]{2,5})?$")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
TAIL_RE = re.compile(r"^(.*\S)\s+\[([^\[\]]+)\]$")
TODO_HEAD_RE = re.compile(r"^## (\d+)\.\s+(.*\S)\s*$")
TODO_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|(.*)\|\s*$")
OPEN_HEAD_RE = re.compile(r"^### OPEN-(\d+)\s+[\u2014\u2013-]\s+(.*\S)\s*$")
OPEN_ROW_RE = re.compile(r"^\|\s*OPEN-(\d+)\s*\|\s*([^|]*?)\s*\|")
CONC_HEAD_RE = re.compile(r"^## C(\d+)\.\s+(.*\S)\s*$")
CONC_TAIL_RE = re.compile(r"^(.*\S)\s+\(([^()]+)\)\s+\[([^\[\]]+)\]$")
STATUS_HEAD_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}): (\S.*)$")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
CODE_SPAN_RE = re.compile(r"`[^`]*`")
TODO_REF_RE = re.compile(r"\bTODO (\d+)\b")


# ---- Model ----


@dataclass
class Todo:
    num: int
    title: str
    bracket: str
    state: str
    line: int
    due: dt.datetime | None = None
    not_before: dt.datetime | None = None
    after: list[int] = field(default_factory=list)
    operator: bool = False
    opens: list[int] = field(default_factory=list)


@dataclass
class OpenIssue:
    num: int
    state: str
    line: int
    todos: list[int] = field(default_factory=list)


@dataclass
class Workstream:
    path: Path
    meta: dict[str, str] = field(default_factory=dict)
    todos: list[Todo] = field(default_factory=list)
    done: list[int] = field(default_factory=list)
    opens: dict[int, OpenIssue] = field(default_factory=dict)
    status_blocks: list[tuple[dt.datetime, str, int]] = field(default_factory=list)
    next_steps: list[str] | None = None
    next_steps_none: bool = False

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def phase(self) -> str:
        return self.meta.get("phase", "")

    def all_todo_ids(self) -> set[int]:
        return {t.num for t in self.todos} | set(self.done)


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")


# ---- Parsing ----


def prose_lines(text: str) -> list[tuple[int, str]]:
    """Numbered lines outside fenced code blocks."""
    out = []
    fenced = False
    for i, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            out.append((i, line))
    return out


def parse_stamp(text: str) -> dt.datetime | None:
    m = STAMP_RE.match(text.strip())
    if not m:
        return None
    try:
        return dt.datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def parse_when(text: str, end_of_day: bool) -> dt.datetime | None:
    m = WHEN_RE.match(text.strip())
    if not m:
        return None
    try:
        day = dt.datetime.strptime(m.group(1), "%Y-%m-%d")
        if m.group(2):
            hh, mm = m.group(2).split(":")
            return day.replace(hour=int(hh), minute=int(mm))
    except ValueError:
        return None
    return day.replace(hour=23, minute=59) if end_of_day else day


def parse_front_matter(text: str) -> dict[str, str] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    meta: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return meta
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return None


def parse_todo_file(ws: Workstream, text: str, rel: str, report: Report) -> None:
    in_done = False
    for no, line in prose_lines(text):
        if line.startswith("## "):
            in_done = line.strip() == "## Done"
            m = TODO_HEAD_RE.match(line)
            if not m:
                continue
            where = f"{rel}:{no}"
            if in_done:
                report.error(where, "a numbered heading under Done; record finished items as Done rows")
                continue
            tail = TAIL_RE.match(m.group(2))
            if not tail:
                report.error(where, f"TODO {m.group(1)} has no [state] bracket")
                continue
            todo = parse_todo_bracket(int(m.group(1)), tail.group(1), tail.group(2), no, where, report)
            if todo:
                ws.todos.append(todo)
        elif in_done:
            row = TODO_ROW_RE.match(line)
            if row:
                cells = [c.strip() for c in row.group(2).split("|")]
                if not re.match(r"(?i)^(done|dropped)\b", cells[-1] if cells else ""):
                    report.error(f"{rel}:{no}", f"Done row {row.group(1)} must end with a 'done' or 'dropped' cell")
                ws.done.append(int(row.group(1)))


def parse_todo_bracket(num: int, title: str, bracket: str, line: int, where: str, report: Report) -> Todo | None:
    tokens = [t.strip() for t in bracket.split(";") if t.strip()]
    if not tokens or tokens[0] not in TODO_STATES:
        report.error(where, f"TODO {num} state must be one of {', '.join(TODO_STATES)}, got [{bracket}]")
        return None
    todo = Todo(num=num, title=title, bracket=bracket, state=tokens[0], line=line)
    for tok in tokens[1:]:
        if tok.startswith("due "):
            todo.due = parse_when(tok[4:], end_of_day=True)
            if todo.due is None:
                report.error(where, f"TODO {num}: bad date in '{tok}' (use YYYY-MM-DD[ HH:MM])")
        elif tok.startswith("not before "):
            todo.not_before = parse_when(tok[11:], end_of_day=False)
            if todo.not_before is None:
                report.error(where, f"TODO {num}: bad date in '{tok}' (use YYYY-MM-DD[ HH:MM])")
        elif m := re.fullmatch(r"after TODO (\d+)", tok):
            todo.after.append(int(m.group(1)))
        elif tok == "operator":
            todo.operator = True
        elif m := re.fullmatch(r"OPEN-(\d+)", tok):
            todo.opens.append(int(m.group(1)))
    return todo


def parse_open_file(ws: Workstream, text: str, rel: str, report: Report) -> None:
    section = ""
    for no, line in prose_lines(text):
        where = f"{rel}:{no}"
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        head = OPEN_HEAD_RE.match(line)
        if head:
            tail = TAIL_RE.match(head.group(2))
            if not tail:
                report.error(where, f"OPEN-{head.group(1)} has no [state] bracket")
                continue
            add_open(ws, int(head.group(1)), tail.group(2), section, no, where, report)
            continue
        row = OPEN_ROW_RE.match(line)
        if row:
            add_open(ws, int(row.group(1)), row.group(2), section, no, where, report)


def add_open(ws: Workstream, num: int, bracket: str, section: str, line: int, where: str, report: Report) -> None:
    tokens = [t.strip() for t in bracket.split(";") if t.strip()]
    first = tokens[0] if tokens else ""
    state = first.split(" ", 1)[0]
    if state not in OPEN_STATES:
        report.error(where, f"OPEN-{num} state must be one of {', '.join(OPEN_STATES)}, got [{bracket}]")
        return
    if state == "resolved" and first == "resolved":
        report.error(where, f"OPEN-{num}: write 'resolved <date or commit>'")
    if num in ws.opens:
        report.error(where, f"duplicate OPEN-{num}")
    issue = OpenIssue(num=num, state=state, line=line)
    for tok in tokens:
        issue.todos.extend(int(n) for n in TODO_REF_RE.findall(tok))
    if state in ("open", "monitor") and section != "open":
        report.error(where, f"OPEN-{num} is {state} but not under '## Open'")
    if state == "resolved" and section == "open":
        report.error(where, f"OPEN-{num} is resolved but under '## Open'")
    ws.opens[num] = issue


def check_conclusions(text: str, rel: str, report: Report) -> None:
    seen: set[int] = set()
    for no, line in prose_lines(text):
        head = CONC_HEAD_RE.match(line)
        if not head:
            continue
        where = f"{rel}:{no}"
        num = int(head.group(1))
        if num in seen:
            report.error(where, f"duplicate C{num}")
        seen.add(num)
        tail = CONC_TAIL_RE.match(head.group(2))
        if not tail:
            report.error(where, f"C{num} heading must end with '(confidence)  [status]'")
            continue
        status = tail.group(3).strip()
        word = status.split(" ", 1)[0].rstrip(":")
        if word not in CONCLUSION_STATES:
            report.error(where, f"C{num} status must start with one of {', '.join(CONCLUSION_STATES)}")
        elif word != "current" and not DATE_RE.search(status):
            report.error(where, f"C{num}: '{word}' needs a date")


def parse_status(ws: Workstream, text: str, rel: str, report: Report) -> None:
    for no, line in prose_lines(text):
        if not line.startswith("## "):
            continue
        m = STATUS_HEAD_RE.match(line)
        when = parse_stamp(f"{m.group(1)} {m.group(2)}") if m else None
        if not when:
            report.error(f"{rel}:{no}", "STATUS headings must be '## YYYY-MM-DD HH:MM: summary'")
            continue
        ws.status_blocks.append((when, m.group(3), no))


def parse_next_steps(text: str) -> tuple[list[str], bool] | None:
    """The numbered items of '## Next steps', and whether the section says 'None'."""
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "## Next steps")
    except StopIteration:
        return None
    items: list[str] = []
    declared_none = False
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        if re.match(r"^\d+\.\s", line):
            items.append(line)
        elif items and line.startswith("   ") and line.strip():
            items[-1] += " " + line.strip()
        elif not items and line.startswith("None"):
            declared_none = True
    return items, declared_none


def load(path: Path, report: Report) -> Workstream:
    ws = Workstream(path=path)
    name = path.name
    readme = path / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        meta = parse_front_matter(text)
        if meta is None:
            report.error(f"{name}/README.md", "missing front matter (--- subject/phase/state/updated ---)")
        else:
            ws.meta = meta
        parsed = parse_next_steps(text)
        if parsed is not None:
            ws.next_steps, ws.next_steps_none = parsed
    if (path / "TODO.md").is_file():
        parse_todo_file(ws, (path / "TODO.md").read_text(encoding="utf-8"), f"{name}/TODO.md", report)
    if (path / "OPEN-ISSUES.md").is_file():
        parse_open_file(ws, (path / "OPEN-ISSUES.md").read_text(encoding="utf-8"), f"{name}/OPEN-ISSUES.md", report)
    if (path / "STATUS.md").is_file():
        parse_status(ws, (path / "STATUS.md").read_text(encoding="utf-8"), f"{name}/STATUS.md", report)
    return ws


def find_root(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    env = os.environ.get("WORKSTREAMS_DIR")
    if env:
        return Path(env).resolve()
    here = Path.cwd().resolve()
    for d in (here, *here.parents):
        if (d / "plans").is_dir():
            return d / "plans"
    sys.exit("no plans/ directory found; pass --root or set WORKSTREAMS_DIR")


def folders(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))


def load_all(root: Path, report: Report) -> list[Workstream]:
    return [load(p, report) for p in folders(root)]


# ---- Index ----


def cell(text: str) -> str:
    return text.replace("|", "\\|").strip()


def outstanding(ws: Workstream) -> str:
    parts = [f"TODO {t.num} ({t.bracket}): {t.title}" for t in ws.todos]
    return "<br>".join(cell(p) for p in parts) if parts else "none"


def render_index(workstreams: list[Workstream]) -> str:
    rows = [
        "| Folder | Subject | Phase | State | Outstanding work |",
        "|---|---|---|---|---|",
    ]
    for ws in workstreams:
        rows.append(
            f"| [`{ws.name}`]({ws.name}/README.md) | {cell(ws.meta.get('subject', ''))} | "
            f"{cell(ws.phase)} | {cell(ws.meta.get('state', ''))} | {outstanding(ws)} |"
        )
    return "\n".join(rows)


def replace_index(readme_text: str, table: str) -> str | None:
    start = readme_text.find(INDEX_START)
    end = readme_text.find(INDEX_END)
    if start < 0 or end < start:
        return None
    return readme_text[: start + len(INDEX_START)] + "\n" + table + "\n" + readme_text[end:]


# ---- Check ----


def check_workstream(ws: Workstream, now: dt.datetime, report: Report) -> None:
    name = ws.name
    if not FOLDER_RE.match(name):
        report.error(name, "folder name must be YYYY-MM-DD-<slug> (lowercase, digits, hyphens)")
    for f in REQUIRED_FILES:
        if not (ws.path / f).is_file():
            report.error(name, f"missing {f}")
    for p in sorted(ws.path.iterdir()):
        if p.name.startswith("."):
            continue
        if p.is_dir() and p.name not in ALLOWED_DIRS:
            report.error(name, f"unexpected directory {p.name}/ (allowed: {', '.join(ALLOWED_DIRS)})")
        elif p.is_file() and p.name not in REQUIRED_FILES + OPTIONAL_FILES:
            report.error(name, f"unexpected file {p.name}")

    meta_where = f"{name}/README.md"
    if ws.meta:
        for key in FRONT_MATTER_KEYS:
            if not ws.meta.get(key):
                report.error(meta_where, f"front matter lacks '{key}'")
        if ws.phase and ws.phase not in PHASES:
            report.error(meta_where, f"phase must be one of {', '.join(PHASES)}")
        updated = parse_stamp(ws.meta.get("updated", ""))
        if ws.meta.get("updated") and updated is None:
            report.error(meta_where, "updated must be 'YYYY-MM-DD HH:MM'")
        if updated and ws.status_blocks:
            newest = max(b[0] for b in ws.status_blocks)
            if updated < newest:
                report.error(meta_where, f"updated {updated:%Y-%m-%d %H:%M} is older than the newest STATUS block")

    # IDs
    seen: set[int] = set()
    for num in [t.num for t in ws.todos] + ws.done:
        if num in seen:
            report.error(f"{name}/TODO.md", f"duplicate TODO {num}")
        seen.add(num)
    all_ids = ws.all_todo_ids()
    for t in ws.todos:
        where = f"{name}/TODO.md:{t.line}"
        for dep in t.after:
            if dep not in all_ids:
                report.error(where, f"TODO {t.num} is after unknown TODO {dep}")
        for ref in t.opens:
            if ref not in ws.opens:
                report.error(where, f"TODO {t.num} cites unknown OPEN-{ref}")
        if t.due and t.due < now:
            report.warn(where, f"TODO {t.num} is overdue (due {t.due:%Y-%m-%d %H:%M})")
    for issue in ws.opens.values():
        for ref in issue.todos:
            if ref not in all_ids:
                report.error(f"{name}/OPEN-ISSUES.md:{issue.line}", f"OPEN-{issue.num} cites unknown TODO {ref}")

    # Phase against the TODO list
    if ws.phase in FINISHED_PHASES and ws.todos:
        report.error(meta_where, f"phase {ws.phase} but TODO {ws.todos[0].num} is still {ws.todos[0].state}")
    if ws.phase in ("active", "monitoring", "blocked") and not ws.todos:
        report.error(meta_where, f"phase {ws.phase} but TODO.md has nothing outstanding")
    if ws.phase == "monitoring" and any(t.state != "monitor" for t in ws.todos):
        report.error(meta_where, "phase monitoring but a TODO is open or blocked (use active)")

    # Next steps
    if ws.next_steps is None:
        report.error(meta_where, "missing '## Next steps'")
    else:
        if not ws.next_steps and not ws.next_steps_none:
            report.error(meta_where, "Next steps is empty; list 1-3 steps or write 'None: <reason>'")
        elif not ws.next_steps and ws.phase not in FINISHED_PHASES:
            report.error(meta_where, f"phase {ws.phase} needs at least one next step")
        if len(ws.next_steps) > MAX_NEXT_STEPS:
            report.error(meta_where, f"Next steps has {len(ws.next_steps)} items (at most {MAX_NEXT_STEPS})")
        open_ids = {t.num for t in ws.todos}
        for step in ws.next_steps:
            for ref in map(int, TODO_REF_RE.findall(step)):
                if ref in ws.done:
                    report.error(meta_where, f"Next steps cites TODO {ref}, which is done")
                elif ref not in open_ids:
                    report.error(meta_where, f"Next steps cites unknown TODO {ref}")

    # STATUS
    stamps = [b[0] for b in ws.status_blocks]
    if (ws.path / "STATUS.md").is_file() and not stamps:
        report.error(f"{name}/STATUS.md", "no dated block")
    if stamps != sorted(stamps, reverse=True):
        report.error(f"{name}/STATUS.md", "blocks must be newest first")
    if len(stamps) > MAX_STATUS_BLOCKS:
        report.error(f"{name}/STATUS.md", f"{len(stamps)} blocks (at most {MAX_STATUS_BLOCKS}); run trim-status")

    if (ws.path / "CONCLUSIONS.md").is_file():
        check_conclusions((ws.path / "CONCLUSIONS.md").read_text(encoding="utf-8"), f"{name}/CONCLUSIONS.md", report)
    check_links(ws.path, report)


def check_links(path: Path, report: Report) -> None:
    files = sorted(path.glob("*.md")) + sorted((path / "logs").glob("*.md"))
    for f in files:
        rel = f"{path.name}/{f.relative_to(path)}"
        for no, line in prose_lines(f.read_text(encoding="utf-8")):
            for target in LINK_RE.findall(CODE_SPAN_RE.sub("", line)):
                if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith(("#", "/")):
                    continue
                dest = unquote(target.split("#", 1)[0])
                if dest and not (f.parent / dest).exists():
                    report.error(f"{rel}:{no}", f"broken link {target}")


def run_check(root: Path, now: dt.datetime) -> Report:
    report = Report()
    workstreams = load_all(root, report)
    for ws in workstreams:
        check_workstream(ws, now, report)
    readme = root / "README.md"
    if not readme.is_file():
        report.error("README.md", "missing plans/README.md")
        return report
    text = readme.read_text(encoding="utf-8")
    updated = replace_index(text, render_index(workstreams))
    if updated is None:
        report.error("README.md", f"index markers {INDEX_START} and {INDEX_END} not found")
    elif updated != text:
        report.error("README.md", "index is stale; run the index command")
    return report


# ---- Commands ----


def cmd_index(root: Path) -> int:
    report = Report()
    workstreams = load_all(root, report)
    readme = root / "README.md"
    if not readme.is_file():
        print(f"{readme} not found", file=sys.stderr)
        return 1
    text = readme.read_text(encoding="utf-8")
    updated = replace_index(text, render_index(workstreams))
    if updated is None:
        print(f"README.md: index markers {INDEX_START} and {INDEX_END} not found", file=sys.stderr)
        return 1
    if updated != text:
        readme.write_text(updated, encoding="utf-8")
        print("README.md: index updated")
    for e in report.errors:
        print(f"warning: {e}", file=sys.stderr)
    return 0


def cmd_check(root: Path, now: dt.datetime) -> int:
    report = run_check(root, now)
    for w in report.warnings:
        print(f"warning: {w}")
    for e in report.errors:
        print(f"error: {e}")
    print(f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    return 1 if report.errors else 0


def next_lines(root: Path, now: dt.datetime) -> list[str]:
    report = Report()
    active = [ws for ws in load_all(root, report) if ws.phase not in FINISHED_PHASES]
    soon = now + dt.timedelta(days=DUE_SOON_DAYS)
    groups: dict[str, list[str]] = {
        "Overdue": [],
        f"Due within {DUE_SOON_DAYS} days": [],
        "Not before a date": [],
        "Waiting on the operator": [],
    }
    for ws in active:
        for t in ws.todos:
            ref = f"{ws.name} TODO {t.num}: {t.title}"
            if t.due and t.due < now:
                groups["Overdue"].append(f"{ref} (due {t.due:%Y-%m-%d %H:%M})")
            elif t.due and t.due <= soon:
                groups[f"Due within {DUE_SOON_DAYS} days"].append(f"{ref} (due {t.due:%Y-%m-%d %H:%M})")
            if t.not_before:
                when = "ready" if t.not_before <= now else f"from {t.not_before:%Y-%m-%d %H:%M}"
                groups["Not before a date"].append(f"{ref} ({when})")
            if t.operator:
                groups["Waiting on the operator"].append(ref)
    out: list[str] = []
    for title, items in groups.items():
        if items:
            out.append(f"{title}:")
            out.extend(f"  {i}" for i in items)
    out.append("Next steps:")
    for ws in active:
        out.append(f"  {ws.name} [{ws.phase}]")
        out.extend(f"    {s}" for s in ws.next_steps or ["(none listed)"])
    return out


def cmd_next(root: Path, now: dt.datetime) -> int:
    print("\n".join(next_lines(root, now)))
    return 0


def scaffold(slug: str, subject: str, now: dt.datetime) -> dict[str, str]:
    stamp = f"{now:%Y-%m-%d %H:%M}"
    return {
        "README.md": f"""---
subject: {subject}
phase: active
state: started {now:%Y-%m-%d}
updated: {stamp}
---

# {subject}

This folder is one workstream of [`plans/`](../README.md).

## What this is

State the goal and its scope in a few sentences.

## Status in one table

| Item | State |
|---|---|
| Design | not written |

## Next steps

1. **TODO 1:** write the design.

## Read in this order

| File | Contents |
|---|---|
| [`README.md`](README.md) | this file |
| [`STATUS.md`](STATUS.md) | dated state blocks, newest first |
| [`TODO.md`](TODO.md) | outstanding work with acceptance criteria |

## Artifacts

| Path | Purpose |
|---|---|

## Environment

| Need | Detail |
|---|---|
""",
        "STATUS.md": f"""# STATUS

Dated blocks, newest first; at most {MAX_STATUS_BLOCKS}.

## {stamp}: workstream created
""",
        "TODO.md": f"""# TODO

IDs are stable and never reused.

## 1. Write the design  [open]

**Acceptance:** a design in `artifacts/docs/{now:%Y-%m-%d}-{slug}-design.md` with a `**Status:**` line.

## Done

| # | Item | Result |
|---|---|---|
""",
    }


def cmd_new(root: Path, slug: str, subject: str | None, now: dt.datetime) -> int:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        print("slug must be lowercase letters, digits and hyphens", file=sys.stderr)
        return 1
    path = root / f"{now:%Y-%m-%d}-{slug}"
    if path.exists():
        print(f"{path} already exists", file=sys.stderr)
        return 1
    path.mkdir(parents=True)
    for fname, body in scaffold(slug, subject or slug.replace("-", " "), now).items():
        (path / fname).write_text(body, encoding="utf-8")
    print(f"created {path}")
    return cmd_index(root)


def split_blocks(text: str) -> tuple[str, list[str]]:
    lines = text.splitlines(keepends=True)
    starts = [i for i, l in enumerate(lines) if STATUS_HEAD_RE.match(l.rstrip("\n"))]
    if not starts:
        return text, []
    intro = "".join(lines[: starts[0]])
    blocks = ["".join(lines[a:b]) for a, b in zip(starts, starts[1:] + [len(lines)])]
    return intro, blocks


def trim_status(path: Path) -> int:
    status = path / "STATUS.md"
    intro, blocks = split_blocks(status.read_text(encoding="utf-8"))
    if len(blocks) <= MAX_STATUS_BLOCKS:
        return 0
    keep, move = blocks[:MAX_STATUS_BLOCKS], blocks[MAX_STATUS_BLOCKS:]
    move = [b if b.endswith("\n\n") else b.rstrip("\n") + "\n\n" for b in move]
    archive = path / "STATUS-ARCHIVE.md"
    if archive.is_file():
        a_intro, a_blocks = split_blocks(archive.read_text(encoding="utf-8"))
        a_body = "".join(a_blocks)
    else:
        a_intro, a_body = "# STATUS archive\n\nBlocks moved out of STATUS.md, newest first.\n\n", ""
    archive.write_text((a_intro + "".join(move) + a_body).rstrip("\n") + "\n", encoding="utf-8")
    if "STATUS-ARCHIVE.md" not in intro:
        intro = intro.rstrip("\n") + "\n\nOlder blocks are in [`STATUS-ARCHIVE.md`](STATUS-ARCHIVE.md).\n\n"
    status.write_text((intro + "".join(keep)).rstrip("\n") + "\n", encoding="utf-8")
    print(f"{path.name}: moved {len(move)} block(s) to STATUS-ARCHIVE.md")
    return len(move)


def cmd_trim(root: Path, names: list[str]) -> int:
    targets = [root / n for n in names] if names else folders(root)
    for path in targets:
        if (path / "STATUS.md").is_file():
            trim_status(path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", help="the plans directory")
    parser.add_argument("--now", help="override the current local time, 'YYYY-MM-DD HH:MM'")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("index")
    sub.add_parser("check")
    sub.add_parser("next")
    new = sub.add_parser("new")
    new.add_argument("slug")
    new.add_argument("--subject")
    trim = sub.add_parser("trim-status")
    trim.add_argument("folders", nargs="*")
    args = parser.parse_args(argv)

    root = find_root(args.root)
    now = parse_stamp(args.now) if args.now else dt.datetime.now().replace(second=0, microsecond=0)
    if now is None:
        parser.error("--now must be 'YYYY-MM-DD HH:MM'")
    if args.command == "index":
        return cmd_index(root)
    if args.command == "check":
        return cmd_check(root, now)
    if args.command == "next":
        return cmd_next(root, now)
    if args.command == "new":
        return cmd_new(root, args.slug, args.subject, now)
    return cmd_trim(root, args.folders)


if __name__ == "__main__":
    sys.exit(main())
