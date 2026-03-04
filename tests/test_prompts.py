"""Tests for LLM prompt generation — analyzer, reflector, sniper."""

import json
import unittest

from crisper.llm_analyzer import (
    build_analyzer_prompt,
    parse_analyzer_output,
    ANALYZER_SYSTEM_PROMPT,
)
from crisper.reflector import (
    build_reflector_prompt,
    parse_reflector_output,
    REFLECTOR_SYSTEM_PROMPT,
)
from crisper.sniper import (
    build_snipe_prompt,
    parse_snipe_output,
    SNIPER_SECTION_RULES,
)


class TestAnalyzerPrompt(unittest.TestCase):
    def test_system_prompt_contains_research(self):
        self.assertIn("semantic", ANALYZER_SYSTEM_PROMPT.lower())

    def test_build_prompt(self):
        input_data = {
            "gene_summary": "Project: test",
            "raw_tail": "[user] let's use JWT\n[assistant] Good choice.",
            "start_turn": 10,
            "end_turn": 12,
            "last_cultivation_turn": 10,
        }
        system, user = build_analyzer_prompt(input_data)
        self.assertIn("CATEGORICAL", user)
        self.assertIn("SEMANTIC", user)
        self.assertIn("SUBTLE", user)
        self.assertIn("JWT", user)

    def test_parse_valid_output(self):
        output = json.dumps({
            "categorical": {"decisions": [{"what": "use JWT", "type": "explicit"}]},
            "semantic": {"phase": "executing"},
            "subtle": {},
            "affected_sections": ["live_state"],
            "urgency": "normal",
            "summary": "JWT decision made",
        })
        result = parse_analyzer_output(output)
        self.assertEqual(len(result["categorical"]["decisions"]), 1)
        self.assertEqual(result["semantic"]["phase"], "executing")

    def test_parse_markdown_wrapped(self):
        output = "```json\n" + json.dumps({"categorical": {}, "semantic": {}, "subtle": {}, "affected_sections": [], "urgency": "normal", "summary": "test"}) + "\n```"
        result = parse_analyzer_output(output)
        self.assertNotIn("_parse_error", result)

    def test_parse_garbage_returns_fallback(self):
        result = parse_analyzer_output("this is not json at all")
        self.assertTrue(result.get("_parse_error"))
        self.assertIn("live_state", result["affected_sections"])


class TestReflectorPrompt(unittest.TestCase):
    def test_system_prompt_contains_augment(self):
        self.assertIn("AUGMENT", REFLECTOR_SYSTEM_PROMPT.upper())
        self.assertIn("knowledge", REFLECTOR_SYSTEM_PROMPT.lower())

    def test_build_prompt(self):
        change_set = {"categorical": {"decisions": [{"what": "use JWT"}]}}
        affected = {"live_state": "## Decisions\n- Use sessions"}
        system, user = build_reflector_prompt(change_set, affected, "user said JWT")
        self.assertIn("JWT", user)
        self.assertIn("EVALUATE", user)
        self.assertIn("ENRICH", user)
        self.assertIn("AUGMENT", user)
        self.assertIn("10 dimensions", user.lower().replace("10", "10"))

    def test_parse_valid_output(self):
        output = json.dumps({
            "evaluate": {"decisions": [{"decision": "JWT", "inferred_rationale": "stateless"}]},
            "enrich": {"cross_references": [], "dependency_chains": [], "risks": []},
            "augment": {"items": [{"for_decision": "JWT", "dimension": "best_practices", "content": "use RS256"}]},
        })
        result = parse_reflector_output(output)
        self.assertEqual(len(result["augment"]["items"]), 1)


class TestSniperPrompt(unittest.TestCase):
    def test_all_sections_have_rules(self):
        expected = ["system_identity", "live_state", "failure_log", "subgoal_tree",
                     "compressed_history", "breadcrumbs", "objectives"]
        for section in expected:
            self.assertIn(section, SNIPER_SECTION_RULES)
            self.assertGreater(len(SNIPER_SECTION_RULES[section]), 50)

    def test_build_prompt(self):
        system, user = build_snipe_prompt(
            "live_state",
            "## Decisions\n- Use sessions",
            {"categorical": {"decisions": [{"what": "switched to JWT"}]}},
            {"evaluate": {"decisions": [{"decision": "JWT", "inferred_rationale": "stateless"}]}},
        )
        self.assertIn("live_state", user)
        self.assertIn("JWT", user)
        self.assertIn("stateless", user)

    def test_parse_output(self):
        raw = "## Active Decisions\n- Decision: JWT\n  Rationale: stateless"
        result = parse_snipe_output(raw)
        self.assertIn("JWT", result)

    def test_parse_code_block_wrapped(self):
        raw = "```markdown\n## Decisions\n- JWT\n```"
        result = parse_snipe_output(raw)
        self.assertIn("JWT", result)


if __name__ == "__main__":
    unittest.main()
