"""Tests for cross-session persister."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from crisper.persister import (
    get_persist_dir,
    get_persist_path,
    save_persistent,
    load_persistent,
    load_all_persistent,
    persist_learnings,
    format_bootstrap_context,
    parse_persist_output,
    PERSIST_FILES,
)


class TestPersister(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.session = Path(self.tmpdir) / "session.jsonl"
        self.session.write_text("{}\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_persist_dir_created(self):
        persist = get_persist_dir(self.session)
        self.assertTrue(persist.exists())
        self.assertTrue(persist.is_dir())

    def test_save_and_load(self):
        save_persistent(self.session, "patterns", "# User Patterns\n- Prefers simplicity")
        content = load_persistent(self.session, "patterns")
        self.assertIn("simplicity", content)

    def test_load_nonexistent(self):
        content = load_persistent(self.session, "patterns")
        self.assertEqual(content, "")

    def test_persist_learnings(self):
        learnings = {
            "patterns": "# Patterns\n- prefers zero deps",
            "conventions": "# Conventions\n- kebab-case files",
            "failures": "# Failures\n- circular imports",
        }
        written = persist_learnings(self.session, learnings)
        self.assertEqual(len(written), 3)
        for path in written.values():
            self.assertTrue(Path(path).exists())

    def test_load_all_persistent(self):
        save_persistent(self.session, "patterns", "patterns content")
        save_persistent(self.session, "architecture", "arch content")
        all_p = load_all_persistent(self.session)
        self.assertEqual(len(all_p), 2)
        self.assertIn("patterns", all_p)
        self.assertIn("architecture", all_p)

    def test_format_bootstrap_context(self):
        persistent = {
            "patterns": "- Prefers simplicity",
            "conventions": "- kebab-case files",
        }
        bootstrap = format_bootstrap_context(persistent)
        self.assertIn("Cross-Session Knowledge", bootstrap)
        self.assertIn("simplicity", bootstrap)
        self.assertIn("kebab-case", bootstrap)

    def test_format_empty_bootstrap(self):
        bootstrap = format_bootstrap_context({})
        self.assertEqual(bootstrap, "")

    def test_parse_persist_output(self):
        output = json.dumps({
            "patterns": "# Patterns\ntest",
            "conventions": "# Conv\ntest",
        })
        result = parse_persist_output(output)
        self.assertIn("patterns", result)
        self.assertIn("conventions", result)

    def test_parse_wrapped_output(self):
        output = "```json\n" + json.dumps({"patterns": "test"}) + "\n```"
        result = parse_persist_output(output)
        self.assertIn("patterns", result)

    def test_ignores_unknown_categories(self):
        learnings = {
            "patterns": "valid",
            "unknown_category": "should be ignored",
        }
        written = persist_learnings(self.session, learnings)
        self.assertEqual(len(written), 1)  # Only patterns written


if __name__ == "__main__":
    unittest.main()
