import ast
import contextlib
import datetime as dt
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "workstreams"
SCRIPT = SKILL / "scripts" / "workstreams.py"
sys.path.insert(0, str(SCRIPT.parent))
import workstreams as ws  # noqa: E402

NOW = dt.datetime(2026, 10, 21, 12, 0)
FOLDER = "2026-10-21-fixture"

INDEX = "# Workstreams\n\n<!-- workstreams:index:start -->\n<!-- workstreams:index:end -->\n"
README = """---
subject: fixture
phase: active
state: started
updated: 2026-10-21 09:00
---

# Fixture

## Next steps

1. **TODO 1:** write it.
"""
TODO = """# TODO

## 1. Write it  [open]

**Acceptance:** the file exists.

## Done

| # | Item | Result |
|---|---|---|
"""
STATUS = "# STATUS\n\n## 2026-10-21 09:00: created\n"


def write(root, rel, text, newline="\n"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline=newline) as fh:
        fh.write(text)


def make(root, newline="\n", bom=False):
    files = {
        "README.md": INDEX,
        f"{FOLDER}/README.md": README,
        f"{FOLDER}/TODO.md": TODO,
        f"{FOLDER}/STATUS.md": STATUS,
    }
    for rel, text in files.items():
        if newline != "\n":
            text = text.replace("\n", newline)
        if bom:
            text = "\ufeff" + text
        write(root, rel, text)


def quiet(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*args)


def run_main(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = ws.main(list(argv))
    return code, out.getvalue(), err.getvalue()


@contextlib.contextmanager
def cwd(path):
    before = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(before)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        make(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def indexed(self):
        self.assertEqual(quiet(ws.cmd_index, self.root), 0)

    def append(self, rel, text):
        write(self.root, rel, (self.root / rel).read_text(encoding="utf-8") + text)

    def errors(self, code=None):
        return [e for e in ws.run_check(self.root, NOW).errors if code is None or f"[{code}]" in e]


class PortableIOTest(Fixture):
    def test_bom_is_tolerated_and_not_written_back(self):
        make(self.root, bom=True)
        report = ws.Report()
        self.assertEqual(ws.load(self.root / FOLDER, report).meta["subject"], "fixture")
        self.assertEqual(report.errors, [])
        self.indexed()
        self.assertFalse((self.root / "README.md").read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertEqual(self.errors(), [])

    def test_crlf_and_cr_input_is_normalized_and_output_stays_lf(self):
        make(self.root, newline="\r\n")
        write(self.root, f"{FOLDER}/STATUS.md", STATUS.replace("\n", "\r"))
        self.indexed()
        self.assertNotIn(b"\r", (self.root / "README.md").read_bytes())
        self.assertEqual(self.errors(), [])

    def test_os_metadata_files_are_ignored(self):
        (self.root / FOLDER / "Thumbs.db").write_bytes(b"x")
        (self.root / FOLDER / "desktop.ini").write_bytes(b"x")
        (self.root / FOLDER / "notes.swp").write_bytes(b"x")
        self.indexed()
        self.assertEqual(self.errors(), [])

    def test_a_file_that_is_not_utf8_is_one_finding_not_a_crash(self):
        self.indexed()
        (self.root / FOLDER / "TODO.md").write_bytes(b"# TODO\n\n## 1. Write it  [open]\n\xff\n")
        self.assertEqual(self.errors("WS-ENCODING"), [f"{FOLDER}/TODO.md:4: [WS-ENCODING] not valid UTF-8"])
        code, _, err = run_main("--root", str(self.root), "--now", "2026-10-21 12:00", "next")
        self.assertEqual(code, 0)
        self.assertIn(f"{FOLDER}/TODO.md:4: warning: [WS-ENCODING] not valid UTF-8", err)


class LinkTest(Fixture):
    def broken(self, *lines):
        write(self.root, f"{FOLDER}/artifacts/a_b.md", "# doc\n")
        self.append(f"{FOLDER}/TODO.md", "\n" + "\n".join(lines) + "\n")
        return [e.split("[WS-LINK] ", 1)[1] for e in self.errors("WS-LINK")]

    def test_links_that_resolve_pass(self):
        self.assertEqual(
            self.broken(
                "[escaped](artifacts/a\\_b.md)",
                "[angle](<artifacts/a_b.md>)",
                '[titled](artifacts/a_b.md "the doc")',
                "[up](..)",
                "[index](../README.md#workstreams)",
                "[directory](artifacts/)",
                "[web](HTTPS://example.com/Missing.md)",
            ),
            [],
        )

    def test_links_that_do_not_resolve_exactly_fail(self):
        self.assertEqual(
            self.broken(
                "[backslash](artifacts\\a_b.md)",
                '[titled](NOPE.md "t")',
                "[directory case](Artifacts/a_b.md)",
                "[file case](artifacts/A_b.md)",
            ),
            [
                "link target must use '/', got artifacts\\a_b.md",
                "broken link NOPE.md",
                "broken link Artifacts/a_b.md",
                "broken link artifacts/A_b.md",
            ],
        )


class SlugTest(Fixture):
    def test_slug_rule(self):
        for slug in ("a", "probe-latency", "v2-api", "a" * 40):
            self.assertTrue(ws.valid_slug(slug), slug)
        for slug in ("", "a" * 41, "trailing-", "-leading", "a--b", "Bad", "snake_case", "caf\u00e9"):
            self.assertFalse(ws.valid_slug(slug), slug)

    def test_new_accepts_the_longest_slug_and_rejects_a_bad_one(self):
        self.assertEqual(quiet(ws.cmd_new, self.root, "a" * 40, None, NOW), 0)
        for slug in ("a" * 41, "a--b"):
            with self.assertRaises(ws.UsageError):
                ws.cmd_new(self.root, slug, None, NOW)

    def test_check_applies_the_same_slug_rule(self):
        bad = [f"2026-10-21-{s}" for s in ("a--b", "trailing-", "a" * 41)]
        for name in bad:
            shutil.copytree(self.root / FOLDER, self.root / name)
        self.indexed()
        self.assertEqual(sorted(e.split(":", 1)[0] for e in self.errors("WS-LAYOUT")), sorted(bad))


class CliContractTest(Fixture):
    def test_json_splits_path_and_line_and_is_ascii(self):
        self.indexed()
        (self.root / FOLDER / "\u65e5\u5fd7.txt").write_text("x", encoding="utf-8")
        self.append(f"{FOLDER}/TODO.md", "\n[x](NOPE.md)\n")
        code, out, _ = run_main("--root", str(self.root), "--now", "2026-10-21 12:00", "check", "--json")
        self.assertEqual(code, 1)
        self.assertTrue(out.isascii())
        payload = json.loads(out)
        self.assertEqual(payload["specVersion"], ws.SPEC_VERSION)
        self.assertEqual(payload["root"], self.root.as_posix())
        self.assertEqual(
            payload["errors"],
            [
                {"code": "WS-LAYOUT", "path": FOLDER, "line": None, "message": "unexpected file \u65e5\u5fd7.txt"},
                {"code": "WS-LINK", "path": f"{FOLDER}/TODO.md", "line": len(TODO.splitlines()) + 2,
                 "message": "broken link NOPE.md"},
            ],
        )
        self.assertEqual(payload["warnings"], [])

    def test_text_lines_are_relative_to_the_current_directory(self):
        self.indexed()
        (self.root / FOLDER / "notes.txt").write_text("x", encoding="utf-8")
        with cwd(self.root.parent):
            code, out, _ = run_main("check", "--root", str(self.root), "--now", "2026-10-21 12:00")
        self.assertEqual(code, 1)
        self.assertIn(f"{self.root.name}/{FOLDER}: error: [WS-LAYOUT] unexpected file notes.txt", out.splitlines())

    def test_exit_2_when_the_command_cannot_run(self):
        self.indexed()
        root = str(self.root)
        for argv in (
            ("--root", str(self.root / "missing"), "check"),
            ("--root", root, "new", "Bad_Slug"),
            ("--root", root, "--now", "2026-10-21 08:00", "new", "fixture"),
            ("--root", root, "trim-status", "2026-01-01-nope"),
        ):
            code, out, err = run_main(*argv)
            self.assertEqual((code, out), (2, ""), argv)
            self.assertTrue(err.startswith("workstreams.py: "), argv)
        with self.assertRaises(SystemExit) as ctx:
            quiet(ws.main, ["--root", root, "--now", "yesterday", "next"])
        self.assertEqual(ctx.exception.code, 2)

    def test_exit_2_without_a_workstreams_directory(self):
        with tempfile.TemporaryDirectory() as empty, cwd(empty), mock.patch.dict(os.environ):
            os.environ.pop("WORKSTREAMS_DIR", None)
            code, out, err = run_main("next")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("no workstreams/README.md with index markers found", err)

    def test_index_needs_a_readable_readme_with_markers_and_check_reports_it(self):
        write(self.root, "README.md", "# Workstreams\n")
        self.assertEqual(run_main("--root", str(self.root), "index")[0], 2)
        (self.root / "README.md").write_bytes(b"# Workstreams\n\xff\n")
        self.assertEqual(run_main("--root", str(self.root), "index")[0], 2)
        with cwd(self.root):
            code, out, _ = run_main("--now", "2026-10-21 12:00", "check", "--root", ".")
        self.assertEqual(code, 1)
        self.assertIn("README.md:2: error: [WS-ENCODING] not valid UTF-8", out.splitlines())


class EntryPointTest(unittest.TestCase):
    def run_script(self, *args, cwd=None):
        env = {k: v for k, v in os.environ.items() if k != "WORKSTREAMS_DIR"}
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8"
        )

    def test_version(self):
        result = self.run_script("--version")
        self.assertEqual((result.returncode, result.stdout.strip()), (0, f"workstreams.py {ws.__version__} (spec 2)"))

    def test_discovery_json_and_missing_root_through_the_real_entry_point(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as empty:
            root = Path(project).resolve() / "workstreams"
            make(root)
            self.assertEqual(self.run_script("--root", str(root), "index").returncode, 0)
            found = self.run_script("check", "--json", "--now", "2026-10-21 12:00", cwd=root / FOLDER)
            self.assertEqual(found.returncode, 0, found.stderr)
            self.assertEqual(json.loads(found.stdout)["root"], root.as_posix())
            lost = self.run_script("check", cwd=empty)
            self.assertEqual((lost.returncode, lost.stdout), (2, ""))

    @unittest.skipIf(os.name == "nt", "Windows has no executable bit")
    def test_script_is_executable(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK))

    def test_source_parses_as_python_3_7_so_older_interpreters_reach_the_version_check(self):
        ast.parse(SCRIPT.read_text(encoding="utf-8"), feature_version=(3, 7))


class PackagingTest(unittest.TestCase):
    def test_versions_agree(self):
        plugin = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
        latest = re.search(r"^## (\S+)", changelog, re.MULTILINE).group(1)
        self.assertEqual([plugin["version"], market["plugins"][0]["version"], latest], [ws.__version__] * 3)

    def test_skill_front_matter_uses_only_agent_skills_spec_fields(self):
        head = (SKILL / "SKILL.md").read_text(encoding="utf-8").split("---\n")[1]
        fields = dict(line.split(": ", 1) for line in head.splitlines())
        self.assertLessEqual(
            set(fields), {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
        )
        self.assertEqual(fields["name"], SKILL.name)
        description = json.loads(fields["description"])
        self.assertLessEqual(len(description), 1024)
        self.assertNotRegex(description, "[<>]")
        self.assertLessEqual(len(fields["compatibility"]), 500)


if __name__ == "__main__":
    unittest.main()
