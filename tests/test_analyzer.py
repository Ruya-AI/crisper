"""Tests for the heuristic analyzer."""

import json
import tempfile
import unittest
from pathlib import Path

from crisper.analyzer import analyze_session, _extract_decisions, _extract_file_changes, _extract_error_chains, _extract_references, _extract_failed_attempts, _extract_topics


def _write_session(messages: list[dict]) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w")
    for msg in messages:
        tmp.write(json.dumps(msg) + "\n")
    tmp.close()
    return Path(tmp.name)


def _make_user(text, idx=0):
    return (idx, {"type": "user", "message": {"role": "user", "content": text}})


def _make_assistant(text, idx=0):
    return (idx, {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}})


def _make_tool_use(name, inp, idx=0):
    return (idx, {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": f"t{idx}", "name": name, "input": inp}]}})


class TestExtractDecisions(unittest.TestCase):
    def test_detects_explicit_decision(self):
        messages = [_make_assistant("I decided to use PostgreSQL for the database.", 0)]
        decisions = _extract_decisions(messages)
        self.assertGreater(len(decisions), 0)
        self.assertIn("PostgreSQL", decisions[0].summary)

    def test_detects_lets_go_with(self):
        messages = [_make_user("let's go with JWT for auth", 0)]
        decisions = _extract_decisions(messages)
        self.assertGreater(len(decisions), 0)

    def test_ignores_non_decision(self):
        messages = [_make_assistant("The file has 200 lines.", 0)]
        decisions = _extract_decisions(messages)
        self.assertEqual(len(decisions), 0)


class TestExtractFileChanges(unittest.TestCase):
    def test_detects_write(self):
        messages = [_make_tool_use("Write", {"file_path": "/src/main.py"}, 0)]
        changes = _extract_file_changes(messages)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].action, "created")
        self.assertEqual(changes[0].path, "/src/main.py")

    def test_detects_edit(self):
        messages = [_make_tool_use("Edit", {"file_path": "/src/main.py"}, 0)]
        changes = _extract_file_changes(messages)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].action, "modified")

    def test_deduplicates_by_path(self):
        messages = [
            _make_tool_use("Write", {"file_path": "/src/main.py"}, 0),
            _make_tool_use("Edit", {"file_path": "/src/main.py"}, 1),
        ]
        changes = _extract_file_changes(messages)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].action, "modified")  # Last action wins


class TestExtractErrors(unittest.TestCase):
    def test_detects_error(self):
        messages = [_make_assistant("Error: ENOENT file not found at /tmp/test.py", 0)]
        errors = _extract_error_chains(messages)
        self.assertGreater(len(errors), 0)

    def test_detects_fix(self):
        messages = [_make_assistant("The error was caused by a missing import. Fixed by adding import os.", 0)]
        errors = _extract_error_chains(messages)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any(e.fix for e in errors))


class TestExtractReferences(unittest.TestCase):
    def test_detects_url(self):
        messages = [_make_assistant("See https://docs.python.org/3/library/json.html for details.", 0)]
        refs = _extract_references(messages)
        self.assertEqual(len(refs), 1)
        self.assertIn("docs.python.org", refs[0].url)

    def test_deduplicates(self):
        messages = [
            _make_assistant("See https://example.com for info.", 0),
            _make_assistant("Again, https://example.com is useful.", 1),
        ]
        refs = _extract_references(messages)
        self.assertEqual(len(refs), 1)


class TestExtractFailedAttempts(unittest.TestCase):
    def test_detects_failure(self):
        messages = [_make_assistant("That didn't work because the import was circular.", 0)]
        attempts = _extract_failed_attempts(messages)
        self.assertGreater(len(attempts), 0)

    def test_detects_try_again(self):
        messages = [_make_user("let me try a different approach", 0)]
        attempts = _extract_failed_attempts(messages)
        self.assertGreater(len(attempts), 0)


class TestExtractTopics(unittest.TestCase):
    def test_detects_topic_shift(self):
        messages = [
            _make_user("Let's work on the database schema with PostgreSQL tables", 0),
            _make_user("Now let's configure the database indexes", 1),
            _make_user("Set up the primary keys and foreign keys", 2),
            _make_user("Now let's switch to the authentication system with JWT tokens", 10),
            _make_user("Configure the token signing and verification", 11),
            _make_user("Set up the login endpoint with password hashing", 12),
        ]
        topics = _extract_topics(messages)
        self.assertGreater(len(topics), 0)

    def test_no_topics_from_short_session(self):
        messages = [_make_user("hello", 0)]
        topics = _extract_topics(messages)
        self.assertEqual(len(topics), 0)


class TestAnalyzeSession(unittest.TestCase):
    def test_full_analysis(self):
        messages = [
            {"type": "user", "message": {"role": "user", "content": "Build a REST API with FastAPI"}},
            {"type": "assistant", "message": {"role": "assistant", "model": "claude-opus-4-6", "content": [{"type": "text", "text": "I'll use FastAPI. Let's go with SQLite for simplicity."}], "usage": {"input_tokens": 1000, "output_tokens": 200, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": "/src/main.py"}}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Error: ModuleNotFoundError for fastapi. Fixed by adding to requirements."}]}},
            {"type": "user", "message": {"role": "user", "content": "See https://fastapi.tiangolo.com for docs"}},
        ]
        path = _write_session(messages)
        try:
            analysis = analyze_session(path, recent_window=2)
            self.assertEqual(analysis.model, "claude-opus-4-6")
            self.assertEqual(analysis.token_count, 1000)
            self.assertIn("REST API", analysis.session_intent)
            self.assertGreater(len(analysis.file_changes), 0)
            self.assertGreater(len(analysis.references), 0)
            self.assertEqual(analysis.total_turns, 5)
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
