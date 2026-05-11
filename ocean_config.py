"""
OCEAN-C Personality Configuration v4.2 — "Troy" Edition
========================================================

Single source of truth for ALL personality parameters.
Edit values here, save, and restart the agent to apply changes.

Sections:
  1. Pattern-Level Update Mechanics (how individual traits move)
  2. Composite Score Weights (toolbox ranking formula)
  3. Jungian Tier Thresholds (consciousness layers)
  4. Reassembly Recalibration (crisis reset values)
  5. Epigenetic Defaults (starting personalities per error type)
  6. Model-Level Personality (aggregate agent character)
  7. Model-Level Behavior Thresholds (tone, toolbox size, etc.)

Valid trait range for all OCEAN-C values: [0.0, 1.0]
"""

# ═══════════════════════════════════════════════════════════════════════
#  1. PATTERN-LEVEL UPDATE MECHANICS
#     How an individual pattern's traits change on success/failure.
# ═══════════════════════════════════════════════════════════════════════

class PatternDynamics:
    """Knobs that control how fast a pattern's personality evolves."""

    # ── Confidence (C) ────────────────────────────────────────────────
    SUCCESS_CONFIDENCE_BOOST: float = 0.10
    """Absolute C added on every successful fix. Range: 0.05 to 0.30
    
    HIGHER → Patterns earn trust faster. Rocket to reliable status.
    LOWER  → Slow, conservative learning. Patterns stay timid longer.
    """

    NEWBORN_CONFIDENCE_DECAY: float = 0.81
    """Multiplier applied to C when a new pattern is born. Range: 0.80 to 1.00
    
    HIGHER → New patterns enter bolder, more confident.
    LOWER  → New patterns enter humble, must prove themselves.
    Applied TWICE: once for no-siblings path, once after sibling blending.
    """

    # ── Neuroticism (N) ──────────────────────────────────────────────
    NEUROTICISM_STEP: float = 0.01
    """How much N shifts per outcome. Range: 0.005 to 0.05
    
    HIGHER → Emotional rollercoaster. Patterns swing between calm and anxious.
    LOWER  → Glacial emotional shifts. Very stable, predictable graph.
    Applied: +step on failure, -step on success.
    """

    NEUROTICISM_MIN: float = 0.20
    """Floor for N. A pattern can never be calmer than this. Range: 0.0 to 1.0
    
    HIGHER → The entire graph has a baseline anxiety. No pattern is ever fully calm.
    LOWER  → Patterns can recover to zen-like stability after enough successes.
    """

    NEUROTICISM_MAX: float = 0.80
    """Ceiling for N. A pattern can never be more anxious than this. Range: 0.0 to 1.0
    
    HIGHER → Patterns can become nearly destroyed by repeated failures.
    LOWER  → Emotional damage is capped. The graph never spirals into chaos.
    """

    # ── Openness (O) ──────────────────────────────────────────────────
    OPENNESS_SUCCESS_DELTA: float = 0.14
    """O gained when pattern succeeds in a NEW context. Range: 0.0 to 0.20
    
    HIGHER → Rapid cross-domain generalization. Patterns become versatile quickly.
    LOWER  → Patterns stay specialized, narrow in applicability.
    Only fires when the success context has never been seen before.
    """

    # ── Extraversion (E) ─────────────────────────────────────────────
    # E is computed dynamically: omega_selections / total_selections
    # No tunable parameter — purely emergent from usage history.

    # ── Agreeableness (A) ────────────────────────────────────────────
    # A is computed dynamically: times_followed / times_shown
    # No tunable parameter — purely emergent from LLM compliance.


# ═══════════════════════════════════════════════════════════════════════
#  2. COMPOSITE SCORE WEIGHTS
#     How the five traits combine into a single toolbox selection score.
# ═══════════════════════════════════════════════════════════════════════

class CompositeWeights:
    """Weights for the toolbox ranking formula.
    
    score = wO*O + wC*C + wE*E + wA*A + wN*N
    
    Positive = higher trait increases score.
    Negative = higher trait DECREASES score (inverted preference).
    """

    OPENNESS:      float =  0.15   # Range: -0.3 to +0.3
    CONFIDENCE:    float =  0.35   # Range:  0.0 to +0.6  (strongest signal)
    EXTRAVERSION:  float =  0.15   # Range: -0.3 to +0.3  (positive = reward omega/relational novel associations)
    """Weight for Extraversion in composite score. Range: -0.3 to +0.3
    
    POSITIVE → Omega/relational patterns (cross-domain, novel associations) score higher.
             The system rewards creative recombination over direct copying.
    NEGATIVE → Direct-match patterns (literal, identical error) score higher.
             The system prefers proven copy-paste fixes.
    ZERO   → Extraversion has no effect on toolbox selection.
    """

    AGREEABLENESS: float =  0.25   # Range:  0.0 to +0.5
    NEUROTICISM:   float = -0.15   # Range: -0.4 to  0.0  (negative = prefer stable)

    FLOOR: float = 0.08
    """Minimum composite score to enter toolbox. Range: 0.0 to 0.30
    
    HIGHER → Ruthless culling. Only elite, proven patterns are shown.
    LOWER  → More inclusive. Borderline patterns get a chance to prove themselves.
    """


# ═══════════════════════════════════════════════════════════════════════
#  3. JUNGIAN TIER THRESHOLDS
#     Four consciousness layers based on confidence and agreeableness.
# ═══════════════════════════════════════════════════════════════════════

class JungianTiers:
    """Tier boundaries for the consciousness model.
    
    Tier 1 (Established)   → High confidence, compliant — the trusted elite
    Tier 2 (Middling)      → Moderate confidence — reliable but not proven
    Tier 3 (Buried)        → Low confidence but some hope — on life support
    Tier 4 (Shadow)        → Forgotten — must prove itself from scratch
    """

    ESTABLISHED_MIN_CONFIDENCE: float = 0.70
    ESTABLISHED_MIN_AGREEABLENESS: float = 0.50
    # Must satisfy BOTH to be Tier 1.

    MIDDELING_MIN_CONFIDENCE: float = 0.50
    # C >= this value (but below Established thresholds) → Tier 2.

    BURIED_MAX_CONFIDENCE: float = 0.50
    BURIED_MIN_CONFIDENCE: float = 0.20
    BURIED_MIN_OPENNESS: float = 0.30
    # C < MIDDELING_MIN AND (C > BURIED_MIN_CONFIDENCE OR O > BURIED_MIN_OPENNESS)

    # Everything else falls to Tier 4 (Shadow).


# ═══════════════════════════════════════════════════════════════════════
#  4. REASSEMBLY RECALIBRATION
#     After 3 consecutive toolbox failures for an error type,
#     all patterns get reset to tier-appropriate values.
# ═══════════════════════════════════════════════════════════════════════

class Reassembly:
    """Values applied during unconscious surfacing (reassembly).
    
    Trigger: 3 consecutive toolbox failures for a single error type.
    Effect: Every pattern of that error type gets its personality reset
            based on which Jungian tier it currently occupies.
    """

    ESTABLISHED_CONFIDENCE_NUDGE: float = -0.15   # Applied to existing C
    ESTABLISHED_CONFIDENCE_FLOOR: float = 0.55     # C won't drop below this
    ESTABLISHED_NEUROTICISM_CAP: float = 0.40      # N hard-capped here

    MIDDELING_CONFIDENCE_RESET: float = 0.50       # C set to exactly this
    MIDDELING_OPENNESS_BOOST: float = 0.05         # O += this (encourage exploration)

    BURIED_CONFIDENCE_LIFELINE_LOW: float = 0.30   # C won't drop below this
    BURIED_CONFIDENCE_LIFELINE_HIGH: float = 0.40  # C won't exceed this
    BURIED_NEUROTICISM_REDUCTION: float = 0.05     # N -= this (calm down)
    BURIED_OPENNESS_BOOST: float = 0.10            # O += this (explore or die)

    SHADOW_CONFIDENCE_WHISPER: float = 0.20        # C set to exactly this
    SHADOW_NEUROTICISM_GENTLE: float = 0.02        # N += this (slight anxiety)


# ═══════════════════════════════════════════════════════════════════════
#  5. EPIGENETIC DEFAULTS
#     Starting OCEAN-C personality for each error type.
#     Format: (Openness, Confidence, Extraversion, Agreeableness, Neuroticism)
#     All values in range [0.0, 1.0].
# ═══════════════════════════════════════════════════════════════════════

EPIGENETIC_PROFILES: dict[str, tuple[float, float, float, float, float]] = {
    # ── Syntax / Structural (high C, low E — mechanical fixes) ──────
    "SyntaxError":         (0.35, 0.70, 0.20, 0.50, 0.20),
    "IndentationError":    (0.30, 0.75, 0.15, 0.50, 0.20),
    "NameError":           (0.40, 0.60, 0.20, 0.50, 0.20),

    # ── Import (high C, low E — local, confident) ───────────────────
    "ImportError":         (0.40, 0.60, 0.20, 0.50, 0.20),
    "ModuleNotFoundError": (0.40, 0.60, 0.20, 0.50, 0.20),

    # ── Type / Value (moderate O and C — common, varied fixes) ──────
    "TypeError":           (0.50, 0.55, 0.30, 0.50, 0.20),
    "ValueError":          (0.50, 0.45, 0.30, 0.50, 0.20),
    "AttributeError":      (0.50, 0.45, 0.30, 0.50, 0.20),

    # ── Index / Key (moderate O and C — structural access errors) ───
    "IndexError":          (0.45, 0.50, 0.25, 0.50, 0.20),
    "KeyError":            (0.45, 0.50, 0.25, 0.50, 0.20),

    # ── Runtime (low C, high O and E — complex, creative fixes) ─────
    "RecursionError":      (0.60, 0.30, 0.40, 0.50, 0.20),
    "TimeoutError":        (0.60, 0.30, 0.40, 0.50, 0.20),
    "AssertionError":      (0.60, 0.50, 0.40, 0.50, 0.20),

    # ── Arithmetic (moderate C, low E — local guard conditions) ─────
    "ZeroDivisionError":   (0.40, 0.55, 0.25, 0.50, 0.20),
}

# Fallback personality when error type is not in the table above.
EPIGENETIC_FALLBACK: tuple[float, float, float, float, float] = (
    0.35, 0.50, 0.50, 0.50, 0.20
)


# ═══════════════════════════════════════════════════════════════════════
#  6. MODEL-LEVEL PERSONALITY
#     The aggregate character of the agent itself (computed from all
#     pattern personalities, not set directly).
#     These are the DEFAULT values used when the graph is empty.
# ═══════════════════════════════════════════════════════════════════════

class ModelDefaults:
    """Starting model personality when no patterns exist yet.
    
    These values are overridden as soon as the first pattern is recorded.
    The actual model personality is computed dynamically by
    PersonalityAggregator in model_personality.py.
    """

    OPENNESS: float = 0.35
    CONFIDENCE: float = 0.50
    EXTRAVERSION: float = 0.50
    AGREEABLENESS: float = 0.50
    NEUROTICISM: float = 0.50


# ═══════════════════════════════════════════════════════════════════════
#  7. MODEL-LEVEL BEHAVIOR THRESHOLDS
#     How the aggregate personality affects agent behavior.
# ═══════════════════════════════════════════════════════════════════════

class ModelBehavior:
    """Thresholds that map model personality to concrete actions.
    
    These control: tone of voice, toolbox size, temperature,
    whether unverified patterns are shown, and more.
    """

    # ── Tone Thresholds ──────────────────────────────────────────────
    TONE_AUTHORITATIVE_CONFIDENCE: float = 0.70
    TONE_AUTHORITATIVE_NEUROTICISM_MAX: float = 0.40
    # Both must be satisfied for "authoritative" tone.

    TONE_CONFIDENT_CONFIDENCE: float = 0.55
    TONE_CONFIDENT_NEUROTICISM_MAX: float = 0.60

    TONE_CAUTIOUS_CONFIDENCE: float = 0.30
    # Below this → "tentative" tone.

    # ── Exploration Thresholds ───────────────────────────────────────
    SHOW_UNVERIFIED_CONFIDENCE: float = 0.50
    SHOW_UNVERIFIED_NEUROTICISM_MAX: float = 0.50
    SHOW_UNVERIFIED_OPENNESS_MIN: float = 0.40
    # All three must be satisfied to include unverified (times_fixed=0)
    # patterns in the toolbox.

    # ── Toolbox Size ─────────────────────────────────────────────────
    TOOLBOX_SIZE_HIGH: int = 5     # C >= 0.70
    TOOLBOX_SIZE_MEDIUM: int = 3   # C >= 0.50
    TOOLBOX_SIZE_LOW: int = 2      # C <  0.50

    # ── Retry Temperature ────────────────────────────────────────────
    TEMP_CONSERVATIVE: float = 0.0   # N > 0.60 (play it safe)
    TEMP_EXPLORATORY: float = 0.2    # O > 0.60 (try alternatives)

    # ── Neuroticism Impact on Aggregate ──────────────────────────────
    NEUROTICISM_MAX_BLEND: float = 0.40
    """How much the most anxious single pattern influences the whole model.
    
    Formula: model_N = (1 - blend) * avg_N + blend * max_N
    HIGHER → One traumatized pattern makes the whole agent anxious.
    LOWER  → Model neuroticism is purely democratic (average of all).
    """

    # ── Confidence Weighting ─────────────────────────────────────────
    CONFIDENCE_WEIGHTED_BLEND: float = 0.70
    """Blend between weighted-by-fixes and simple-average confidence.
    
    Formula: C = blend * weighted_C + (1 - blend) * avg_C
    HIGHER → Patterns with more successful fixes dominate the model character.
    LOWER  → All patterns contribute equally, regardless of success.
    """

    # ── Agreeableness Weighting ──────────────────────────────────────
    AGREEABLENESS_WEIGHTED_BLEND: float = 0.70
    """Same blend logic for agreeableness, but weighted by times_shown.
    
    HIGHER → Patterns shown more often (and presumably followed) dominate.
    LOWER  → Democratic average of all pattern agreeableness values.
    """

    # ── Extraversion Introvert Damping ───────────────────────────────
    INTROVERT_DAMPING_RATIO: float = 0.70
    INTROVERT_DAMPING_FACTOR: float = 0.80
    """If >70% of patterns are introverted (E < 0.5), dampen aggregate E by 20%.
    
    Prevents a few extraverted outliers from overstating the model's relational style
    when the vast majority of patterns are direct-match specialists.
    """


# ═══════════════════════════════════════════════════════════════════════
#  8. QUICK REFERENCE: VALID RANGES FOR EVERY PARAMETER
# ═══════════════════════════════════════════════════════════════════════

VALID_RANGES = {
    # Pattern dynamics
    "PatternDynamics.SUCCESS_CONFIDENCE_BOOST": (0.05, 0.30),
    "PatternDynamics.NEWBORN_CONFIDENCE_DECAY": (0.80, 1.00),
    "PatternDynamics.NEUROTICISM_STEP": (0.005, 0.05),
    "PatternDynamics.NEUROTICISM_MIN": (0.0, 1.0),
    "PatternDynamics.NEUROTICISM_MAX": (0.0, 1.0),
    "PatternDynamics.OPENNESS_SUCCESS_DELTA": (0.0, 0.20),

    # Composite weights
    "CompositeWeights.OPENNESS": (-0.3, 0.3),
    "CompositeWeights.CONFIDENCE": (0.0, 0.6),
    "CompositeWeights.EXTRAVERSION": (-0.3, 0.3),
    "CompositeWeights.AGREEABLENESS": (0.0, 0.5),
    "CompositeWeights.NEUROTICISM": (-0.4, 0.0),
    "CompositeWeights.FLOOR": (0.0, 0.30),

    # Tier thresholds
    "JungianTiers.ESTABLISHED_MIN_CONFIDENCE": (0.5, 1.0),
    "JungianTiers.ESTABLISHED_MIN_AGREEABLENESS": (0.0, 1.0),
    "JungianTiers.MIDDELING_MIN_CONFIDENCE": (0.3, 0.7),
    "JungianTiers.BURIED_MAX_CONFIDENCE": (0.3, 0.6),
    "JungianTiers.BURIED_MIN_CONFIDENCE": (0.0, 0.3),
    "JungianTiers.BURIED_MIN_OPENNESS": (0.0, 0.5),

    # Reassembly
    "Reassembly.ESTABLISHED_CONFIDENCE_NUDGE": (-0.3, 0.0),
    "Reassembly.ESTABLISHED_CONFIDENCE_FLOOR": (0.4, 0.7),
    "Reassembly.ESTABLISHED_NEUROTICISM_CAP": (0.2, 0.6),
    "Reassembly.MIDDELING_CONFIDENCE_RESET": (0.4, 0.6),
    "Reassembly.MIDDELING_OPENNESS_BOOST": (0.0, 0.15),
    "Reassembly.BURIED_CONFIDENCE_LIFELINE_LOW": (0.1, 0.4),
    "Reassembly.BURIED_CONFIDENCE_LIFELINE_HIGH": (0.3, 0.5),
    "Reassembly.BURIED_NEUROTICISM_REDUCTION": (0.0, 0.15),
    "Reassembly.BURIED_OPENNESS_BOOST": (0.0, 0.2),
    "Reassembly.SHADOW_CONFIDENCE_WHISPER": (0.1, 0.3),
    "Reassembly.SHADOW_NEUROTICISM_GENTLE": (0.0, 0.1),

    # Model behavior
    "ModelBehavior.NEUROTICISM_MAX_BLEND": (0.0, 1.0),
    "ModelBehavior.CONFIDENCE_WEIGHTED_BLEND": (0.0, 1.0),
    "ModelBehavior.AGREEABLENESS_WEIGHTED_BLEND": (0.0, 1.0),
    "ModelBehavior.INTROVERT_DAMPING_RATIO": (0.5, 1.0),
    "ModelBehavior.INTROVERT_DAMPING_FACTOR": (0.5, 1.0),
}


# ═══════════════════════════════════════════════════════════════════════
#  HOW TO USE THIS FILE
# ═══════════════════════════════════════════════════════════════════════
#
#  1. Edit any value above.
#  2. Save the file.
#  3. Restart the agent / runner.
#
#  The code imports from this file at runtime. No recompilation needed.
#
#  Safety: Values outside VALID_RANGES are technically allowed but
#  may produce unstable behavior. Stay within the ranges for predictable
#  personality dynamics.
#
#  To reset to factory defaults: copy the fallback block below over
#  the current values, or delete this file (code uses built-in defaults).
# ═══════════════════════════════════════════════════════════════════════
