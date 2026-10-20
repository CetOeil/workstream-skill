import contextlib
import datetime as dt
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "workstreams" / "scripts"))
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


class PortableIOTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def indexed(self):
        self.assertEqual(quiet(ws.cmd_index, self.root), 0)

    def test_bom_is_tolerated(self):
        make(self.root, bom=True)
        report = ws.run_check(self.root, NOW)
        self.assertNotIn("front matter", " ".join(report.errors))

    def test_crlf_input_is_normalized_and_output_stays_lf(self):
        make(self.root, newline="\r\n")
        self.indexed()
        self.assertNotIn(b"\r", (self.root / "README.md").read_bytes())
        self.assertEqual(ws.run_check(self.root, NOW).errors, [])

    def test_os_metadata_files_are_ignored(self):
        (self.root / FOLDER / "Thumbs.db").write_bytes(b"x")
        (self.root / FOLDER / "desktop.ini").write_bytes(b"x")
        (self.root / FOLDER / "notes.swp").write_bytes(b"x")
        self.indexed()
        self.assertEqual(ws.run_check(self.root, NOW).errors, [])

    def test_backslash_link_is_rejected(self):
        self.indexed()
        todo = (self.root / FOLDER / "TODO.md").read_text(encoding="utf-8")
        write(self.root, f"{FOLDER}/TODO.md", todo + "\nSee [the doc](artifacts\\doc.md).\n")
        report = ws.run_check(self.root, NOW)
        self.assertIn("link target must use '/'", " ".join(report.errors))

    def test_slug_shape_and_length(self):
        self.assertEqual(quiet(ws.cmd_new, self.root, "a" * 41, None, NOW), 1)
        self.assertEqual(quiet(ws.cmd_new, self.root, "trailing-", None, NOW), 1)

    def test_json_output_is_machine_readable(self):
        self.indexed()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ws.cmd_check(self.root, NOW, as_json=True)
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["specVersion"], ws.SPEC_VERSION)
        self.assertEqual(payload["errors"], [])
        self.assertIsInstance(payload["warnings"], list)


if __name__ == "__main__":
    unittest.main()
