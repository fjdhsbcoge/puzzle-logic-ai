"""
OCEAN-C Personality Engine for Puzzle Logic Knowledge Graph v4.2
=================================================================

Each ErrorPatternNode has a 5-dimensional personality profile:
  O - Openness:      Cross-context applicability
  C - Confidence:    Verified reliability (earned trust)
  E - Extraversion:  Inward (direct match) vs outward (omega/relational) orientation
  A - Agreeableness: LLM's willingness to follow this pattern's advice (emergent)
  N - Neuroticism:   Decay rate on failure (emotional instability)

Toolbox selection uses composite personality scoring instead of flat confidence.
Reassembly recalibrates the full personality profile by Jungian tier.
Neuroticism controls per-pattern decay: decay_rate = 1.0 - N

All tunable parameters are imported from ocean_config.py — edit that file
and restart the agent to change personality behavior.

References:
  - Jungian tiers: docs/CHANGELOG.md (v2.4 section)
  - Original confidence system: puzzle_logic_agent.py (CoherentKnowledgeGraph)
"""

import json
import os
import re
from collections import deque, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from utils import (
    extract_error_fingerprint,
    infer_fix_strategy,
    compute_locality,
    compute_fix_complexity,
    code_delta,
    same_pattern,
    sig_similarity,
    extract_func_name,
    summarize_fix_principle,
)

# ═══════════════════════════════════════════════════════════════════════
#  Import tunable parameters from central config
# ═══════════════════════════════════════════════════════════════════════

try:
    from ocean_config import (
        PatternDynamics as _PD,
        CompositeWeights as _CW,
        JungianTiers as _JT,
        Reassembly as _RA,
        EPIGENETIC_PROFILES,
        EPIGENETIC_FALLBACK,
    )
except ImportError:
    # Fallback defaults if ocean_config.py is missing
    class _PD:
        SUCCESS_CONFIDENCE_BOOST = 0.10
        NEWBORN_CONFIDENCE_DECAY = 0.81
        NEUROTICISM_STEP = 0.01
        NEUROTICISM_MIN = 0.20
        NEUROTICISM_MAX = 0.80
        OPENNESS_SUCCESS_DELTA = 0.14

    class _CW:
        OPENNESS = 0.15
        CONFIDENCE = 0.35
        EXTRAVERSION = -0.10
        AGREEABLENESS = 0.25
        NEUROTICISM = -0.15
        FLOOR = 0.08

    class _JT:
        ESTABLISHED_MIN_CONFIDENCE = 0.70
        ESTABLISHED_MIN_AGREEABLENESS = 0.50
        MIDDELING_MIN_CONFIDENCE = 0.50
        BURIED_MAX_CONFIDENCE = 0.50
        BURIED_MIN_CONFIDENCE = 0.20
        BURIED_MIN_OPENNESS = 0.30

    class _RA:
        ESTABLISHED_CONFIDENCE_NUDGE = -0.15
        ESTABLISHED_CONFIDENCE_FLOOR = 0.55
        ESTABLISHED_NEUROTICISM_CAP = 0.40
        MIDDELING_CONFIDENCE_RESET = 0.50
        MIDDELING_OPENNESS_BOOST = 0.05
        BURIED_CONFIDENCE_LIFELINE_LOW = 0.30
        BURIED_CONFIDENCE_LIFELINE_HIGH = 0.40
        BURIED_NEUROTICISM_REDUCTION = 0.05
        BURIED_OPENNESS_BOOST = 0.10
        SHADOW_CONFIDENCE_WHISPER = 0.20
        SHADOW_NEUROTICISM_GENTLE = 0.02

    EPIGENETIC_PROFILES = {}
    EPIGENETIC_FALLBACK = (0.35, 0.50, 0.50, 0.50, 0.20)


# ═══════════════════════════════════════════════════════════════════════
#  PATTERN PERSONALITY (OCEAN-C Five-Vector)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class PatternPersonality:
    """
    Five-dimensional personality profile for a knowledge graph pattern.
    All traits range [0.0, 1.0].

    v4.4+: Neuroticism varies within ±50% of its birth value.
    N can shift gently (+0.01 failure, -0.01 success) but never
    escapes the envelope [birth_N * 0.5, birth_N * 1.5].
    """
    openness:      float = 0.35  # O: cross-context exploration
    confidence:    float = 0.50  # C: verified reliability
    extraversion:  float = 0.50  # E: outward (omega) vs inward (direct) orientation
    agreeableness: float = 0.50  # A: LLM compliance rate (emergent)
    neuroticism:   float = 0.50  # N: instability → controls decay rate
    _birth_neuroticism: float = field(default=-1.0, repr=False)
    # _birth_N = -1.0 means "not set yet" — used to detect old patterns on load

    def __post_init__(self):
        # Capture birth N to define the ±50% envelope.
        # Only set if not already explicitly provided (> 0 means valid).
        if self._birth_neuroticism <= 0.0:
            self._birth_neuroticism = self.neuroticism

    @property
    def decay_rate(self) -> float:
        """
        v4.4: Simple linear decay bounded by N envelope.
        N=0.10 → decay=0.90 (calm, loses 10% per failure)
        N=0.20 → decay=0.80 (stable, loses 20% per failure)
        N=0.30 → decay=0.70 (anxious, loses 30% per failure)
        """
        return 1.0 - self.neuroticism

    @property
    def n_min(self) -> float:
        """Lower bound of N envelope: 50% of birth value (floored at 0.05)."""
        return max(0.05, self._birth_neuroticism * 0.5)

    @property
    def n_max(self) -> float:
        """Upper bound of N envelope: 150% of birth value (capped at 1.0)."""
        return min(1.0, self._birth_neuroticism * 1.5)

    @property
    def composite_score(self, weights: Optional[Dict[str, float]] = None) -> float:
        """
        Weighted composite for toolbox selection. Default weights favor
        confident, agreeable, stable patterns with moderate openness.
        """
        w = weights or {
            "openness": 0.15,
            "confidence": 0.35,
            "extraversion": -0.10,  # inverted: introverts more reliable
            "agreeableness": 0.25,
            "neuroticism": -0.15,   # inverted: stable patterns preferred
        }
        return (
            w.get("openness", 0.15) * self.openness +
            w.get("confidence", 0.35) * self.confidence +
            w.get("extraversion", -0.10) * self.extraversion +
            w.get("agreeableness", 0.25) * self.agreeableness +
            w.get("neuroticism", -0.15) * self.neuroticism
        )

    @property
    def jungian_tier(self) -> int:
        """
        Map personality profile to Jungian consciousness tier.
        1=Established, 2=Middling, 3=Buried, 4=Shadow
        Thresholds imported from ocean_config.JungianTiers.
        """
        if (self.confidence >= _JT.ESTABLISHED_MIN_CONFIDENCE
                and self.agreeableness >= _JT.ESTABLISHED_MIN_AGREEABLENESS):
            return 1  # Established
        elif self.confidence >= _JT.MIDDELING_MIN_CONFIDENCE:
            return 2  # Middling
        elif (self.confidence < _JT.BURIED_MAX_CONFIDENCE
              and (self.confidence > _JT.BURIED_MIN_CONFIDENCE
                   or self.openness > _JT.BURIED_MIN_OPENNESS)):
            return 3  # Buried
        else:
            return 4  # Shadow

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PatternPersonality":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def epigenetic_for(cls, error_type: str) -> "PatternPersonality":
        """Get the epigenetic starting personality for an error type."""
        if not hasattr(cls, '_EPIGENETIC_DEFAULTS'):
            # Fallback if monkey-patch hasn't happened yet
            return _make_epigenetic(error_type)
        return cls._EPIGENETIC_DEFAULTS.get(error_type, PatternPersonality())

    def __repr__(self) -> str:
        return (f"[O={self.openness:.2f} C={self.confidence:.2f} "
                f"E={self.extraversion:.2f} A={self.agreeableness:.2f} "
                f"N={self.neuroticism:.2f} tier={self.jungian_tier}]")


# ── Epigenetic domain defaults ─────────────────────────────────────────
# Each error type is an "environment" that shapes a pattern's starting personality.
# Simple/local errors (NameError, SyntaxError) start confident and stable.
# Complex/unlocal errors (AssertionError, RecursionError) start curious but neurotic.

# Use epigenetic defaults from ocean_config.py if available, else inline.
_EPIGENETIC_PROFILES = EPIGENETIC_PROFILES if EPIGENETIC_PROFILES else {
    # Fallback defaults — only used if ocean_config.py is missing.
    "NameError":      (0.40, 0.60, 0.20, 0.50, 0.20),
    "SyntaxError":    (0.35, 0.70, 0.20, 0.50, 0.20),
    "IndentationError": (0.30, 0.75, 0.15, 0.50, 0.20),
    "TypeError":      (0.50, 0.55, 0.30, 0.50, 0.20),
    "IndexError":     (0.45, 0.50, 0.25, 0.50, 0.20),
    "KeyError":       (0.45, 0.50, 0.25, 0.50, 0.20),
    "ValueError":     (0.50, 0.45, 0.30, 0.50, 0.20),
    "AttributeError": (0.50, 0.45, 0.30, 0.50, 0.20),
    "ImportError":    (0.40, 0.60, 0.20, 0.50, 0.20),
    "ModuleNotFoundError": (0.40, 0.60, 0.20, 0.50, 0.20),
    "RecursionError": (0.60, 0.30, 0.40, 0.50, 0.20),
    "TimeoutError":   (0.60, 0.30, 0.40, 0.50, 0.20),
    "ZeroDivisionError": (0.40, 0.55, 0.25, 0.50, 0.20),
    "AssertionError": (0.60, 0.50, 0.40, 0.50, 0.20),
}


def _make_epigenetic(error_type: str) -> PatternPersonality:
    """Factory: create epigenetic starting personality for an error type."""
    o, c, e, a, n = _EPIGENETIC_PROFILES.get(error_type, EPIGENETIC_FALLBACK)
    return PatternPersonality(openness=o, confidence=c, extraversion=e, agreeableness=a, neuroticism=n)


PatternPersonality._EPIGENETIC_DEFAULTS = {
    k: PatternPersonality(openness=o, confidence=c, extraversion=e, agreeableness=a, neuroticism=n)
    for k, (o, c, e, a, n) in _EPIGENETIC_PROFILES.items()
}


# ═══════════════════════════════════════════════════════════════════════
#  PERSONALITY-AWARE ERROR PATTERN NODE
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class PersonalityPatternNode:
    """
    An error-fix pattern with a full OCEAN-C personality profile.
    Replaces ErrorPatternNode from puzzle_logic_agent.py.
    """
    # Identity
    error_type:      str = ""
    error_signature: str = ""
    failing_line:    str = ""
    fix_strategy:    str = ""
    context:         str = ""

    # Personality (the 5-vector)
    personality: PatternPersonality = field(default_factory=PatternPersonality)

    # History (for computing personality dynamics)
    times_seen:       int = 1
    times_fixed:      int = 0
    times_shown:      int = 0       # how many times in toolbox
    times_followed:   int = 0       # LLM actually implemented the fix
    direct_selections: int = 0       # selected by fingerprint match
    omega_selections:  int = 0       # selected via omega/relational boost
    times_synthesized: int = 0      # v4.5: part of cross-domain creative synthesis
    successful_contexts: List[str] = field(default_factory=list)

    # Temporal
    timestamp:    str = field(default_factory=lambda: datetime.now().isoformat())
    last_used:    str = ""
    result_history: deque = field(default_factory=lambda: deque(maxlen=20))  # last 20 outcomes

    # Legacy compatibility
    locality:     float = 0.5

    @property
    def confidence(self) -> float:
        """Legacy accessor — delegates to personality.confidence."""
        return self.personality.confidence

    @confidence.setter
    def confidence(self, value: float):
        self.personality.confidence = value

    # ── Personality update methods ──────────────────────────────────

    def record_success(self, context: str = ""):
        """Call when this pattern's fix succeeds."""
        self.times_fixed += 1
        self.result_history.append(True)

        # C - Confidence: absolute boost on success (capped at 1.0)
        self.personality.confidence = min(
            1.0, self.personality.confidence + _PD.SUCCESS_CONFIDENCE_BOOST
        )

        # O - Openness: if context is new, increase openness
        if context and context not in self.successful_contexts:
            self.successful_contexts.append(context)
            self.personality.openness = min(
                1.0, self.personality.openness + _PD.OPENNESS_SUCCESS_DELTA
            )

        # A - Agreeableness: the LLM followed and it worked
        if self.times_shown > 0:
            self.times_followed += 1
            self.personality.agreeableness = (
                self.times_followed / self.times_shown
            )

        # N - Neuroticism: success calms the pattern (within ±50% envelope)
        self.personality.neuroticism = max(
            self.personality.n_min,
            self.personality.neuroticism - _PD.NEUROTICISM_STEP
        )

    def record_toolbox_shown(self, selected_via_omega: bool = False):
        """Call when this pattern appears in the toolbox."""
        self.times_shown += 1
        if selected_via_omega:
            self.omega_selections += 1
        else:
            self.direct_selections += 1

        # E - Extraversion: ratio of omega vs direct selections
        total = self.direct_selections + self.omega_selections
        if total > 0:
            self.personality.extraversion = self.omega_selections / total

    def record_toolbox_failure(self):
        """
        Call when this pattern was shown but the overall fix still failed.

        v4.4: Bidirectional N within ±50% envelope of birth value.
        Failure: N += 0.01 (capped at n_max = birth_N * 1.5)
        Success: N -= 0.01 (floored at n_min = birth_N * 0.5)
        Decay = 1.0 - N varies gently within [0.70, 0.90].
        No compounding death spiral — N is bounded.
        """
        self.result_history.append(False)

        # Apply personality-controlled decay to confidence
        decay = self.personality.decay_rate  # = 1.0 - N (varies gently)
        self.personality.confidence *= decay

        # N - Neuroticism: failure makes pattern slightly more anxious
        # (within ±50% envelope — never escapes birth band)
        self.personality.neuroticism = min(
            self.personality.n_max,
            self.personality.neuroticism + _PD.NEUROTICISM_STEP
        )
        if self.times_shown > 0:
            self.personality.agreeableness = (
                self.times_followed / self.times_shown
            )

    def record_synthesis(self):
        """
        v4.5: Call when this pattern was shown alongside patterns from
        OTHER error types AND the overall fix succeeded.
        This pattern contributed to a creative cross-domain synthesis.
        """
        self.times_synthesized += 1

    def record_error_observation(self):
        """Call when the error this pattern matches is seen again."""
        self.times_seen += 1

    # ── Internal helpers ────────────────────────────────────────────

    def _recent_success_rate(self, window: int = 10) -> float:
        recent = list(self.result_history)[-window:]
        if not recent:
            return 0.5
        return sum(recent) / len(recent)

    # ── Serialization ───────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = {
            "error_type": self.error_type,
            "error_signature": self.error_signature,
            "failing_line": self.failing_line,
            "fix_strategy": self.fix_strategy,
            "context": self.context,
            "personality": self.personality.to_dict(),
            "times_seen": self.times_seen,
            "times_fixed": self.times_fixed,
            "times_shown": self.times_shown,
            "times_followed": self.times_followed,
            "direct_selections": self.direct_selections,
            "omega_selections": self.omega_selections,
            "times_synthesized": self.times_synthesized,
            "successful_contexts": self.successful_contexts[-20:],  # keep last 20
            "timestamp": self.timestamp,
            "last_used": self.last_used,
            "locality": self.locality,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PersonalityPatternNode":
        node = cls(
            error_type=d.get("error_type", ""),
            error_signature=d.get("error_signature", ""),
            failing_line=d.get("failing_line", ""),
            fix_strategy=d.get("fix_strategy", ""),
            context=d.get("context", ""),
            personality=PatternPersonality.from_dict(
                d.get("personality", {})
            ),
            times_seen=d.get("times_seen", 1),
            times_fixed=d.get("times_fixed", 0),
            times_shown=d.get("times_shown", 0),
            times_followed=d.get("times_followed", 0),
            direct_selections=d.get("direct_selections", 0),
            omega_selections=d.get("omega_selections", 0),
            times_synthesized=d.get("times_synthesized", 0),
            successful_contexts=d.get("successful_contexts", []),
            timestamp=d.get("timestamp", datetime.now().isoformat()),
            last_used=d.get("last_used", ""),
            locality=d.get("locality", 0.5),
        )

        # v4.4 migration: old patterns (no _birth_neuroticism in JSON) have
        # corrupted N from the compounding bug. Reset birth_N to epigenetic
        # default and clamp current N within the ±50% envelope.
        pers = node.personality
        raw_personality = d.get("personality", {})
        if "_birth_neuroticism" not in raw_personality:
            # Old pattern — reset birth_N and clamp N to envelope
            epigenetic_n = _EPIGENETIC_PROFILES.get(node.error_type, EPIGENETIC_FALLBACK)[4]
            pers._birth_neuroticism = epigenetic_n
            pers.neuroticism = max(pers.n_min, min(pers.n_max, pers.neuroticism))

        # Restore result_history from counts if migrating from old format
        success_count = d.get("times_fixed", 0)
        fail_count = max(0, d.get("times_shown", 0) - success_count)
        for _ in range(min(success_count, 10)):
            node.result_history.append(True)
        for _ in range(min(fail_count, 10)):
            node.result_history.append(False)
        return node

    def __repr__(self) -> str:
        return (f"PersonalityPattern[{self.error_type}] "
                f"C={self.personality.confidence:.2f} "
                f"fixed={self.times_fixed} shown={self.times_shown} "
                f"{self.personality}")


# ═══════════════════════════════════════════════════════════════════════
#  PERSONALITY-AWARE KNOWLEDGE GRAPH
# ═══════════════════════════════════════════════════════════════════════

class PersonalityKnowledgeGraph:
    """
    v4.0 — OCEAN-C personality-based knowledge graph.
    Replaces CoherentKnowledgeGraph from puzzle_logic_agent.py.

    Key differences from v3.5:
      - Patterns have 5-dimensional personalities, not flat confidence
      - Toolbox selection uses composite personality scoring
      - Decay is per-pattern (neuroticism-controlled)
      - Reassembly recalibrates full personality profiles
      - Omega revision is now extraversion-aware
    """

    def __init__(self, storage_path: str = "puzzle_logic_knowledge.json"):
        self.storage_path = storage_path
        self.patterns: List[PersonalityPatternNode] = []
        self.by_type: Dict[str, List[PersonalityPatternNode]] = defaultdict(list)
        self._dirty = False
        self._toolbox_failures = defaultdict(int)
        self._load()

    @property
    def omega(self) -> float:
        """
        Omega = weighted average confidence, validated patterns count more.
        Unverified patterns (times_fixed=0) don't drag down the average.
        """
        if not self.patterns:
            return 0.5
        total_fixes = sum(p.times_fixed for p in self.patterns)
        if total_fixes == 0:
            return sum(p.personality.confidence for p in self.patterns) / len(self.patterns)
        weighted = sum(p.personality.confidence * max(1, p.times_fixed) for p in self.patterns)
        total_weight = sum(max(1, p.times_fixed) for p in self.patterns)
        return weighted / total_weight

    @property
    def personality_summary(self) -> Dict:
        """Aggregate personality stats for the entire graph."""
        if not self.patterns:
            return {}
        traits = ["openness", "confidence", "extraversion", "agreeableness", "neuroticism"]
        return {
            t: sum(getattr(p.personality, t) for p in self.patterns) / len(self.patterns)
            for t in traits
        }

    # ── Core recording ──────────────────────────────────────────────

    def record_error(self, error_text: str, context: str = "", code: str = "") -> Dict:
        """Record an error observation. Updates existing patterns only."""
        err_type, err_sig, failing_line = extract_error_fingerprint(error_text)

        for p in self.by_type.get(err_type, []):
            if same_pattern(p.error_signature, err_sig):
                p.record_error_observation()
                self._dirty = True
                return {
                    "type": err_type,
                    "sig": err_sig,
                    "line": failing_line,
                    "locality": p.locality,
                    "existing": True,
                    "personality": p.personality.to_dict(),
                }

        return {
            "type": err_type,
            "sig": err_sig,
            "line": failing_line,
            "locality": compute_locality(err_type, None),
            "existing": False,
        }

    def record_fix(self, error_text: str, failing_code: str = "",
                   fixed_code: str = "", context: str = "",
                   llm_client=None, ingredients: List[PersonalityPatternNode] = None):
        """
        Record a successful fix. Updates personality + creates new patterns.
        
        v4.5: If ingredients are provided and they span multiple error types,
        each ingredient gets a synthesis credit (creative cross-domain fix).
        
        If llm_client is provided, asks the LLM to generalize the fix into a
        reusable principle (e.g., "cast to str() before int()"). Otherwise
        falls back to a raw code diff.
        """
        err_type, err_sig, failing_line = extract_error_fingerprint(error_text)
        delta = code_delta(failing_code, fixed_code)
        locality = compute_locality(err_type, delta)

        # v4.3: Generalize the fix into a reusable principle via LLM
        principle = summarize_fix_principle(
            failing_code=failing_code,
            fixed_code=fixed_code,
            error_type=err_type,
            error_signature=err_sig,
            llm_client=llm_client,
        )
        fix_description = principle if principle else delta if delta else infer_fix_strategy(err_type, err_sig)

        context_snippet = ""
        if failing_code:
            lines = failing_code.strip().split("\n")
            context_snippet = "; ".join(l.strip() for l in lines if l.strip())[:200]

        matched = None
        for p in self.by_type.get(err_type, []):
            if same_pattern(p.error_signature, err_sig):
                p.record_success(context=context_snippet)
                p.locality = locality
                if not p.failing_line and failing_line:
                    p.failing_line = failing_line
                if not p.context and context_snippet:
                    p.context = context_snippet
                # Update fix strategy with the generalized principle
                if principle:
                    p.fix_strategy = principle
                matched = p
                break

        if not matched:
            # New pattern born with inherited personality from domain
            personality = self._inherit_domain_personality(err_type)
            matched = PersonalityPatternNode(
                error_type=err_type,
                error_signature=err_sig,
                failing_line=failing_line,
                fix_strategy=fix_description,
                context=context_snippet,
                personality=personality,
                locality=locality,
            )
            matched.personality.confidence = 0.5
            matched.times_fixed = 0
            matched.record_success(context=context_snippet)
            self.patterns.append(matched)
            self.by_type[err_type].append(matched)

        self._omega_revision(matched)
        self._dirty = True

        # v4.5: If ingredients span multiple error types, credit synthesis
        if ingredients:
            ingredient_types = set(ing.error_type for ing in ingredients)
            if len(ingredient_types) > 1:
                for ing in ingredients:
                    ing.record_synthesis()

        # Reset toolbox failure counter for this error type
        if err_type in self._toolbox_failures:
            del self._toolbox_failures[err_type]

    def record_toolbox_failure(self, shown_patterns: List[PersonalityPatternNode]):
        """Per-pattern neuroticism-controlled decay."""
        if not shown_patterns:
            return

        types = set()
        for p in shown_patterns:
            p.record_toolbox_failure()
            types.add(p.error_type)

        # Log with personality detail
        for err_type in types:
            self._toolbox_failures[err_type] += 1
            avg_n = sum(
                p.personality.neuroticism
                for p in shown_patterns if p.error_type == err_type
            ) / max(1, len([p for p in shown_patterns if p.error_type == err_type]))
            avg_decay = sum(
                p.personality.decay_rate
                for p in shown_patterns if p.error_type == err_type
            ) / max(1, len([p for p in shown_patterns if p.error_type == err_type]))
            print(f"    [PENALTY] {err_type}: {len(shown_patterns)} patterns, "
                  f"avg_N={avg_n:.2f}, decay={avg_decay:.2f}")

            if self._toolbox_failures[err_type] >= 3:
                print(f"    [CRISIS] {err_type}: {self._toolbox_failures[err_type]} "
                      f"toolbox failures. Unconscious surfacing...")
                self._reassembly(err_type)
                self._toolbox_failures[err_type] = 0

        self._dirty = True

    # ── Toolbox: Personality-Weighted Selection ─────────────────────

    def get_toolbox(self, error_text: str, failing_code: str = "",
                    top_k: int = 3, min_score: float = 0.1,
                    llm_client=None) -> Tuple[str, List[PersonalityPatternNode]]:
        """
        v4.5 CREATIVE MODE: Cross-domain synthesis toolbox.

        Instead of showing patterns from the SAME error type (direct copy),
        we gather the best patterns from ALL error types and select top-k
        from DIFFERENT types. The LLM synthesizes a new solution by
        combining insights from diverse verified patterns.

        Returns: (toolbox_text, shown_patterns)
        """
        err_type, err_sig, failing_line = extract_error_fingerprint(error_text)

        # v4.5: Gather candidates from ALL error types (creative ingredients)
        all_candidates = []
        for etype, plist in self.by_type.items():
            for p in plist:
                if p.times_fixed > 0:
                    all_candidates.append(p)

        if not all_candidates:
            return "", []

        # Score all patterns by composite personality
        scored = []
        for p in all_candidates:
            base_score = p.personality.composite_score
            if base_score < _CW.FLOOR:
                continue
            sig_sim = sig_similarity(p.error_signature, err_sig)
            selected_via_omega = (sig_sim < 0.8)
            p.record_toolbox_shown(selected_via_omega=selected_via_omega)
            scored.append((base_score, p))

        # Sort by score descending
        scored.sort(key=lambda x: -x[0])

        # v4.5: Select top-k from DIFFERENT error types (cross-domain synthesis)
        shown = []
        used_types = set()
        for score, p in scored:
            if len(shown) >= top_k:
                break
            if score < min_score:
                continue
            # Prefer patterns from different error types (creative diversity)
            if p.error_type not in used_types or len(used_types) >= top_k:
                shown.append(p)
                used_types.add(p.error_type)

        if not shown:
            return "", []

        # Build creative synthesis prompt
        # v4.5: Include model orientation (outward/balanced/inward)
        # Lazy import to avoid circular dependency with model_personality
        try:
            from model_personality import PersonalityAggregator
            model_pers = PersonalityAggregator.from_patterns(self.patterns).to_model_personality()
            orient_text = model_pers.orientation_instruction()
        except Exception:
            orient_text = ""

        orient_lines = [orient_text] if orient_text else []

        lines = [
            f"[Creative Toolbox — Synthesis Ingredients]",
            f"Your current error: {err_sig[:120]}",
            "",
        ] + orient_lines + [
            "CREATIVITY RULE: Do not copy any single fix below. "
            "Instead, combine insights from multiple ingredients into a "
            "solution that has never been tried before in this exact form.",
            "",
            "LEGEND:\n"
            "  C (Confidence) = How many times this fix has worked before.\n"
            "  A (Agreeableness) = How often the model followed this advice and it worked.\n"
            "  Source = Which error type this insight comes from (cross-domain = creative).",
            "",
            "SYNTHESIZE: Scan YOUR current code. Find the structural problem. "
            "Then blend the relevant ingredients into a NEW solution. "
            "Output the complete fixed function.",
            "",
        ]

        for i, p in enumerate(shown, 1):
            func_name = extract_func_name(p.failing_line) or "function"
            fix_desc = p.fix_strategy[:200] if p.fix_strategy else "(no description)"
            pers = p.personality

            lines.append(
                f"  Ingredient {i} [{p.error_type}]:\n"
                f"    Principle: {fix_desc}\n"
                f"    Trust: C={pers.confidence:.2f} A={pers.agreeableness:.2f} "
                f"(proven {p.times_fixed}x)"
            )

        lines.append("")
        lines.append(
            "CREATE: Combine ingredients above into a solution for YOUR code. "
            "Do not copy verbatim — synthesize something new. "
            "Output the complete fixed function."
        )

        return "\n".join(lines), shown

    # ── Jungian Reassembly (Personality Recalibration) ──────────────

    def _reassembly(self, error_type: str):
        """
        The unconscious surfacing in layers. Recalibrates full personality
        profiles by tier. Nothing is ever truly forgotten.
        """
        tiers = {1: 0, 2: 0, 3: 0, 4: 0}

        for p in self.by_type.get(error_type, []):
            old = p.personality
            tier = old.jungian_tier
            tiers[tier] += 1

            if tier == 1:
                # Established: gentle nudge, stay stable
                old.confidence = max(
                    _RA.ESTABLISHED_CONFIDENCE_FLOOR,
                    old.confidence + _RA.ESTABLISHED_CONFIDENCE_NUDGE
                )
                old.neuroticism = min(
                    _RA.ESTABLISHED_NEUROTICISM_CAP, old.neuroticism
                )  # stabilize
            elif tier == 2:
                # Middling: reset confidence, moderate everything else
                old.confidence = _RA.MIDDELING_CONFIDENCE_RESET
                old.openness = min(
                    1.0, old.openness + _RA.MIDDELING_OPENNESS_BOOST
                )  # encourage exploration
            elif tier == 3:
                # Buried: small lifeline, reduce neuroticism slightly
                old.confidence = max(
                    _RA.BURIED_CONFIDENCE_LIFELINE_LOW,
                    min(_RA.BURIED_CONFIDENCE_LIFELINE_HIGH,
                        old.confidence + 0.1)
                )
                old.neuroticism = max(
                    _RA.BURIED_NEUROTICISM_REDUCTION,
                    old.neuroticism - _RA.BURIED_NEUROTICISM_REDUCTION
                )
                old.openness = min(
                    1.0, old.openness + _RA.BURIED_OPENNESS_BOOST
                )  # explore or die
            else:
                # Shadow: faintest whisper. Must prove itself.
                old.confidence = _RA.SHADOW_CONFIDENCE_WHISPER
                old.neuroticism = min(
                    _PD.NEUROTICISM_MAX,
                    old.neuroticism + _RA.SHADOW_NEUROTICISM_GENTLE
                )

        total = sum(tiers.values())
        if total > 0:
            labels = {1: "established", 2: "middling", 3: "buried", 4: "shadow"}
            parts = [f"{labels[t]}={c}" for t, c in tiers.items() if c]
            print(f"    [REASSEMBLY] {error_type}: {total} patterns — {', '.join(parts)}")

    # ── Omega Revision (Extraversion-Aware) ─────────────────────────

    def _omega_revision(self, confirmed: PersonalityPatternNode):
        """
        Boost related patterns' confidence. Now tracks extraversion:
        patterns that get boosted via omega (not direct match) have
        their extraversion trait increased.
        """
        for etype, plist in self.by_type.items():
            for p in plist:
                if p is confirmed:
                    continue
                sig_sim = sig_similarity(
                    p.error_signature, confirmed.error_signature
                )
                loc_sim = 1.0 - abs(p.locality - confirmed.locality)
                type_bonus = 0.3 if p.error_type == confirmed.error_type else 0.0

                relatedness = sig_sim * 0.5 + loc_sim * 0.3 + type_bonus * 0.2
                if relatedness > 0.4:
                    boost = self.omega * relatedness * 0.15
                    p.personality.confidence = min(1.0, p.confidence + boost)
                    p.omega_selections += 1
                    # Update extraversion based on omega selections
                    total_sel = p.direct_selections + p.omega_selections
                    if total_sel > 0:
                        p.personality.extraversion = p.omega_selections / total_sel

    # ── Domain Personality Inheritance ──────────────────────────────

    def _inherit_domain_personality(self, error_type: str) -> PatternPersonality:
        """
        New patterns inherit an epigenetic personality from their error type.
        The error type IS the environment that shapes the pattern's starting character.
        """
        # Start from epigenetic default for this error type
        base = PatternPersonality.epigenetic_for(error_type)

        siblings = self.by_type.get(error_type, [])
        if len(siblings) < 2:
            # No established culture — use the epigenetic default directly
            # Newborn patterns are slightly more neurotic (unproven)
            base.neuroticism = min(
                _PD.NEUROTICISM_MAX, base.neuroticism + _PD.NEUROTICISM_STEP
            )
            base.confidence *= _PD.NEWBORN_CONFIDENCE_DECAY
            return base

        # Blend with siblings' average
        for p in siblings:
            pers = p.personality
            base.openness = (base.openness + pers.openness) / 2
            base.confidence = (base.confidence + pers.confidence) / 2
            base.extraversion = (base.extraversion + pers.extraversion) / 2
            base.agreeableness = (base.agreeableness + pers.agreeableness) / 2
            base.neuroticism = (base.neuroticism + pers.neuroticism) / 2

        # Newborn patterns are slightly more neurotic (unproven)
        base.neuroticism = min(1.0, base.neuroticism + 0.05)
        base.confidence *= _PD.NEWBORN_CONFIDENCE_DECAY

        return base

    # ── Stats / Persistence ─────────────────────────────────────────

    def stats(self) -> Dict:
        if not self.patterns:
            return {"n_patterns": 0, "total_seen": 0, "total_fixed": 0}

        by_type = defaultdict(int)
        by_tier = {1: 0, 2: 0, 3: 0, 4: 0}
        for p in self.patterns:
            by_type[p.error_type] += 1
            by_tier[p.personality.jungian_tier] += 1

        return {
            "n_patterns": len(self.patterns),
            "by_type": dict(by_type),
            "by_tier": by_tier,
            "personality": self.personality_summary,
            "omega": self.omega,
            "total_seen": sum(p.times_seen for p in self.patterns),
            "total_fixed": sum(p.times_fixed for p in self.patterns),
        }

    def print_summary(self):
        summary = self.stats()
        print(f"\nPersonality Knowledge Graph ({summary['n_patterns']} patterns):")
        if not self.patterns:
            print("  (empty)")
            return

        ps = summary["personality"]
        print(f"  Aggregate OCEAN-C: "
              f"O={ps.get('openness',0):.2f} "
              f"C={ps.get('confidence',0):.2f} "
              f"E={ps.get('extraversion',0):.2f} "
              f"A={ps.get('agreeableness',0):.2f} "
              f"N={ps.get('neuroticism',0):.2f} "
              f"| Omega={self.omega:.2f}")

        tier_labels = {1: "ESTABLISHED", 2: "MIDDELING", 3: "BURIED", 4: "SHADOW"}
        for p in sorted(self.patterns, key=lambda x: -x.personality.confidence):
            tier = p.personality.jungian_tier
            tier_label = tier_labels.get(tier, "UNKNOWN")
            pers = p.personality
            print(f"  [{p.error_type}] {tier_label} {p.error_signature[:50]}")
            print(f"    Fix: {p.fix_strategy[:60]}...")
            print(f"    O={pers.openness:.2f} C={pers.confidence:.2f} "
                  f"E={pers.extraversion:.2f} A={pers.agreeableness:.2f} "
                  f"N={pers.neuroticism:.2f} | fixed={p.times_fixed} "
                  f"shown={p.times_shown} followed={p.times_followed}")

    def _save(self):
        if not self._dirty:
            return
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"patterns": [p.to_dict() for p in self.patterns]}, f, indent=2
                )
            self._dirty = False
        except Exception:
            pass

    def flush(self):
        self._save()

    def _load(self):
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for pd in data.get("patterns", []):
                    # v3.5 migration: check if old format (no personality field)
                    if "personality" not in pd:
                        pd = self._migrate_v35_to_v40(pd)
                    node = PersonalityPatternNode.from_dict(pd)
                    self.patterns.append(node)
                    self.by_type[node.error_type].append(node)
        except Exception:
            pass

    def _migrate_v35_to_v40(self, old: dict) -> dict:
        """Convert v3.5 ErrorPatternNode to v4.0 PersonalityPatternNode."""
        personality = PatternPersonality()
        personality.confidence = old.get("confidence", 0.5)
        personality.neuroticism = 0.5  # default for legacy patterns

        # Estimate agreeableness from times_fixed / times_seen
        seen = old.get("times_seen", 1)
        fixed = old.get("times_fixed", 0)
        if seen > 0:
            personality.agreeableness = 0.3 + (fixed / seen) * 0.7

        # Estimate openness from fix complexity
        fix = old.get("fix_strategy", "")
        n_changes = fix.count("Changed:") + fix.count("Added:")
        personality.openness = min(1.0, 0.3 + n_changes * 0.1)

        return {
            **old,
            "personality": personality.to_dict(),
            "times_shown": 0,
            "times_followed": 0,
            "direct_selections": 0,
            "omega_selections": 0,
            "successful_contexts": [],
        }