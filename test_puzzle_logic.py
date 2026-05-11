"""
Puzzle Logic v4.0 Integration Tests
====================================

TDD-style vertical slice tests. Each test exercises behavior through public interfaces.
Run: python test_puzzle_logic.py
"""

import sys
import os
import json
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from puzzle_logic_agent import (
    PuzzleLogicAgent, LMStudioClient, extract_error_fingerprint,
    extract_code, execute_code, infer_fix_strategy, StrategyExtractor,
    AttemptTracker,
)

# v4.0 modules
from personality_engine import (
    PatternPersonality, PersonalityPatternNode, PersonalityKnowledgeGraph,
)
from model_personality import (
    ModelPersonality, PersonalityAggregator, PersonalityPromptBuilder,
    PersonalityAwareKnowledgeGraph,
)
from constraint_engine import HybridConstraintEngine


class TestErrorFingerprint(unittest.TestCase):
    """Behavior: extract_error_fingerprint identifies error type, signature, and line."""

    def test_name_error(self):
        err = "NameError: name 'foo' is not defined"
        t, sig, line = extract_error_fingerprint(err)
        self.assertEqual(t, "NameError")
        self.assertIn("not defined", sig)

    def test_type_error(self):
        err = "TypeError: my_func() takes 2 positional arguments but 3 were given"
        t, sig, line = extract_error_fingerprint(err)
        self.assertEqual(t, "TypeError")
        self.assertIn("takes <N> positional argument", sig)

    def test_assertion_error(self):
        err = "AssertionError: assert x == y"
        t, sig, line = extract_error_fingerprint(err)
        self.assertEqual(t, "AssertionError")

    def test_traceback_parsing(self):
        tb = """Traceback (most recent call last):
  File "test.py", line 5, in <module>
    result = my_func(1, 2, 3)
TypeError: my_func() takes 2 positional arguments but 3 were given"""
        t, sig, line = extract_error_fingerprint(tb)
        self.assertEqual(t, "TypeError")
        self.assertEqual(line, "result = my_func(1, 2, 3)")

    def test_empty_error(self):
        t, sig, line = extract_error_fingerprint("")
        self.assertEqual(t, "Unknown")


class TestCodeExtraction(unittest.TestCase):
    """Behavior: extract_code finds Python code in model output."""

    def test_markdown_block(self):
        text = "```python\ndef foo():\n    return 1\n```"
        code = extract_code(text)
        self.assertIn("def foo()", code)

    def test_plain_code(self):
        text = "def bar():\n    pass"
        code = extract_code(text)
        self.assertIn("def bar()", code)

    def test_no_code(self):
        text = "I cannot help with that."
        code = extract_code(text)
        self.assertEqual(code, "")


class TestCodeExecution(unittest.TestCase):
    """Behavior: execute_code runs Python safely in a sandbox."""

    def test_simple_pass(self):
        result = execute_code("print('hello')")
        self.assertTrue(result["passed"])

    def test_syntax_error(self):
        result = execute_code("def foo(\n")
        self.assertFalse(result["passed"])
        self.assertIn("SyntaxError", result["error"])

    def test_runtime_error(self):
        result = execute_code("1/0")
        self.assertFalse(result["passed"])
        self.assertIn("ZeroDivisionError", result["error"])

    def test_timeout(self):
        result = execute_code("while True: pass", timeout=1)
        self.assertFalse(result["passed"])
        self.assertIn("Timeout", result["error"])

    def test_empty_code(self):
        result = execute_code("")
        self.assertFalse(result["passed"])


class TestStrategyExtractor(unittest.TestCase):
    """Behavior: StrategyExtractor guesses the fix strategy from a code diff."""

    def test_add_parameter(self):
        old = "def func(a):\n    return a\n"
        new = "def func(a, b):\n    return a + b\n"
        s = StrategyExtractor().extract(old, new)
        self.assertEqual(s, "add parameter")

    def test_change_return(self):
        old = "def func():\n    return 1\n"
        new = "def func():\n    return 2\n"
        s = StrategyExtractor().extract(old, new)
        self.assertEqual(s, "change return value")

    def test_add_import(self):
        old = "def func():\n    pass\n"
        new = "import math\ndef func():\n    pass\n"
        s = StrategyExtractor().extract(old, new)
        self.assertEqual(s, "add import")

    def test_unknown(self):
        s = StrategyExtractor().extract("", "")
        self.assertEqual(s, "unknown")


class TestAttemptTracker(unittest.TestCase):
    """Behavior: AttemptTracker records attempts and generates rotation hints."""

    def test_rotation_hint(self):
        tracker = AttemptTracker()
        tracker.record("TypeError", "def f(): pass", "def f(x): pass", False)
        tracker.record("TypeError", "def f(x): pass", "def f(x, y): pass", False)
        hint = tracker.get_rotation_hint()
        self.assertIn("rotation", hint.lower())
        self.assertIn("add parameter", hint)

    def test_no_rotation_when_all_pass(self):
        tracker = AttemptTracker()
        tracker.record("TypeError", "a", "b", True)
        self.assertEqual(tracker.get_rotation_hint(), "")

    def test_successful_strategy(self):
        tracker = AttemptTracker()
        tracker.record("TypeError", "def f():\n    return 1", "def f(x):\n    return x", False)
        tracker.record("TypeError", "def f(x):\n    return x", "def f(a, b):\n    return a + b", True)
        # The successful strategy should be something recognizable
        self.assertIn(tracker.get_successful_strategy(),
                      ["add parameter", "change return value", "code change"])


class TestPatternPersonality(unittest.TestCase):
    """Behavior: PatternPersonality computes decay and composite scores correctly."""

    def test_default_decay_rate(self):
        p = PatternPersonality()
        # v4.2: N=0.5 -> decay = 1.0 - 0.5 = 0.50
        self.assertAlmostEqual(p.decay_rate, 0.50, places=3)

    def test_stable_decay(self):
        p = PatternPersonality(neuroticism=0.2)
        # v4.2: N=0.2 -> decay = 1.0 - 0.2 = 0.80
        self.assertAlmostEqual(p.decay_rate, 0.80, places=3)

    def test_neurotic_decay(self):
        p = PatternPersonality(neuroticism=0.8)
        # v4.2: N=0.8 -> decay = 1.0 - 0.8 = 0.20
        self.assertAlmostEqual(p.decay_rate, 0.20, places=3)

    def test_composite_score(self):
        p = PatternPersonality(confidence=0.8, agreeableness=0.7, neuroticism=0.2)
        score = p.composite_score
        self.assertGreater(score, 0)
        self.assertLess(score, 1)

    def test_jungian_tiers(self):
        self.assertEqual(PatternPersonality(confidence=0.8, agreeableness=0.6).jungian_tier, 1)
        self.assertEqual(PatternPersonality(confidence=0.6).jungian_tier, 2)
        self.assertEqual(PatternPersonality(confidence=0.3, openness=0.6).jungian_tier, 3)
        self.assertEqual(PatternPersonality(confidence=0.1, openness=0.1).jungian_tier, 4)


class TestPersonalityPatternNode(unittest.TestCase):
    """Behavior: PersonalityPatternNode updates personality on success/failure."""

    def test_record_success(self):
        node = PersonalityPatternNode(error_type="TypeError", error_signature="sig", fix_strategy="fix")
        node.record_success(context="def foo(): pass")
        self.assertEqual(node.times_fixed, 1)
        self.assertGreater(node.personality.confidence, 0.5)

    def test_record_toolbox_failure(self):
        """v4.4: Confidence decays by (1.0 - N), N increases +0.01 within envelope."""
        node = PersonalityPatternNode(
            error_type="TypeError", error_signature="sig", fix_strategy="fix",
            personality=PatternPersonality(confidence=0.8, neuroticism=0.2)
        )
        node.record_toolbox_shown()
        node.record_toolbox_failure()
        # Confidence decays: 0.8 * (1.0 - 0.2) = 0.64
        self.assertAlmostEqual(node.personality.confidence, 0.64, places=5)
        # N increases +0.01 (within ±50% envelope: [0.10, 0.30])
        self.assertAlmostEqual(node.personality.neuroticism, 0.21, places=5)

    def test_neuroticism_self_correcting(self):
        """Success should reduce neuroticism over time."""
        node = PersonalityPatternNode(
            error_type="TypeError", error_signature="sig", fix_strategy="fix",
            personality=PatternPersonality(neuroticism=0.7)
        )
        for _ in range(5):
            node.record_success()
        self.assertLess(node.personality.neuroticism, 0.7)


class TestPersonalityKnowledgeGraph(unittest.TestCase):
    """Behavior: Knowledge graph persists and retrieves patterns."""

    def setUp(self):
        self.tmp_path = tempfile.mktemp(suffix=".json")

    def tearDown(self):
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    def test_empty_graph(self):
        kg = PersonalityKnowledgeGraph(storage_path=self.tmp_path)
        self.assertEqual(len(kg.patterns), 0)
        self.assertAlmostEqual(kg.omega, 0.5)

    def test_record_fix_creates_pattern(self):
        kg = PersonalityKnowledgeGraph(storage_path=self.tmp_path)
        kg.record_fix("TypeError: takes 2 args but 3 given", "def f(): pass", "def f(x): pass")
        self.assertEqual(len(kg.patterns), 1)
        self.assertEqual(kg.patterns[0].times_fixed, 1)

    def test_record_error_existing(self):
        kg = PersonalityKnowledgeGraph(storage_path=self.tmp_path)
        kg.record_fix("NameError: name 'x' is not defined", "print(x)", "print('x')")
        info = kg.record_error("NameError: name 'x' is not defined")
        self.assertTrue(info["existing"])
        self.assertEqual(kg.patterns[0].times_seen, 2)  # 1 from fix + 1 from error

    def test_save_and_load(self):
        kg = PersonalityKnowledgeGraph(storage_path=self.tmp_path)
        kg.record_fix("TypeError: sig", "code1", "code2")
        kg.flush()

        kg2 = PersonalityKnowledgeGraph(storage_path=self.tmp_path)
        self.assertEqual(len(kg2.patterns), 1)
        self.assertEqual(kg2.patterns[0].error_type, "TypeError")

    def test_toolbox_selection(self):
        kg = PersonalityKnowledgeGraph(storage_path=self.tmp_path)
        kg.record_fix("TypeError: takes <N>", "def f(): pass", "def f(x): pass")
        # Set high confidence
        kg.patterns[0].personality.confidence = 0.9
        kg.patterns[0].times_fixed = 3

        text, shown = kg.get_toolbox("TypeError: takes 1 arg but 2 given")
        self.assertGreaterEqual(len(shown), 1)


class TestModelPersonality(unittest.TestCase):
    """Behavior: Model personality aggregates pattern personalities."""

    def test_blank_slate(self):
        mp = ModelPersonality()
        self.assertEqual(mp.tone, "cautious")  # C=0.5, N=0.5 -> cautious
        self.assertEqual(mp.max_toolbox_patterns(), 3)  # C=0.5 -> 3 patterns
        self.assertFalse(mp.should_show_unverified())

    def test_expert_tone(self):
        mp = ModelPersonality(confidence=0.8, neuroticism=0.2)
        self.assertEqual(mp.tone, "authoritative")
        self.assertEqual(mp.max_toolbox_patterns(), 5)

    def test_exploration_bias(self):
        mp = ModelPersonality(openness=0.8, neuroticism=0.2)
        self.assertAlmostEqual(mp.exploration_bias, 0.64, places=2)

    def test_self_awareness_contains_description(self):
        mp = ModelPersonality(confidence=0.6, neuroticism=0.3)
        self.assertIn("expertise", mp.self_awareness.lower())


class TestPersonalityAggregator(unittest.TestCase):
    """Behavior: Aggregator computes model personality from patterns."""

    def test_empty_patterns(self):
        mp = PersonalityAggregator.from_patterns([])
        self.assertEqual(mp.confidence, 0.5)

    def test_single_confident_pattern(self):
        p = PersonalityPatternNode(
            error_type="NameError", error_signature="sig", fix_strategy="fix",
            personality=PatternPersonality(confidence=0.9)
        )
        p.times_fixed = 5
        mp = PersonalityAggregator.from_patterns([p])
        self.assertGreater(mp.confidence, 0.5)

    def test_neuroticism_trauma_awareness(self):
        """One traumatic pattern should raise model neuroticism."""
        p1 = PersonalityPatternNode(
            error_type="NameError", error_signature="sig1", fix_strategy="fix",
            personality=PatternPersonality(confidence=0.8, neuroticism=0.2)
        )
        p2 = PersonalityPatternNode(
            error_type="AssertionError", error_signature="sig2", fix_strategy="fix",
            personality=PatternPersonality(confidence=0.2, neuroticism=0.9)
        )
        mp = PersonalityAggregator.from_patterns([p1, p2])
        # Max neuroticism (0.9) should pull average up
        self.assertGreater(mp.neuroticism, 0.5)

    def test_weighted_confidence(self):
        """Patterns with more fixes should count more toward confidence."""
        p1 = PersonalityPatternNode(
            error_type="NameError", error_signature="sig1", fix_strategy="fix",
            personality=PatternPersonality(confidence=0.9)
        )
        p1.times_fixed = 10
        p2 = PersonalityPatternNode(
            error_type="TypeError", error_signature="sig2", fix_strategy="fix",
            personality=PatternPersonality(confidence=0.3)
        )
        p2.times_fixed = 1
        mp = PersonalityAggregator.from_patterns([p1, p2])
        # Weighted average should be closer to 0.9 than 0.3
        self.assertGreater(mp.confidence, 0.6)


class TestConstraintEngine(unittest.TestCase):
    """Behavior: Constraint engine provides structural hints for local errors."""

    def test_name_error_hint(self):
        ce = HybridConstraintEngine()
        hint = ce.build_toolbox_prompt(
            error_type="NameError", error_sig="name 'fooo' is not defined",
            failing_code="def test():\n    foo = 1\n    return fooo + 1", test_code="",
            locality=0.9, pattern_fix="", pattern_context=""
        )
        self.assertIsNotNone(hint)
        self.assertIn("undefined_name", hint)

    def test_type_error_arity_hint(self):
        ce = HybridConstraintEngine()
        hint = ce.build_toolbox_prompt(
            error_type="TypeError", error_sig="func() takes 2 positional arguments but 3 were given",
            failing_code="def func(a, b):\n    return a + b\n\nfunc(1, 2, 3)", test_code="",
            locality=0.8, pattern_fix="", pattern_context=""
        )
        self.assertIsNotNone(hint)
        self.assertIn("arity", hint.lower())


class TestPuzzleLogicAgent(unittest.TestCase):
    """Behavior: Agent initializes correctly and selects modes."""

    def test_v4_mode_active(self):
        agent = PuzzleLogicAgent(model="test", knowledge_path=tempfile.mktemp(suffix=".json"))
        self.assertTrue(agent.v4_mode)
        self.assertIsNotNone(agent.constraint_engine)
        self.assertIsInstance(agent.constraint_engine, HybridConstraintEngine)

    def test_model_personality_on_init(self):
        agent = PuzzleLogicAgent(model="test", knowledge_path=tempfile.mktemp(suffix=".json"))
        agent.knowledge.refresh_model_personality()
        mp = agent.knowledge.model_personality
        self.assertIsInstance(mp, ModelPersonality)
        self.assertEqual(mp.tone, "cautious")  # empty graph = cautious beginner


class TestEndToEnd(unittest.TestCase):
    """End-to-end: full agent loop without LLM calls."""

    def test_generate_no_test(self):
        """Without test code, agent should return code on first attempt (or fail gracefully)."""
        agent = PuzzleLogicAgent(model="test", knowledge_path=tempfile.mktemp(suffix=".json"))
        result = agent.solve("Write a function that returns 42.", test_code=None, n_attempts=1)
        self.assertIn("code", result)
        self.assertIn("attempts", result)
        # With no real LLM, it may fail extraction - that's OK for this test
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)
