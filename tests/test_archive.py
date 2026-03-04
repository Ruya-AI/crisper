"""Tests for archive retrieval."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from crisper.archive import (
    get_archive_path,
    archive_exists,
    archive_stats,
    retrieve_lines,
    retrieve_search,
    retrieve_context,
)


class TestArchive(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.session = Path(self.tmpdir) / "session.jsonl"
        self.session.write_text("{}\n")  # Dummy session
        self.archive = get_archive_path(self.session)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write_archive(self, messages):
        with open(self.archive, "w", encoding="utf-8") as f:
            for msg in messages:
                f.write(json.dumps(msg) + "\n")

    def test_archive_path(self):
        self.assertTrue(str(self.archive).endswith(".archive.jsonl"))

    def test_archive_not_exists(self):
        self.assertFalse(archive_exists(self.session))

    def test_archive_exists(self):
        self._write_archive([{"type": "user"}])
        self.assertTrue(archive_exists(self.session))

    def test_archive_stats(self):
        self._write_archive([
            {"type": "user", "message": {"role": "user", "content": "hello"}},
            {"type": "assistant", "message": {"role": "assistant", "content": "hi"}},
        ])
        stats = archive_stats(self.session)
        self.assertTrue(stats["exists"])
        self.assertEqual(stats["lines"], 2)
        self.assertGreater(stats["bytes"], 0)

    def test_retrieve_lines(self):
        self._write_archive([
            {"type": "user", "message": {"role": "user", "content": "line one"}},
            {"type": "assistant", "message": {"role": "assistant", "content": "line two"}},
            {"type": "user", "message": {"role": "user", "content": "line three"}},
        ])
        result = retrieve_lines(self.session, 2, 2)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "assistant")

    def test_retrieve_range(self):
        self._write_archive([
            {"type": "user", "message": {"role": "user", "content": f"line {i}"}}
            for i in range(10)
        ])
        result = retrieve_lines(self.session, 3, 7)
        self.assertEqual(len(result), 5)

    def test_retrieve_search(self):
        self._write_archive([
            {"type": "user", "message": {"role": "user", "content": "hello world"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "JWT authentication setup"}]}},
            {"type": "user", "message": {"role": "user", "content": "thanks"}},
        ])
        results = retrieve_search(self.session, "JWT")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["line"], 2)

    def test_retrieve_search_no_results(self):
        self._write_archive([
            {"type": "user", "message": {"role": "user", "content": "hello"}},
        ])
        results = retrieve_search(self.session, "nonexistent")
        self.assertEqual(len(results), 0)

    def test_retrieve_context(self):
        self._write_archive([
            {"type": "user", "message": {"role": "user", "content": f"line {i}"}}
            for i in range(20)
        ])
        results = retrieve_context(self.session, 10, context=3)
        self.assertGreater(len(results), 0)
        target = [r for r in results if r["is_target"]]
        self.assertEqual(len(target), 1)
        self.assertEqual(target[0]["line"], 10)


if __name__ == "__main__":
    unittest.main()
