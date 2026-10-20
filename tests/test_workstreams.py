import contextlib
import datetime as dt
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "workstreams" / "scripts"))
import workstreams as ws  # noqa: E402

NOW = dt.datetime(2026, 10, 21, 12, 0)

INDEX_README = """# Workstreams

<!-- workstreams:index:start -->
<!-- workstreams:index:end -->

## Conventions
"""

ACTIVE_README = """---
subject: the active fixture
phase: active
state: live since 2026-10-20
updated: 2026-10-21 09:00
---

# Active fixture

## Next steps

1. **TODO 2:** read the evidence after the due time.
2. Operator: answer TODO 3.

## Read in this order

| File | Contents |
|---|---|
| [`STATUS.md`](STATUS.md) | state |
| [`TODO.md`](TODO.md) | work |
"""

ACTIVE_TODO = """# TODO

## 2. Read the evidence  [open; due 2026-10-22 18:30 CST; OPEN-1]

Text.

## 3. Decide the cap  [blocked; after TODO 2; operator]

## 4. Watch the next event  [monitor]

## 5. Rerun later  [open; not before 2026-10-21 10:00]

## Done

| # | Item | Result |
|---|---|---|
| 1 | Build it | done 2026-10-20 (`abc1234`) |
| | Earlier history | see STATUS |
"""

ACTIVE_OPEN = """# OPEN ISSUES

## Open

### OPEN-1 — The change is unproven  [monitor; TODO 2]

## Resolved or informational

### OPEN-2 — Old problem  [resolved 2026-10-20; TODO 1]

| ID | State | Summary |
|---|---|---|
| OPEN-3 | info | a note |
"""

ACTIVE_CONCLUSIONS = """# CONCLUSIONS

## C1. The cache is the cap. (High)  [current]

## C2. The fix must ship by Friday. (Medium)  [superseded 2026-10-20: shipped]
"""

ACTIVE_STATUS = """# STATUS

## 2026-10-21 09:00: evidence window opened

Text.

## 2026-10-20 18:30: deployed
"""

DONE_README = """---
subject: the finished fixture
phase: done
state: implemented 2026-10-01
updated: 2026-10-02 08:00
---

# Done fixture

## Next steps

None: the work is finished.
"""

DONE_TODO = """# TODO

## Done

| # | Item | Result |
|---|---|---|
| 1 | Ship | done 2026-10-01 |
| 2 | Extra | dropped 2026-10-01: not needed |
"""

DONE_STATUS = """# STATUS

## 2026-10-02 08:00: finished
"""


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_workstreams(root: Path) -> None:
    write(root, "README.md", INDEX_README)
    a = "2026-10-20-active-fixture"
    write(root, f"{a}/README.md", ACTIVE_README)
    write(root, f"{a}/TODO.md", ACTIVE_TODO)
    write(root, f"{a}/OPEN-ISSUES.md", ACTIVE_OPEN)
    write(root, f"{a}/CONCLUSIONS.md", ACTIVE_CONCLUSIONS)
    write(root, f"{a}/STATUS.md", ACTIVE_STATUS)
    d = "2026-09-01-done-fixture"
    write(root, f"{d}/README.md", DONE_README)
    write(root, f"{d}/TODO.md", DONE_TODO)
    write(root, f"{d}/STATUS.md", DONE_STATUS)


def quiet(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*args)


class WorkstreamsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_workstreams(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def folder(self, name="2026-10-20-active-fixture"):
        return self.root / name

    def check(self):
        return ws.run_check(self.root, NOW)

    def test_todo_brackets_parse_dates_dependencies_and_references(self):
        report = ws.Report()
        loaded = ws.load(self.folder(), report)
        self.assertEqual(report.errors, [])
        by_num = {t.num: t for t in loaded.todos}
        self.assertEqual(sorted(by_num), [2, 3, 4, 5])
        self.assertEqual(by_num[2].state, "open")
        self.assertEqual(by_num[2].due, dt.datetime(2026, 10, 22, 18, 30))
        self.assertEqual(by_num[2].opens, [1])
        self.assertEqual(by_num[3].state, "blocked")
        self.assertEqual(by_num[3].after, [2])
        self.assertTrue(by_num[3].operator)
        self.assertFalse(by_num[2].operator)
        self.assertEqual(by_num[5].not_before, dt.datetime(2026, 10, 21, 10, 0))
        self.assertEqual(loaded.done, [1])
        self.assertEqual(sorted(loaded.opens), [1, 2, 3])
        self.assertEqual(loaded.opens[1].state, "monitor")
        self.assertEqual(loaded.opens[3].state, "info")
        self.assertEqual(loaded.next_steps[0], "1. **TODO 2:** read the evidence after the due time.")

    def test_date_only_due_means_end_of_day_and_not_before_means_start(self):
        self.assertEqual(ws.parse_when("2026-10-22", end_of_day=True), dt.datetime(2026, 10, 22, 23, 59))
        self.assertEqual(ws.parse_when("2026-10-22", end_of_day=False), dt.datetime(2026, 10, 22, 0, 0))
        self.assertIsNone(ws.parse_when("22 Oct", end_of_day=True))

    def test_index_is_generated_from_front_matter_and_open_todos(self):
        self.assertEqual(quiet(ws.cmd_index, self.root), 0)
        text = (self.root / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "| [`2026-09-01-done-fixture`](2026-09-01-done-fixture/README.md) | the finished fixture | done "
            "| implemented 2026-10-01 | none |",
            text,
        )
        self.assertIn(
            "| [`2026-10-20-active-fixture`](2026-10-20-active-fixture/README.md) | the active fixture | active "
            "| live since 2026-10-20 | TODO 2 (open; due 2026-10-22 18:30 CST; OPEN-1): Read the evidence<br>"
            "TODO 3 (blocked; after TODO 2; operator): Decide the cap<br>TODO 4 (monitor): Watch the next event<br>"
            "TODO 5 (open; not before 2026-10-21 10:00): Rerun later |",
            text,
        )
        self.assertTrue(text.endswith("<!-- workstreams:index:end -->\n\n## Conventions\n"))

    def test_clean_fixture_passes_check_once_indexed(self):
        self.assertEqual(self.check().errors, ["README.md: index is stale; run the index command"])
        quiet(ws.cmd_index, self.root)
        report = self.check()
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_overdue_due_date_is_a_warning_not_an_error(self):
        quiet(ws.cmd_index, self.root)
        report = ws.run_check(self.root, dt.datetime(2026, 10, 23, 0, 0))
        self.assertEqual(report.errors, [])
        self.assertEqual(
            report.warnings,
            ["2026-10-20-active-fixture/TODO.md:3: TODO 2 is overdue (due 2026-10-22 18:30)"],
        )

    def test_check_reports_each_defect(self):
        f = self.folder()
        write(self.root, f"{f.name}/README.md", ACTIVE_README.replace("phase: active", "phase: paused").replace(
            "2. Operator: answer TODO 3.",
            "2. Operator: answer TODO 3.\n3. Close TODO 1.\n4. Read [the plan](PLAN.md).",
        ).replace("updated: 2026-10-21 09:00", "updated: 2026-10-20 09:00"))
        write(self.root, f"{f.name}/TODO.md", ACTIVE_TODO.replace("[monitor]", "[waiting]") + "| 2 | Again | done |\n")
        write(self.root, f"{f.name}/OPEN-ISSUES.md", ACTIVE_OPEN.replace("[monitor; TODO 2]", "[resolved 2026-10-21]"))
        write(self.root, f"{f.name}/CONCLUSIONS.md", ACTIVE_CONCLUSIONS.replace("[current]", "[holds]"))
        write(self.root, f"{f.name}/manifest.json", "{}")
        blocks = "".join(f"## 2026-10-{d:02d} 10:00: block {d}\n\n" for d in (21, 15, 16, 14, 13, 12))
        write(self.root, f"{f.name}/STATUS.md", "# STATUS\n\n" + blocks)
        errors = self.check().errors
        name = f.name
        expected = [
            f"{name}/TODO.md:9: TODO 4 state must be one of open, monitor, blocked, got [waiting]",
            f"{name}/OPEN-ISSUES.md:5: OPEN-1 is resolved but under '## Open'",
            f"{name}/STATUS.md: blocks must be newest first",
            f"{name}/STATUS.md: 6 blocks (at most 5); run trim-status",
            f"{name}: unexpected file manifest.json",
            f"{name}/README.md: phase must be one of active, monitoring, blocked, done, closed",
            f"{name}/README.md: updated 2026-10-20 09:00 is older than the newest STATUS block",
            f"{name}/TODO.md: duplicate TODO 2",
            f"{name}/README.md: Next steps has 4 items (at most 3)",
            f"{name}/README.md: Next steps cites TODO 1, which is done",
            f"{name}/CONCLUSIONS.md:3: C1 status must start with one of current, confirmed, revised, superseded, retracted",
            f"{name}/README.md:15: broken link PLAN.md",
        ]
        for message in expected:
            self.assertIn(message, errors)

    def test_phase_must_agree_with_the_todo_list(self):
        d = self.folder("2026-09-01-done-fixture")
        write(self.root, f"{d.name}/TODO.md", DONE_TODO.replace("## Done", "## 3. Late item  [monitor]\n\n## Done"))
        a = self.folder()
        write(self.root, f"{a.name}/README.md", ACTIVE_README.replace("phase: active", "phase: monitoring"))
        errors = self.check().errors
        self.assertIn(f"{d.name}/README.md: phase done but TODO 3 is still monitor", errors)
        self.assertIn(f"{a.name}/README.md: phase monitoring but a TODO is open or blocked (use active)", errors)

    def test_active_phase_needs_a_next_step_and_unknown_references_fail(self):
        a = self.folder()
        readme = ACTIVE_README.split("## Next steps")[0] + "## Next steps\n\nNone: waiting.\n"
        write(self.root, f"{a.name}/README.md", readme)
        write(self.root, f"{a.name}/TODO.md", ACTIVE_TODO.replace("after TODO 2", "after TODO 9").replace("OPEN-1]", "OPEN-7]"))
        errors = self.check().errors
        self.assertIn(f"{a.name}/README.md: phase active needs at least one next step", errors)
        self.assertIn(f"{a.name}/TODO.md:7: TODO 3 is after unknown TODO 9", errors)
        self.assertIn(f"{a.name}/TODO.md:3: TODO 2 cites unknown OPEN-7", errors)

    def test_next_groups_due_waiting_and_next_steps(self):
        lines = ws.next_lines(self.root, NOW)
        self.assertEqual(
            lines,
            [
                "Due within 7 days:",
                "  2026-10-20-active-fixture TODO 2: Read the evidence (due 2026-10-22 18:30)",
                "Not before a date:",
                "  2026-10-20-active-fixture TODO 5: Rerun later (ready)",
                "Waiting on the operator:",
                "  2026-10-20-active-fixture TODO 3: Decide the cap",
                "Next steps:",
                "  2026-10-20-active-fixture [active]",
                "    1. **TODO 2:** read the evidence after the due time.",
                "    2. Operator: answer TODO 3.",
            ],
        )

    def test_new_scaffold_passes_check(self):
        self.assertEqual(quiet(ws.cmd_new, self.root, "probe-latency", "probe latency", NOW), 0)
        path = self.root / "2026-10-21-probe-latency"
        self.assertEqual(sorted(p.name for p in path.iterdir()), ["README.md", "STATUS.md", "TODO.md"])
        self.assertEqual(self.check().errors, [])
        text = (self.root / "README.md").read_text(encoding="utf-8")
        self.assertIn("| probe latency | active | started 2026-10-21 | TODO 1 (open): Write the design |", text)
        self.assertEqual(quiet(ws.cmd_new, self.root, "probe-latency", None, NOW), 1)
        self.assertEqual(quiet(ws.cmd_new, self.root, "Bad_Slug", None, NOW), 1)

    def test_trim_status_moves_the_oldest_blocks_to_the_archive(self):
        f = self.folder()
        blocks = "".join(f"## 2026-10-{d:02d} 10:00: block {d}\n\nBody {d}.\n\n" for d in range(21, 14, -1))
        write(self.root, f"{f.name}/STATUS.md", "# STATUS\n\nNewest first.\n\n" + blocks)
        self.assertEqual(quiet(ws.trim_status, f), 2)
        status = (f / "STATUS.md").read_text(encoding="utf-8")
        archive = (f / "STATUS-ARCHIVE.md").read_text(encoding="utf-8")
        self.assertIn("Older blocks are in [`STATUS-ARCHIVE.md`](STATUS-ARCHIVE.md).", status)
        self.assertEqual(status.count("\n## 2026-"), 5)
        self.assertTrue(status.rstrip().endswith("Body 17."))
        self.assertEqual(
            [l for l in archive.splitlines() if l.startswith("## ")],
            ["## 2026-10-16 10:00: block 16", "## 2026-10-15 10:00: block 15"],
        )
        more = "## 2026-10-22 10:00: block 22\n\nBody 22.\n\n"
        write(self.root, f"{f.name}/STATUS.md", status.replace("## 2026-10-21", more + "## 2026-10-21", 1))
        self.assertEqual(quiet(ws.trim_status, f), 1)
        archive = (f / "STATUS-ARCHIVE.md").read_text(encoding="utf-8")
        self.assertEqual(
            [l for l in archive.splitlines() if l.startswith("## ")],
            ["## 2026-10-17 10:00: block 17", "## 2026-10-16 10:00: block 16", "## 2026-10-15 10:00: block 15"],
        )
        self.assertEqual(quiet(ws.trim_status, f), 0)

    def test_fenced_code_is_ignored(self):
        f = self.folder()
        write(self.root, f"{f.name}/TODO.md", ACTIVE_TODO + "\n```\n## 9. Example  [bogus]\n[x](missing.md)\n```\n")
        quiet(ws.cmd_index, self.root)
        self.assertEqual(self.check().errors, [])

    def test_find_root_walks_up_to_an_indexed_workstreams_directory(self):
        project = self.root / "project"
        make_workstreams(project / "workstreams")
        # A skill directory named workstreams has no index README and must be skipped.
        write(project, "skills/workstreams/SKILL.md", "---\nname: workstreams\n---\n")
        write(project, "plans/notes.md", "# A plan from another tool\n")
        cwd = Path.cwd()
        try:
            with mock.patch.dict(os.environ, {}, clear=True):
                os.chdir(project / "skills")
                self.assertEqual(ws.find_root(None), (project / "workstreams").resolve())
                os.chdir(project / "workstreams" / "2026-10-20-active-fixture")
                self.assertEqual(ws.find_root(None), (project / "workstreams").resolve())
                self.assertEqual(ws.find_root(str(project / "plans")), (project / "plans").resolve())
                os.environ["WORKSTREAMS_DIR"] = str(project / "plans")
                self.assertEqual(ws.find_root(None), (project / "plans").resolve())
        finally:
            os.chdir(cwd)


class ParseWhenTest(unittest.TestCase):
    def test_any_zone_label_is_ignored(self):
        for label in ("", " CST", " UTC", " AEDT"):
            self.assertEqual(
                ws.parse_when("2026-10-22 18:30" + label, end_of_day=True),
                dt.datetime(2026, 10, 22, 18, 30),
            )

    def test_lowercase_label_is_rejected(self):
        self.assertIsNone(ws.parse_when("2026-10-22 18:30 utc", end_of_day=True))


if __name__ == "__main__":
    unittest.main()
