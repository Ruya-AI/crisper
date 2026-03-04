"""Tests for the cultivator — gene model, boundary detection, archiving."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from crisper.cultivator import (
    is_cultivated,
    find_gene_boundary,
    get_archive_path,
    move_tail_to_archive,
    build_gene_jsonl,
    cultivate,
    GENE_MARKER,
)


def _write_jsonl(path: Path, messages: list[dict]):
    with open(path, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")


def _make_gene_user(section_name, uuid="gu1", parent="u0"):
    """User message that marks a gene section (contains the gene: marker)."""
    return {
        "type": "user",
        "uuid": uuid,
        "parentUuid": parent,
        "sessionId": "test",
        "isSidechain": False,
        "message": {"role": "user", "content": f"Project Test — {section_name} [gene:v1]"},
    }


def _make_gene_msg(section_name, content, uuid="u1", parent="gu1"):
    """Assistant message with gene section content."""
    return {
        "type": "assistant",
        "uuid": uuid,
        "parentUuid": parent,
        "sessionId": "test",
        "isSidechain": False,
        "message": {"role": "assistant", "content": [{"type": "text", "text": content}]},
    }


def _make_raw_msg(text, uuid="r1", parent="u1"):
    return {
        "type": "user",
        "uuid": uuid,
        "parentUuid": parent,
        "sessionId": "test",
        "isSidechain": False,
        "message": {"role": "user", "content": text},
    }


class TestIsCultivated(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.session = Path(self.tmpdir) / "session.jsonl"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_uncultivated_session(self):
        _write_jsonl(self.session, [
            {"type": "user", "message": {"role": "user", "content": "hello"}},
        ])
        self.assertFalse(is_cultivated(self.session))

    def test_cultivated_session(self):
        _write_jsonl(self.session, [
            _make_gene_user("System Identity"),
            _make_gene_msg("System Identity", "Project: test"),
            _make_raw_msg("hello"),
        ])
        self.assertTrue(is_cultivated(self.session))


class TestFindGeneBoundary(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.session = Path(self.tmpdir) / "session.jsonl"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_uncultivated_returns_zero(self):
        _write_jsonl(self.session, [
            {"type": "user", "message": {"role": "user", "content": "hello"}},
        ])
        self.assertEqual(find_gene_boundary(self.session), 0)

    def test_finds_boundary(self):
        _write_jsonl(self.session, [
            _make_gene_user("System Identity", uuid="gu1", parent="root"),
            _make_gene_msg("System Identity", "project info", uuid="ga1", parent="gu1"),
            _make_gene_user("Live State", uuid="gu2", parent="ga1"),
            _make_gene_msg("Live State", "decisions here", uuid="ga2", parent="gu2"),
            _make_raw_msg("this is a raw turn", uuid="r1", parent="ga2"),
            _make_raw_msg("another raw turn", uuid="r2", parent="r1"),
        ])
        boundary = find_gene_boundary(self.session)
        self.assertEqual(boundary, 4)  # First 4 are gene (2 pairs), rest are raw


class TestArchive(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.session = Path(self.tmpdir) / "session.jsonl"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_archive_path(self):
        self.assertEqual(
            get_archive_path(self.session),
            self.session.with_suffix(".archive.jsonl"),
        )

    def test_move_tail_to_archive(self):
        _write_jsonl(self.session, [
            _make_gene_msg("System Identity", "project info"),
            _make_raw_msg("raw turn 1"),
            _make_raw_msg("raw turn 2"),
        ])
        moved = move_tail_to_archive(self.session, gene_boundary=1)
        self.assertEqual(moved, 2)

        archive = get_archive_path(self.session)
        self.assertTrue(archive.exists())
        with open(archive) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 2)


class TestBuildGeneJsonl(unittest.TestCase):
    def test_builds_valid_jsonl(self):
        sections = {
            "system_identity": "Project: test\nArchitecture: monolith",
            "live_state": "## Decisions\n- Use SQLite",
            "failure_log": "## Failed\n- Tried PostgreSQL, too complex",
            "subgoal_tree": "- [x] Setup\n- [ ] Auth",
            "compressed_history": "## Topic: Setup\nConfigured project",
            "breadcrumbs": "## Archive\n- Setup: archive:1-10",
            "objectives": "## Current Task\nBuild auth\n## Next\n1. JWT setup",
        }
        result = build_gene_jsonl(sections, "test-session-id")

        # Every line should be valid JSON
        for line in result.strip().split("\n"):
            msg = json.loads(line)
            self.assertIn("type", msg)
            self.assertIn("uuid", msg)
            self.assertIn("parentUuid", msg)
            self.assertIn("message", msg)

    def test_uuid_chain_is_valid(self):
        sections = {
            "system_identity": "test",
            "live_state": "test",
            "objectives": "test",
        }
        result = build_gene_jsonl(sections, "test-id")
        messages = [json.loads(line) for line in result.strip().split("\n")]

        uuids = {msg["uuid"] for msg in messages}
        for i, msg in enumerate(messages):
            if i == 0:
                continue  # First message can have root parent
            parent = msg["parentUuid"]
            if parent != "00000000-0000-0000-0000-000000000000":
                self.assertIn(parent, uuids, f"Broken chain at message {i}")

    def test_objectives_at_end(self):
        sections = {
            "system_identity": "first",
            "live_state": "middle",
            "objectives": "OBJECTIVES_CONTENT",
        }
        result = build_gene_jsonl(sections, "test-id")
        lines = result.strip().split("\n")
        last_content = json.loads(lines[-1])
        text = last_content["message"]["content"][0]["text"]
        self.assertIn("OBJECTIVES_CONTENT", text)

    def test_includes_recent_turns(self):
        sections = {"system_identity": "test", "objectives": "test"}
        recent = [
            json.dumps({"type": "user", "uuid": "r1", "parentUuid": "x", "message": {"role": "user", "content": "sacred turn"}}),
        ]
        result = build_gene_jsonl(sections, "test-id", recent_turns=recent)
        self.assertIn("sacred turn", result)


class TestCultivate(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.session = Path(self.tmpdir) / "session.jsonl"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_first_cultivation(self):
        _write_jsonl(self.session, [
            {"type": "user", "uuid": "u1", "parentUuid": "root", "sessionId": "test", "message": {"role": "user", "content": "hello"}},
            {"type": "assistant", "uuid": "u2", "parentUuid": "u1", "sessionId": "test", "message": {"role": "assistant", "content": [{"type": "text", "text": "hi there"}]}},
        ])

        sections = {
            "system_identity": "Project: test",
            "live_state": "No decisions yet",
            "objectives": "Get started",
        }

        result = cultivate(self.session, sections, [], recent_window=10)
        self.assertTrue(result["success"])
        self.assertGreater(result["bytes_before"], 0)
        self.assertGreater(result["gene_lines"], 0)

        # Session should now be cultivated
        self.assertTrue(is_cultivated(self.session))

        # Backup should exist
        self.assertTrue(Path(result["backup_path"]).exists())


if __name__ == "__main__":
    unittest.main()
