# Puzzle Logic Agent

An empirical, psychology-inspired constraint satisfaction system for code generation. The agent learns from compiler errors and builds a knowledge graph of verified fix patterns.

## Philosophy

> **"Creativity: Create something, from the sum of your Memory, that has not been in the memory before."**

Puzzle Logic treats code generation as a **creative synthesis** problem. When the LLM fails, the system doesn't just copy old fixes — it combines insights from multiple proven patterns into novel solutions.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   You       │────▶│   Aider      │────▶│  LLM (local)│
│ (task desc) │     │  (orchestrate)│     │  7B/14B     │
└─────────────┘     └──────┬───────┘     └─────────────┘
                           │
                    ┌──────▼──────┐
                    │   Tests     │◀── pytest
                    │ (pass/fail) │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ Puzzle Logic│───▶ Knowledge Graph
                    │  (on fail)  │◀───── Creative Toolbox
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   LLM       │───▶ Retry with enriched prompt
                    │  (retry)    │     + toolbox + orientation
                    └─────────────┘
```

## Key Concepts

### OCEAN-C Personality Model

Each error pattern has a 5-dimensional personality profile:

| Trait | Meaning | How It Changes |
|---|---|---|
| **O** — Openness | Cross-context applicability | +0.14 on new context success |
| **C** — Confidence | Verified reliability (earned trust) | +0.10 on success, ×decay on failure |
| **E** — Extraversion | Omega (relational) vs direct orientation | Emergent: omega_selections / total |
| **A** — Agreeableness | LLM compliance rate | times_followed / times_shown |
| **N** — Neuroticism | Emotional stability (controls decay) | ±0.01 per outcome, bounded ±50% of birth |

### Creative Mode (v4.5)

Instead of showing one pattern from the same error type, the toolbox presents **3 ingredients from different error types**. The LLM synthesizes a novel solution by combining cross-domain insights.

### Inward/Outward Orientation

The model's attention direction shifts based on aggregate confidence:

| Confidence | Orientation | Behavior |
|---|---|---|
| C < 0.4 | **Outward** | Observe environment, build understanding from outside in |
| 0.4 ≤ C < 0.7 | **Balanced** | Cross-reference toolbox with actual error |
| C ≥ 0.7 | **Inward** | Trust proven patterns decisively |

### N Envelope (v4.4)

Neuroticism stays within **±50% of its birth value**. No more death spirals:
- Default birth N = 0.20 → envelope [0.10, 0.30]
- Decay stays between 0.70–0.90 (predictable, bounded)

## Requirements

- Python 3.9+
- [Aider](https://aider.chat/) (AI pair programming)
- [LM Studio](https://lmstudio.ai/) or similar (local LLM server)
- Compatible LLM (7B minimum for Aider, 14B recommended)

## Hardware Recommendations

| GPU VRAM | Model | Workers | Notes |
|---|---|---|---|
| 12GB | Qwen 2.5 Coder 14B | 1-2 | Best quality, fits comfortably |
| 12GB | Qwen 2.5 Coder 7B | 3-4 | Fast iteration, good quality |
| 16GB+ | Qwen 2.5 Coder 14B | 2-3 | Headroom for larger projects |

**Avoid:** <7B models (cannot handle Aider's diff format), MoE models (uneven quality).

## Quick Start

### Step 1: Install Dependencies

```bash
pip install aider-chat pytest
```

### Step 2: Set Up Your Project

Create a project folder and copy the bridge:

```bash
mkdir my_app
cd my_app
cp /path/to/puzzle-logic/aider_bridge.py ./
mkdir tests
touch tests/__init__.py
```

Create `.gitignore`:
```
# Puzzle Logic auto-generated files
.puzzle_logic_knowledge.json
.puzzle_logic_failure_log.json
.puzzle_logic_toolbox.md
```

### Step 3: Launch LM Studio

1. Open LM Studio
2. Load your model (e.g., Qwen 2.5 Coder 14B)
3. Start the server on port 1234

### Step 4: Launch Aider with Puzzle Logic

```bash
aider \
  --model openai/qwen2.5-coder-14b-instruct \
  --api-key openai=not-needed \
  --openai-api-base http://localhost:1234/v1 \
  --test-cmd "python aider_bridge.py --test" \
  --dark-mode
```

**Windows PowerShell:**
```powershell
$env:OPENAI_API_BASE = "http://localhost:1234/v1"
aider `
  --model openai/qwen2.5-coder-14b-instruct `
  --api-key openai=not-needed `
  --openai-api-base http://localhost:1234/v1 `
  --test-cmd "python aider_bridge.py --test" `
  --dark-mode
```

### Step 5: Start Building

Give Aider a task that includes a test:

```
Create tests/test_math.py:

def test_circle_area():
    from app import circle_area
    assert circle_area(10) == 314.16

Now implement circle_area(radius) in app.py.
```

After Aider generates code, trigger your bridge manually:
```
/run python aider_bridge.py --test
```

**If the test fails**, you'll see:
```
[Creative Toolbox — Synthesis Ingredients]
ORIENTATION: You are in OBSERVE mode...
Ingredient 1 [TypeError]: ...
CREATE: Combine ingredients into a solution for YOUR code.
```

**If the test passes** after a failure:
```
[Puzzle Logic] Fix recorded to knowledge graph: TypeError
```

## How It Works

### The Learning Loop

1. **Aider generates code** → runs via bridge
2. **pytest fails** → bridge extracts error signature
3. **Knowledge graph queried** → returns Creative Toolbox
4. **Toolbox injected into retry prompt** → LLM synthesizes fix
5. **pytest passes** → bridge records successful fix to graph
6. **Pattern confidence grows** → available for future errors

### Curriculum Learning

For best results, follow this progression:

| Phase | Task Type | Goal |
|---|---|---|
| **1** | Structural fixes (TypeError, NameError) | Master mechanical corrections |
| **2** | Logic fixes (AssertionError, ValueError) | Learn algorithmic patterns |
| **3** | Creative synthesis (multi-domain) | Combine ingredients from different errors |

## Files

| File | Purpose |
|---|---|
| `personality_engine.py` | OCEAN-C knowledge graph, creative toolbox |
| `model_personality.py` | Aggregate agent personality, orientation system |
| `utils.py` | Error fingerprinting, principle generation, code delta |
| `ocean_config.py` | Tunable parameters (all knobs in one file) |
| `constraint_engine.py` | Structural auto-fixer for local errors |
| `puzzle_logic_agent.py` | Main agent with baseline/basic/advanced modes |
| `aider_bridge.py` | Aider integration (place in your project) |
| `test_puzzle_logic.py` | 46 integration tests |

## Configuration

Edit `ocean_config.py` to tune behavior:

```python
class PatternDynamics:
    SUCCESS_CONFIDENCE_BOOST: float = 0.10   # How much C grows per fix
    NEUROTICISM_STEP: float = 0.01             # How fast N shifts
    NEUROTICISM_MIN: float = 0.20             # Floor for N
    NEUROTICISM_MAX: float = 0.80             # Ceiling for N

class CompositeWeights:
    OPENNESS: float = 0.15       # Reward generalists
    CONFIDENCE: float = 0.35     # Reward proven patterns (highest weight)
    EXTRAVERSION: float = 0.15   # Reward novel associations (creative mode)
    AGREEABLENESS: float = 0.25  # Reward LLM compliance
    NEUROTICISM: float = -0.15  # Penalize unstable patterns
    FLOOR: float = 0.08          # Minimum score to enter toolbox
```

## Troubleshooting

### "No verified patterns for X yet"
This is normal on first encounters. The graph builds knowledge over time. After 20-30 problems in a domain, you'll have solid patterns.

### Model hangs on commit messages
Use `--no-auto-commit` flag, or switch to a larger model (7B minimum, 14B recommended).

### "The LLM did not conform to the edit format"
Context too long for the model. Use `/clear` in Aider, or switch to a model with larger context window.

### Puzzle Logic never activates
Ensure:
1. `aider_bridge.py` is in your project directory
2. You're using `/run python aider_bridge.py --test` (not letting Aider auto-run flake8)
3. Your tests check **logic**, not just imports (flake8 catches import errors first)

## License

MIT License

## Acknowledgments

Inspired by:
- Carl Jung's psychological types (consciousness tiers)
- OCEAN personality model (adapted for error patterns)
- John Ousterhout's deep modules philosophy
- Aider's agentic coding paradigm

Collaboration between:
SenatorThunfisch & KIMI K2.6 Agent