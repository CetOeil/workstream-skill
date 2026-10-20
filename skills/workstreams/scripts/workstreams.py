#!/usr/bin/env python3
"""Maintain the workstream folders under workstreams/.

Commands:
  index         regenerate the workstream table in workstreams/README.md
  check         validate every workstream folder and the index; exit 1 on an error
  next          list what is overdue, due, waiting on the operator, or next, across workstreams
  new SLUG      scaffold workstreams/<today>-SLUG/ and add it to the index
  trim-status   move STATUS.md blocks beyond the newest five to STATUS-ARCHIVE.md

The workstreams directory is --root, else $WORKSTREAMS_DIR, else the first workstreams/ directory
holding a README.md with the index markers, walking up from the current directory. A project that
keeps its workstreams elsewhere, such as plans/, sets one of the first two. Times are local
wall-clock times; a trailing zone label
such as 'CST' or 'UTC' on a due date is accepted and ignored.

Python 3.9+ (standard library only). Output is UTF-8 with LF line endings on every OS.

The conventions it enforces are in ../references/CONVENTIONS.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
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
SPEC_VERSION = 1
__version__ = "0.2.0"
MAX_SLUG_LENGTH = 40
IGNORED_FILES = ("thumbs.db", "desktop.ini")
IGNORED_SUFFIXES = (".swp", "~")

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


# ---- Portable I/O ----


def read_text(path: Path) -> str:
    """Read UTF-8 (BOM tolerated) and normalize line endings to LF."""
    text = path.read_text(encoding="utf-8-sig")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def write_text(path: Path, text: str) -> None:
    """Write UTF-8 with LF, independent of the OS default."""
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


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
class Diagnostic:
    level: str
    code: str
    where: str
    message: str

    def format(self) -> str:
        prefix = f"{self.where}: " if self.where else ""
        return f"{prefix}[{self.code}] {self.message}"


@dataclass
class Report:
    items: list[Diagnostic] = field(default_factory=list)

    def error(self, where: str, msg: str, code: str = "WS-GENERAL") -> None:
        self.items.append(Diagnostic("error", code, where, msg))

    def warn(self, where: str, msg: str, code: str = "WS-OVERDUE") -> None:
        self.items.append(Diagnostic("warning", code, where, msg))

    @property
    def errors(self) -> list[str]:
        return [d.format() for d in self.items if d.level == "error"]

    @property
    def warnings(self) -> list[str]:
        return [d.format() for d in self.items if d.level == "warning"]

    def as_dict(self) -> dict[str, list[dict[str, str]]]:
        def rows(level: str) -> list[dict[str, str]]:
            return [
                {"code": d.code, "where": d.where, "message": d.message}
                for d in self.items
                if d.level == level
            ]

        return {"errors": rows("error"), "warnings": rows("warning")}


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
                report.error(where, "a numbered heading under Done; record finished items as Done rows", "WS-TODO")
                continue
            tail = TAIL_RE.match(m.group(2))
            if not tail:
                report.error(where, f"TODO {m.group(1)} has no [state] bracket", "WS-TODO")
                continue
            todo = parse_todo_bracket(int(m.group(1)), tail.group(1), tail.group(2), no, where, report)
            if todo:
                ws.todos.append(todo)
        elif in_done:
            row = TODO_ROW_RE.match(line)
            if row:
                cells = [c.strip() for c in row.group(2).split("|")]
                if not re.match(r"(?i)^(done|dropped)\b", cells[-1] if cells else ""):
                    report.error(f"{rel}:{no}", f"Done row {row.group(1)} must end with a 'done' or 'dropped' cell", "WS-TODO")
                ws.done.append(int(row.group(1)))


def parse_todo_bracket(num: int, title: str, bracket: str, line: int, where: str, report: Report) -> Todo | None:
    tokens = [t.strip() for t in bracket.split(";") if t.strip()]
    if not tokens or tokens[0] not in TODO_STATES:
        report.error(where, f"TODO {num} state must be one of {', '.join(TODO_STATES)}, got [{bracket}]", "WS-TODO")
        return None
    todo = Todo(num=num, title=title, bracket=bracket, state=tokens[0], line=line)
    for tok in tokens[1:]:
        if tok.startswith("due "):
            todo.due = parse_when(tok[4:], end_of_day=True)
            if todo.due is None:
                report.error(where, f"TODO {num}: bad date in '{tok}' (use YYYY-MM-DD[ HH:MM])", "WS-TODO")
        elif tok.startswith("not before "):
            todo.not_before = parse_when(tok[11:], end_of_day=False)
            if todo.not_before is None:
                report.error(where, f"TODO {num}: bad date in '{tok}' (use YYYY-MM-DD[ HH:MM])", "WS-TODO")
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
                report.error(where, f"OPEN-{head.group(1)} has no [state] bracket", "WS-OPEN")
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
        report.error(where, f"OPEN-{num} state must be one of {', '.join(OPEN_STATES)}, got [{bracket}]", "WS-OPEN")
        return
    if state == "resolved" and first == "resolved":
        report.error(where, f"OPEN-{num}: write 'resolved <date or commit>'", "WS-OPEN")
    if num in ws.opens:
        report.error(where, f"duplicate OPEN-{num}", "WS-IDS")
    issue = OpenIssue(num=num, state=state, line=line)
    for tok in tokens:
        issue.todos.extend(int(n) for n in TODO_REF_RE.findall(tok))
    if state in ("open", "monitor") and section != "open":
        report.error(where, f"OPEN-{num} is {state} but not under '## Open'", "WS-OPEN")
    if state == "resolved" and section == "open":
        report.error(where, f"OPEN-{num} is resolved but under '## Open'", "WS-OPEN")
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
            report.error(where, f"duplicate C{num}", "WS-IDS")
        seen.add(num)
        tail = CONC_TAIL_RE.match(head.group(2))
        if not tail:
            report.error(where, f"C{num} heading must end with '(confidence)  [status]'", "WS-CONCLUSION")
            continue
        status = tail.group(3).strip()
        word = status.split(" ", 1)[0].rstrip(":")
        if word not in CONCLUSION_STATES:
            report.error(where, f"C{num} status must start with one of {', '.join(CONCLUSION_STATES)}", "WS-CONCLUSION")
        elif word != "current" and not DATE_RE.search(status):
            report.error(where, f"C{num}: '{word}' needs a date", "WS-CONCLUSION")


def parse_status(ws: Workstream, text: str, rel: str, report: Report) -> None:
    for no, line in prose_lines(text):
        if not line.startswith("## "):
            continue
        m = STATUS_HEAD_RE.match(line)
        when = parse_stamp(f"{m.group(1)} {m.group(2)}") if m else None
        if not when:
            report.error(f"{rel}:{no}", "STATUS headings must be '## YYYY-MM-DD HH:MM: summary'", "WS-STATUS")
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
        text = read_text(readme)
        meta = parse_front_matter(text)
        if meta is None:
            report.error(f"{name}/README.md", "missing front matter (--- subject/phase/state/updated ---)")
        else:
            ws.meta = meta
        parsed = parse_next_steps(text)
        if parsed is not None:
            ws.next_steps, ws.next_steps_none = parsed
    if (path / "TODO.md").is_file():
        parse_todo_file(ws, read_text(path / "TODO.md"), f"{name}/TODO.md", report)
    if (path / "OPEN-ISSUES.md").is_file():
        parse_open_file(ws, read_text(path / "OPEN-ISSUES.md"), f"{name}/OPEN-ISSUES.md", report)
    if (path / "STATUS.md").is_file():
        parse_status(ws, read_text(path / "STATUS.md"), f"{name}/STATUS.md", report)
    return ws


def find_root(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    env = os.environ.get("WORKSTREAMS_DIR")
    if env:
        return Path(env).resolve()
    here = Path.cwd().resolve()
    for d in (here, *here.parents):
        readme = d / "workstreams" / "README.md"
        # The index markers tell a workstreams root from a skill directory of the same name.
        if readme.is_file() and INDEX_START in read_text(readme):
            return readme.parent
    sys.exit("no workstreams/README.md with index markers found; pass --root or set WORKSTREAMS_DIR")


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
        report.error(name, "folder name must be YYYY-MM-DD-<slug> (lowercase, digits, hyphens)", "WS-LAYOUT")
    for f in REQUIRED_FILES:
        if not (ws.path / f).is_file():
            report.error(name, f"missing {f}", "WS-LAYOUT")
    for p in sorted(ws.path.iterdir()):
        if (
            p.name.startswith(".")
            or p.name.casefold() in IGNORED_FILES
            or p.name.casefold().endswith(IGNORED_SUFFIXES)
        ):
            continue
        if p.is_dir() and p.name not in ALLOWED_DIRS:
            report.error(name, f"unexpected directory {p.name}/ (allowed: {', '.join(ALLOWED_DIRS)})", "WS-LAYOUT")
        elif p.is_file() and p.name not in REQUIRED_FILES + OPTIONAL_FILES:
            report.error(name, f"unexpected file {p.name}", "WS-LAYOUT")

    meta_where = f"{name}/README.md"
    if ws.meta:
        for key in FRONT_MATTER_KEYS:
            if not ws.meta.get(key):
                report.error(meta_where, f"front matter lacks '{key}'", "WS-FRONTMATTER")
        if ws.phase and ws.phase not in PHASES:
            report.error(meta_where, f"phase must be one of {', '.join(PHASES)}", "WS-PHASE")
        updated = parse_stamp(ws.meta.get("updated", ""))
        if ws.meta.get("updated") and updated is None:
            report.error(meta_where, "updated must be 'YYYY-MM-DD HH:MM'", "WS-FRONTMATTER")
        if updated and ws.status_blocks:
            newest = max(b[0] for b in ws.status_blocks)
            if updated < newest:
                report.error(meta_where, f"updated {updated:%Y-%m-%d %H:%M} is older than the newest STATUS block", "WS-PHASE")

    # IDs
    seen: set[int] = set()
    for num in [t.num for t in ws.todos] + ws.done:
        if num in seen:
            report.error(f"{name}/TODO.md", f"duplicate TODO {num}", "WS-IDS")
        seen.add(num)
    all_ids = ws.all_todo_ids()
    for t in ws.todos:
        where = f"{name}/TODO.md:{t.line}"
        for dep in t.after:
            if dep not in all_ids:
                report.error(where, f"TODO {t.num} is after unknown TODO {dep}", "WS-REFS")
        for ref in t.opens:
            if ref not in ws.opens:
                report.error(where, f"TODO {t.num} cites unknown OPEN-{ref}", "WS-REFS")
        if t.due and t.due < now:
            report.warn(where, f"TODO {t.num} is overdue (due {t.due:%Y-%m-%d %H:%M})", "WS-OVERDUE")
    for issue in ws.opens.values():
        for ref in issue.todos:
            if ref not in all_ids:
                report.error(f"{name}/OPEN-ISSUES.md:{issue.line}", f"OPEN-{issue.num} cites unknown TODO {ref}", "WS-REFS")

    # Phase against the TODO list
    if ws.phase in FINISHED_PHASES and ws.todos:
        report.error(meta_where, f"phase {ws.phase} but TODO {ws.todos[0].num} is still {ws.todos[0].state}", "WS-PHASE")
    if ws.phase in ("active", "monitoring", "blocked") and not ws.todos:
        report.error(meta_where, f"phase {ws.phase} but TODO.md has nothing outstanding", "WS-PHASE")
    if ws.phase == "monitoring" and any(t.state != "monitor" for t in ws.todos):
        report.error(meta_where, "phase monitoring but a TODO is open or blocked (use active)", "WS-PHASE")

    # Next steps
    if ws.next_steps is None:
        report.error(meta_where, "missing '## Next steps'", "WS-NEXT")
    else:
        if not ws.next_steps and not ws.next_steps_none:
            report.error(meta_where, "Next steps is empty; list 1-3 steps or write 'None: <reason>'", "WS-NEXT")
        elif not ws.next_steps and ws.phase not in FINISHED_PHASES:
            report.error(meta_where, f"phase {ws.phase} needs at least one next step", "WS-NEXT")
        if len(ws.next_steps) > MAX_NEXT_STEPS:
            report.error(meta_where, f"Next steps has {len(ws.next_steps)} items (at most {MAX_NEXT_STEPS})", "WS-NEXT")
        open_ids = {t.num for t in ws.todos}
        for step in ws.next_steps:
            for ref in map(int, TODO_REF_RE.findall(step)):
                if ref in ws.done:
                    report.error(meta_where, f"Next steps cites TODO {ref}, which is done", "WS-NEXT")
                elif ref not in open_ids:
                    report.error(meta_where, f"Next steps cites unknown TODO {ref}", "WS-NEXT")

    # STATUS
    stamps = [b[0] for b in ws.status_blocks]
    if (ws.path / "STATUS.md").is_file() and not stamps:
        report.error(f"{name}/STATUS.md", "no dated block", "WS-STATUS")
    if stamps != sorted(stamps, reverse=True):
        report.error(f"{name}/STATUS.md", "blocks must be newest first", "WS-STATUS")
    if len(stamps) > MAX_STATUS_BLOCKS:
        report.error(f"{name}/STATUS.md", f"{len(stamps)} blocks (at most {MAX_STATUS_BLOCKS}); run trim-status", "WS-STATUS")

    if (ws.path / "CONCLUSIONS.md").is_file():
        check_conclusions(read_text(ws.path / "CONCLUSIONS.md"), f"{name}/CONCLUSIONS.md", report)
    check_links(ws.path, report)


def exists_exact_case(path: Path) -> bool:
    """True when the path exists with exactly this spelling (case-sensitive on every OS)."""
    if not path.exists():
        return False
    try:
        return path.name in {entry.name for entry in path.parent.iterdir()}
    except OSError:
        return True


def check_links(path: Path, report: Report) -> None:
    files = sorted(path.glob("*.md")) + sorted((path / "logs").glob("*.md"))
    for f in files:
        rel = f"{path.name}/{f.relative_to(path)}"
        for no, line in prose_lines(read_text(f)):
            for target in LINK_RE.findall(CODE_SPAN_RE.sub("", line)):
                if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith(("#", "/")):
                    continue
                if "\\" in target:
                    report.error(f"{rel}:{no}", f"link target must use '/', got {target}", "WS-LINK")
                    continue
                dest = unquote(target.split("#", 1)[0])
                if dest and not exists_exact_case(f.parent / dest):
                    report.error(f"{rel}:{no}", f"broken link {target}", "WS-LINK")


def run_check(root: Path, now: dt.datetime) -> Report:
    report = Report()
    workstreams = load_all(root, report)
    for ws in workstreams:
        check_workstream(ws, now, report)
    readme = root / "README.md"
    if not readme.is_file():
        report.error("README.md", f"missing {root.name}/README.md", "WS-INDEX")
        return report
    text = read_text(readme)
    updated = replace_index(text, render_index(workstreams))
    if updated is None:
        report.error("README.md", f"index markers {INDEX_START} and {INDEX_END} not found", "WS-INDEX")
    elif updated != text:
        report.error("README.md", "index is stale; run the index command", "WS-INDEX")
    return report


# ---- Commands ----


def cmd_index(root: Path) -> int:
    report = Report()
    workstreams = load_all(root, report)
    readme = root / "README.md"
    if not readme.is_file():
        print(f"{readme.as_posix()} not found", file=sys.stderr)
        return 1
    text = read_text(readme)
    updated = replace_index(text, render_index(workstreams))
    if updated is None:
        print(f"README.md: index markers {INDEX_START} and {INDEX_END} not found", file=sys.stderr)
        return 1
    if updated != text:
        write_text(readme, updated)
        print("README.md: index updated")
    for e in report.errors:
        print(f"warning: {e}", file=sys.stderr)
    return 0


def cmd_check(root: Path, now: dt.datetime, as_json: bool = False) -> int:
    report = run_check(root, now)
    if as_json:
        payload = {"specVersion": SPEC_VERSION, "root": root.as_posix(), **report.as_dict()}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1 if report.errors else 0
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

This folder is one workstream; [the index](../README.md) lists the others.

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
    if (
        not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug)
        or slug.endswith("-")
        or len(slug) > MAX_SLUG_LENGTH
    ):
        print(
            f"slug must be lowercase letters, digits and single hyphens, at most {MAX_SLUG_LENGTH} characters",
            file=sys.stderr,
        )
        return 1
    path = root / f"{now:%Y-%m-%d}-{slug}"
    if path.exists():
        print(f"{path.as_posix()} already exists", file=sys.stderr)
        return 1
    path.mkdir(parents=True)
    for fname, body in scaffold(slug, subject or slug.replace("-", " "), now).items():
        write_text(path / fname, body)
    print(f"created {path.as_posix()}")
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
    intro, blocks = split_blocks(read_text(status))
    if len(blocks) <= MAX_STATUS_BLOCKS:
        return 0
    keep, move = blocks[:MAX_STATUS_BLOCKS], blocks[MAX_STATUS_BLOCKS:]
    move = [b if b.endswith("\n\n") else b.rstrip("\n") + "\n\n" for b in move]
    archive = path / "STATUS-ARCHIVE.md"
    if archive.is_file():
        a_intro, a_blocks = split_blocks(read_text(archive))
        a_body = "".join(a_blocks)
    else:
        a_intro, a_body = "# STATUS archive\n\nBlocks moved out of STATUS.md, newest first.\n\n", ""
    write_text(archive, (a_intro + "".join(move) + a_body).rstrip("\n") + "\n")
    if "STATUS-ARCHIVE.md" not in intro:
        intro = intro.rstrip("\n") + "\n\nOlder blocks are in [`STATUS-ARCHIVE.md`](STATUS-ARCHIVE.md).\n\n"
    write_text(status, (intro + "".join(keep)).rstrip("\n") + "\n")
    print(f"{path.name}: moved {len(move)} block(s) to STATUS-ARCHIVE.md")
    return len(move)


def cmd_trim(root: Path, names: list[str]) -> int:
    targets = [root / n for n in names] if names else folders(root)
    for path in targets:
        if (path / "STATUS.md").is_file():
            trim_status(path)
    return 0


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 9):
        print("workstreams.py requires Python 3.9 or newer", file=sys.stderr)
        return 2
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", help="the workstreams directory")
    parser.add_argument("--now", help="override the current local time, 'YYYY-MM-DD HH:MM'")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} (spec {SPEC_VERSION})")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("index")
    check = sub.add_parser("check")
    check.add_argument("--json", action="store_true", help="print errors and warnings as JSON")
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
        return cmd_check(root, now, args.json)
    if args.command == "next":
        return cmd_next(root, now)
    if args.command == "new":
        return cmd_new(root, args.slug, args.subject, now)
    return cmd_trim(root, args.folders)


if __name__ == "__main__":
    sys.exit(main())
