"""Tests for gene quality scoring."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from crisper.gene_scorer import score_gene, GeneScore
from crisper.cultivator import build_gene_jsonl


class TestGeneScorer(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.session = Path(self.tmpdir) / "session.jsonl"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_uncultivated_scores_zero(self):
        with open(self.session, "w") as f:
            f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "hello"}}) + "\n")

        score = score_gene(self.session)
        self.assertEqual(score.overall, 0)

    def test_cultivated_scores_nonzero(self):
        sections = {
            "system_identity": "Project: TestProject\nArchitecture: monolith\nConstraint: zero deps",
            "live_state": "## Active Decisions\n- Decision: Use SQLite\n  Rationale: simplicity\n  Dependencies: none\n\n## File State Map\n- /src/main.py: created, Purpose: entry point",
            "failure_log": "## Failed Approaches\n- Approach: PostgreSQL\n  Why failed: too complex\n  Lesson: prefer embedded databases",
            "subgoal_tree": "- [x] Project setup → done\n- [ ] Auth system",
            "compressed_history": "## Topic: Setup\nConfigured project [archive:1-10]\nRelated: see Auth topic",
            "breadcrumbs": "## Archive\n- Setup discussion: archive:1-10",
            "objectives": "## Current Task\nBuild authentication\n## Next Steps\n1. Implement JWT\n2. Add middleware",
        }
        gene = build_gene_jsonl(sections, "test-session")
        self.session.write_text(gene, encoding="utf-8")

        score = score_gene(self.session)
        self.assertGreater(score.overall, 0)
        self.assertGreater(score.completeness, 0)
        self.assertGreater(score.enrichment, 0)

    def test_enriched_gene_scores_higher(self):
        # Minimal gene
        minimal = {
            "system_identity": "Project: test",
            "live_state": "Use SQLite",
            "objectives": "Build auth",
        }
        gene1 = build_gene_jsonl(minimal, "test")
        self.session.write_text(gene1, encoding="utf-8")
        score1 = score_gene(self.session)

        # Enriched gene
        enriched = {
            "system_identity": "Project: TestProject\nArchitecture: monolith with SQLite\nConstraint: zero external deps\nModel: claude-opus-4-6",
            "live_state": "## Active Decisions\n- Decision: SQLite for database\n  Rationale: embedded, no server needed, sufficient for current scale\n  Alternatives rejected: PostgreSQL (too complex), MongoDB (wrong paradigm)\n  Dependencies: affects backup strategy, migration approach\n  [augmented] Best practice: use WAL mode for concurrent reads\n\n## File State Map\n- /src/main.py: created turn 1, Purpose: FastAPI entry point, imports: fastapi, uvicorn\n- /src/db.py: created turn 3, Purpose: database connection, depends on: main.py\n\n## Dependency Graph\n- SQLite decision affects backup strategy\n- db.py imports from main.py",
            "failure_log": "## Failed Approaches\n- Approach: PostgreSQL setup\n  Why failed: added unnecessary complexity for single-user tool\n  Lesson: start with embedded DB, migrate later if needed\n  Related: see SQLite decision in live_state",
            "subgoal_tree": "- [x] Project setup → outcome: FastAPI + SQLite configured\n- [/] Auth system\n  - [ ] JWT token generation\n  - [ ] Middleware integration",
            "compressed_history": "## Topic: Database Selection\nEvaluated PostgreSQL vs SQLite. Chose SQLite for simplicity. [archive:1-10]\nLesson: embedded > server for tools\nRelated: see auth topic for token storage implications",
            "breadcrumbs": "## Archive Index\n- Database discussion: archive:1-10\n- Initial requirements: archive:1-3\n\n## How to Retrieve\ncrisper retrieve current --line N",
            "objectives": "## Current Task\nWhat: Implement JWT authentication\nAcceptance: login endpoint returns valid JWT\nApproach: python-jose library\nRisks: token expiry handling\n[augmented] Best practice: RS256 signing, ≤15min expiry\n\n## Next Steps\n1. Install python-jose\n2. Create auth routes\n3. Add middleware",
        }
        gene2 = build_gene_jsonl(enriched, "test")
        self.session.write_text(gene2, encoding="utf-8")
        score2 = score_gene(self.session)

        # Enriched should score higher on density, enrichment, cross-refs
        self.assertGreater(score2.enrichment, score1.enrichment)
        self.assertGreater(score2.overall, score1.overall)


if __name__ == "__main__":
    unittest.main()
