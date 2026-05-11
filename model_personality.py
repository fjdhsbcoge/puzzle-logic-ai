"""
OCEAN-C Personality Engine v4.1 — Dual-Level Personality System
===============================================================

Two personality layers:

  1. MODEL-LEVEL (global) — characterizes the LLM as an agent.
     Computed as aggregates across all patterns. Used for interaction design,
     tone calibration, and meta-cognitive self-awareness.

  2. PATTERN-LEVEL (local) — characterizes individual error-fix patterns.
     Used for toolbox selection, decay rates, and Jungian reassembly.

Model-level personality answers: "What kind of agent am I?"
  - High O: Explorer — suggests novel patterns, takes risks
  - Low O: Specialist — sticks to proven patterns, conservative
  - High C: Confident — speaks with authority, high trust in knowledge
  - Low C: Humble — tentative, asks user to verify
  - High E: Relational — "this reminds me of...", cross-domain analogies
  - Low E: Literal — exact matches, no embellishment
  - High A: Compliant — toolbox suggestions are followed by LLM
  - Low A: Stubborn — LLM resists hints, needs raw error instead
  - High N: Volatile — knowledge shifts rapidly, model is "moody"
  - Low N: Stable — consistent performance, reliable expertise

Pattern-level personality answers: "What kind of pattern is this?"
  (As implemented in v4.0 personality_engine.py)

References:
  - docs/CHANGELOG.md (v2.4 Omega → C transition)
  - personality_engine.py (PatternPersonality, v4.0)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from collections import deque

try:
    from ocean_config import ModelDefaults as _MD, ModelBehavior as _MB
except ImportError:
    class _MD:
        OPENNESS = 0.35
        CONFIDENCE = 0.50
        EXTRAVERSION = 0.50
        AGREEABLENESS = 0.50
        NEUROTICISM = 0.50

    class _MB:
        TONE_AUTHORITATIVE_CONFIDENCE = 0.70
        TONE_AUTHORITATIVE_NEUROTICISM_MAX = 0.40
        TONE_CONFIDENT_CONFIDENCE = 0.55
        TONE_CONFIDENT_NEUROTICISM_MAX = 0.60
        TONE_CAUTIOUS_CONFIDENCE = 0.30
        SHOW_UNVERIFIED_CONFIDENCE = 0.50
        SHOW_UNVERIFIED_NEUROTICISM_MAX = 0.50
        SHOW_UNVERIFIED_OPENNESS_MIN = 0.40
        TOOLBOX_SIZE_HIGH = 5
        TOOLBOX_SIZE_MEDIUM = 3
        TOOLBOX_SIZE_LOW = 2
        TEMP_CONSERVATIVE = 0.0
        TEMP_EXPLORATORY = 0.2
        NEUROTICISM_MAX_BLEND = 0.40
        CONFIDENCE_WEIGHTED_BLEND = 0.70
        AGREEABLENESS_WEIGHTED_BLEND = 0.70
        INTROVERT_DAMPING_RATIO = 0.70
        INTROVERT_DAMPING_FACTOR = 0.80

# ═══════════════════════════════════════════════════════════════════════
#  MODEL-LEVEL PERSONALITY (The Agent's Character)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ModelPersonality:
    """
    The aggregate personality of the Puzzle Logic agent itself.
    Computed from all pattern personalities in the knowledge graph.
    Used for interaction design, tone, and meta-cognitive behaviour.
    """
    openness:      float = _MD.OPENNESS
    confidence:    float = _MD.CONFIDENCE
    extraversion:  float = _MD.EXTRAVERSION
    agreeableness: float = _MD.AGREEABLENESS
    neuroticism:   float = _MD.NEUROTICISM

    # ── Interaction Design Properties ───────────────────────────────

    @property
    def tone(self) -> str:
        """
        Suggest interaction tone based on confidence and neuroticism.
        Returns one of: 'authoritative', 'confident', 'cautious', 'tentative'
        """
        if self.confidence >= 0.7 and self.neuroticism <= 0.4:
            return "authoritative"
        elif self.confidence >= 0.55 and self.neuroticism <= 0.6:
            return "confident"
        elif self.confidence >= 0.3:
            return "cautious"
        else:
            return "tentative"

    @property
    def orientation(self) -> str:
        """
        v4.5 ORIENTATION: How the model directs its attention.
        
        Low confidence  → Outward-looking (observe environment, learn)
        Mid confidence  → Balanced (observe + verify against knowledge)
        High confidence → Inward-looking (trust proven patterns, act)
        
        The shift is gradual, not binary. Confidence is the dimmer switch.
        """
        if self.confidence >= 0.7:
            return "inward"
        elif self.confidence >= 0.4:
            return "balanced"
        else:
            return "outward"

    def orientation_instruction(self) -> str:
        """
        Generate a prompt fragment that guides the model's attention
        direction based on its current orientation.
        """
        orient = self.orientation
        if orient == "outward":
            return (
                "ORIENTATION: You are in OBSERVE mode. Your internal knowledge "
                "is still forming. Look carefully at the error message, the test "
                "expectations, and the code structure. Before applying any fix, "
                "first understand what the environment is telling you. Parse the "
                "error type, identify the structural mismatch, and build your "
                "understanding from the outside in."
            )
        elif orient == "balanced":
            return (
                "ORIENTATION: You are in BALANCE mode. You have some proven "
                "patterns, but not enough to rely on memory alone. Check your "
                "toolbox for relevant insights, but verify each suggestion against "
                "the actual code and error. Cross-reference: does the principle "
                "match the structural problem you see in the environment?"
            )
        else:  # inward
            return (
                "ORIENTATION: You are in TRUST mode. You have deep, verified "
                "knowledge. The patterns in your toolbox have proven themselves "
                "many times. When you see a familiar error structure, apply the "
                "corresponding fix confidently. Your memory is your strength — "
                "draw on it decisively."
            )

    @property
    def exploration_bias(self) -> float:
        """
        How likely the model is to suggest novel/unverified patterns.
        High openness + low neuroticism = more exploration.
        """
        return self.openness * (1.0 - self.neuroticism)
        """
        How likely the model is to suggest novel/unverified patterns.
        High openness + low neuroticism = more exploration.
        """
        return self.openness * (1.0 - self.neuroticism)

    @property
    def self_awareness(self) -> str:
        """
        A natural-language description of the model's current character.
        For logging, UI display, or user communication.
        """
        parts = []

        # Confidence archetype
        if self.confidence >= 0.7:
            parts.append("an expert with deep accumulated knowledge")
        elif self.confidence >= 0.5:
            parts.append("a competent practitioner with growing expertise")
        elif self.confidence >= 0.3:
            parts.append("a learner still building reliable patterns")
        else:
            parts.append("a novice exploring mostly unverified territory")

        # Stability
        if self.neuroticism <= 0.3:
            parts.append("stable and consistent")
        elif self.neuroticism <= 0.6:
            parts.append("moderately volatile")
        else:
            parts.append("still finding its footing")

        # Style
        if self.extraversion >= 0.6:
            parts.append("draws connections across domains")
        else:
            parts.append("works from direct experience")

        if self.agreeableness >= 0.6:
            parts.append("and generally follows its own advice well")
        elif self.agreeableness <= 0.4:
            parts.append("but sometimes resists its own suggestions")

        return f"This model is {', '.join(parts)}."

    # ── Meta-cognitive Behaviour ────────────────────────────────────

    def should_show_unverified(self) -> bool:
        """
        Whether to include unverified patterns (times_fixed == 0) in toolbox.
        Only confident, stable, open models should venture into the unknown.
        """
        return (
            self.confidence >= _MB.SHOW_UNVERIFIED_CONFIDENCE
            and self.neuroticism <= _MB.SHOW_UNVERIFIED_NEUROTICISM_MAX
            and self.openness >= _MB.SHOW_UNVERIFIED_OPENNESS_MIN
        )

    def max_toolbox_patterns(self) -> int:
        """How many patterns to show. Confident models show more."""
        if self.confidence >= 0.7:
            return _MB.TOOLBOX_SIZE_HIGH
        elif self.confidence >= 0.5:
            return _MB.TOOLBOX_SIZE_MEDIUM
        else:
            return 2

    def retry_temperature(self) -> float:
        """
        Suggested LLM temperature for retry attempts.
        High neuroticism → lower temperature (play it safe).
        High openness → higher temperature (explore alternatives).
        """
        base = 0.0
        if self.neuroticism > 0.6:
            base = 0.0  # conservative
        elif self.openness > 0.6:
            base = 0.2  # some exploration
        return base

    # ── Serialization ───────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "openness": self.openness,
            "confidence": self.confidence,
            "extraversion": self.extraversion,
            "agreeableness": self.agreeableness,
            "neuroticism": self.neuroticism,
            "tone": self.tone,
            "self_awareness": self.self_awareness,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ModelPersonality":
        return cls(
            openness=d.get("openness", 0.35),
            confidence=d.get("confidence", 0.50),
            extraversion=d.get("extraversion", 0.50),
            agreeableness=d.get("agreeableness", 0.50),
            neuroticism=d.get("neuroticism", 0.50),
        )

    def __repr__(self) -> str:
        return (f"Model[O={self.openness:.2f} C={self.confidence:.2f} "
                f"E={self.extraversion:.2f} A={self.agreeableness:.2f} "
                f"N={self.neuroticism:.2f} | tone={self.tone}]")


# ═══════════════════════════════════════════════════════════════════════
#  PERSONALITY COMPUTATION (Aggregate from Patterns)
# ═══════════════════════════════════════════════════════════════════════

class PersonalityAggregator:
    """
    Computes model-level personality from a collection of patterns.
    Not a simple average — some traits are weighted by importance.
    """

    @staticmethod
    def from_patterns(patterns: list) -> ModelPersonality:
        """
        Compute model personality from a list of PersonalityPatternNode objects.
        """
        if not patterns:
            return ModelPersonality()  # default blank slate

        n = len(patterns)

        # Raw averages (simple) — start from 0, not defaults
        avg = ModelPersonality()
        avg.openness = 0.0
        avg.confidence = 0.0
        avg.extraversion = 0.0
        avg.agreeableness = 0.0
        avg.neuroticism = 0.0

        for p in patterns:
            pers = p.personality
            avg.openness += pers.openness
            avg.confidence += pers.confidence
            avg.extraversion += pers.extraversion
            avg.agreeableness += pers.agreeableness
            avg.neuroticism += pers.neuroticism

        avg.openness /= n
        avg.confidence /= n
        avg.extraversion /= n
        avg.agreeableness /= n
        avg.neuroticism /= n

        # Weighted confidence: patterns with more fixes count more
        # (they represent "proven" knowledge)
        total_fixes = sum(p.times_fixed for p in patterns)
        if total_fixes > 0:
            weighted_c = sum(
                p.personality.confidence * p.times_fixed
                for p in patterns
            ) / total_fixes
            # Blend: 70% weighted, 30% simple average
            avg.confidence = 0.7 * weighted_c + 0.3 * avg.confidence

        # Weighted agreeableness: patterns shown more count more
        # (they represent actual interaction history)
        total_shown = sum(p.times_shown for p in patterns)
        if total_shown > 0:
            weighted_a = sum(
                p.personality.agreeableness * p.times_shown
                for p in patterns
            ) / total_shown
            b = _MB.AGREEABLENESS_WEIGHTED_BLEND
            avg.agreeableness = b * weighted_a + (1 - b) * avg.agreeableness

        # Neuroticism: if ANY highly-neurotic pattern exists, it pulls the
        # whole model up (one traumatic pattern makes the whole system anxious)
        max_n = max(p.personality.neuroticism for p in patterns)
        b = _MB.NEUROTICISM_MAX_BLEND
        avg.neuroticism = (1 - b) * avg.neuroticism + b * max_n

        # v4.5 CREATIVE MODE: Extraversion is now positively weighted.
        # We do NOT dampen extraversion — omega/relational patterns are
        # creative ingredients, and their presence should be fully counted.
        # The model's extraversion reflects the graph's willingness to make
        # novel cross-domain associations.

        # Clamp all to [0, 1]
        for trait in ["openness", "confidence", "extraversion", "agreeableness", "neuroticism"]:
            setattr(avg, trait, max(0.0, min(1.0, getattr(avg, trait))))

        return avg

    @staticmethod
    def personality_evolution_history(
        historical_graphs: List[dict]
    ) -> List[Dict]:
        """
        Track how model personality evolved over time.
        Pass a list of historical knowledge graph dicts.
        Returns list of {timestamp, personality} snapshots.
        """
        from personality_engine import PersonalityPatternNode

        snapshots = []
        for graph_data in historical_graphs:
            timestamp = graph_data.get("timestamp", "unknown")
            patterns = [
                PersonalityPatternNode.from_dict(p)
                for p in graph_data.get("patterns", [])
            ]
            personality = PersonalityAggregator.from_patterns(patterns)
            snapshots.append({
                "timestamp": timestamp,
                "personality": personality.to_dict(),
                "n_patterns": len(patterns),
            })
        return snapshots


# ═══════════════════════════════════════════════════════════════════════
#  PERSONALITY-AWARE INTERACTION PROMPT BUILDER
# ═══════════════════════════════════════════════════════════════════════

class PersonalityPromptBuilder:
    """
    Builds prompts that adapt to the model's current personality.
    The model speaks differently about itself and its knowledge
    depending on its aggregate character.
    """

    def __init__(self, model_personality: ModelPersonality):
        self.mp = model_personality

    def system_prompt(self) -> str:
        """
        Generate a system prompt that reflects the model's self-awareness.
        """
        tone = self.mp.tone
        parts = ["You are a helpful coding assistant."]

        # v4.5: Orientation guides how the model directs its attention
        parts.append(self.mp.orientation_instruction())

        if tone == "authoritative":
            parts.append(
                "You have extensive experience with common coding errors. "
                "When you recognize a pattern, state the fix clearly and confidently."
            )
        elif tone == "confident":
            parts.append(
                "You have learned from many past fixes. Apply what you know, "
                "but stay open to unusual cases."
            )
        elif tone == "cautious":
            parts.append(
                "You are still learning which fixes work reliably. "
                "Suggest changes, but verify they make sense for this specific code."
            )
        else:  # tentative
            parts.append(
                "You are exploring solutions. Try what seems reasonable, "
                "and be prepared to reconsider if it doesn't work."
            )

        if self.mp.openness >= 0.6:
            parts.append(
                "You excel at drawing analogies between different types of problems."
            )

        if self.mp.agreeableness < 0.4:
            parts.append(
                "Trust your own reasoning. Past hints don't always apply directly."
            )

        return " ".join(parts)

    def toolbox_prefix(self) -> str:
        """
        How the model introduces toolbox suggestions.
        Depends on confidence and agreeableness.
        """
        if self.mp.confidence >= 0.7 and self.mp.agreeableness >= 0.5:
            return "Based on proven patterns, try this fix:"
        elif self.mp.confidence >= 0.5:
            return "A similar error was previously fixed by:"
        else:
            return "One approach that has worked before (verify it fits):"

    def failure_reaction(self, error_text: str) -> str:
        """
        How the model reacts when its suggested fix fails.
        Depends on neuroticism and confidence.
        """
        if self.mp.neuroticism > 0.7:
            return (
                "That didn't work — let me reconsider. The pattern I applied "
                "may not fit this case. I'll try a different approach."
            )
        elif self.mp.confidence > 0.5:
            return (
                "The fix didn't resolve it. Let me look closer at the specific "
                "error and adjust the approach."
            )
        else:
            return (
                "Still failing. Let me step back and analyze the error "
                "from first principles rather than applying a pattern."
            )

    def success_reflection(self, pattern_id: str) -> str:
        """
        Internal monologue when a fix succeeds.
        For logging or chain-of-thought display.
        """
        if self.mp.confidence >= 0.6:
            return f"Pattern {pattern_id} confirmed. Knowledge deepening."
        else:
            return f"Fix succeeded. Noting pattern {pattern_id} for future use."


# ═══════════════════════════════════════════════════════════════════════
#  INTEGRATION: ModelPersonality + PersonalityKnowledgeGraph
# ═══════════════════════════════════════════════════════════════════════

class PersonalityAwareKnowledgeGraph:
    """
    Wraps PersonalityKnowledgeGraph with model-level personality awareness.
    This is the class PuzzleLogicAgent should use.
    """

    def __init__(self, pattern_graph):
        """
        pattern_graph: a PersonalityKnowledgeGraph instance.
        """
        self.patterns = pattern_graph
        self.model_personality = self._compute_model_personality()
        self.prompt_builder = PersonalityPromptBuilder(self.model_personality)

    def _compute_model_personality(self) -> ModelPersonality:
        return PersonalityAggregator.from_patterns(self.patterns.patterns)

    def refresh_model_personality(self):
        """Recompute after significant changes (e.g., after reassembly)."""
        self.model_personality = self._compute_model_personality()
        self.prompt_builder = PersonalityPromptBuilder(self.model_personality)

    def get_system_prompt(self) -> str:
        return self.prompt_builder.system_prompt()

    def get_toolbox(self, error_text: str, failing_code: str = "",
                    top_k: int = None, llm_client=None) -> tuple:
        """
        Get toolbox with model-personality-aware settings.
        """
        if top_k is None:
            top_k = self.model_personality.max_toolbox_patterns()

        # Optionally include unverified if model is exploratory
        min_score = 0.0
        if not self.model_personality.should_show_unverified():
            min_score = 0.15  # filter out weak patterns

        return self.patterns.get_toolbox(
            error_text, failing_code, top_k=top_k,
            min_score=min_score, llm_client=llm_client
        )

    def print_model_character(self):
        """Print a human-readable character summary."""
        mp = self.model_personality
        print(f"\n{'='*60}")
        print("  MODEL CHARACTER PROFILE")
        print(f"{'='*60}")
        print(f"  OCEAN-C: {mp}")
        print(f"")
        print(f"  Self-awareness: {mp.self_awareness}")
        print(f"  Exploration bias: {mp.exploration_bias:.2f}")
        print(f"  Retry temperature: {mp.retry_temperature()}")
        print(f"  Max toolbox patterns: {mp.max_toolbox_patterns()}")
        print(f"  Show unverified: {mp.should_show_unverified()}")
        print(f"{'='*60}")
