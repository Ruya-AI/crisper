"""Tests for the feedback monitor."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from crisper.monitor import (
    add_signal,
    load_feedback,
    get_feedback_path,
    get_feedback_summary,
)
from crisper.cultivator import build_gene_jsonl


class TestMonitor(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.session = Path(self.tmpdir) / "session.jsonl"
        self.session.write_text("{}\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_add_and_load_signal(self):
        add_signal(self.session, "reread", "Re-read /src/main.py", turn=5)
        signals = load_feedback(self.session)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["type"], "reread")
        self.assertIn("main.py", signals[0]["detail"])

    def test_multiple_signals(self):
        add_signal(self.session, "reread", "file1", turn=1)
        add_signal(self.session, "repetition", "tried again", turn=2)
        add_signal(self.session, "gap", "missing info", turn=3)
        signals = load_feedback(self.session)
        self.assertEqual(len(signals), 3)

    def test_signal_limit(self):
        for i in range(60):
            add_signal(self.session, "gap", f"signal {i}")
        signals = load_feedback(self.session)
        self.assertEqual(len(signals), 50)  # Keeps last 50

    def test_feedback_summary(self):
        add_signal(self.session, "reread", "file1")
        add_signal(self.session, "reread", "file2")
        add_signal(self.session, "repetition", "approach1")
        summary = get_feedback_summary(self.session)
        self.assertEqual(summary["total_signals"], 3)
        self.assertEqual(len(summary["rereads"]), 2)
        self.assertEqual(len(summary["repetitions"]), 1)

    def test_empty_feedback(self):
        summary = get_feedback_summary(self.session)
        self.assertEqual(summary["total_signals"], 0)


if __name__ == "__main__":
    unittest.main()
