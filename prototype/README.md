# Prototype: Puzzle Logic Coding Agent

This is a minimal but functional prototype demonstrating the Puzzle Logic architecture.

## Architecture in This Prototype

```
humaneval_runner.py -> lmstudio_client.py  (Synapse)
            |
            v
    constraint_engine.py  (OS - hard constraints)
```

## The Primary Benchmark: HumanEval

We use the **OpenAI HumanEval** benchmark — the industry standard for code generation evaluation. It contains **164 hand-written Python programming problems** with test cases. Published baselines exist for every major model (GPT-4, Claude, CodeLlama, DeepSeek, etc.).

### Why HumanEval?

- **Community standard** — every paper reports HumanEval scores
- **Functional correctness** — code must pass tests, not just look good
- **Exact fit for our architecture** — the test cases ARE the constraint engine
- **Clear metric** — `pass@k`: percentage of problems solved with k attempts

### The Comparison: Base Model vs Puzzle Logic OS

| | **Base Model** | **Puzzle Logic OS** |
|---|---|---|
| **Candidates per problem** | 1 (pass@1) | Up to 3 (adaptive) |
| **Selection** | Blind acceptance | Empirical: pick candidate that passes tests |
| **Error feedback** | **NONE** — model never sees failures | **ACTIVE** — failed attempts inform next candidate |
| **Adaptation** | **NONE** — static, same prompt every time | **IN-CONTEXT** — prompt changes based on errors |
| **Metric** | `pass@1` | Best-of-k with feedback loop |

### The Adaptation Mechanism (This Is The Key Difference)

**Base Model:**
```
Problem -> Generate 1 candidate -> Test -> Pass/Fail (end)
```
If the candidate fails, that's it. The model never learns why.

**Puzzle Logic OS:**
```
Problem -> Generate candidate 1 -> Test -> If FAIL:
              |
              v
         Error message captured
              |
              v
         Add error to prompt: "Your previous attempt failed because..."
              |
              v
         Generate candidate 2 (model sees the mistake)
              |
              v
         Test -> If FAIL, repeat up to k times
```

The **same model** with **same weights** generates the candidates. What changes is the **input prompt** — it now contains empirical feedback from previous attempts. This is **real in-context adaptation** without any fine-tuning.

### Baselines (published, for comparison)

| Model | HumanEval pass@1 |
|-------|-----------------|
| GPT-4 | ~67% |
| GPT-3.5 | ~48% |
| Claude 3.5 Sonnet | ~92% |
| CodeLlama-7B | ~28% |
| DeepSeek-Coder-6.7B | ~47% |
| Qwen2.5-Coder-7B | ~80% |

Your local 8B model will likely score somewhere in the 30-60% range. The question is: **does the OS improve that score by learning from errors?**

## Run the HumanEval Benchmark

### Prerequisites

1. **LM Studio** installed (https://lmstudio.ai)
2. A model loaded — we recommend **DeepSeek R1-0528-Qwen3-8B** or **Qwen2.5-Coder-7B**
3. The local server started (Developer tab -> Start Server)
4. Python 3.8+
5. `pip install requests`

### Quick Test (15 medium problems, ~5-8 minutes)

The default runs 15 **medium** problems where an 8B model should get ~40-70% in base mode, giving the OS room to recover from failures.

```bash
python humaneval_runner.py --mode both
```

### Options

```bash
# Medium subset (15 problems, default)
python humaneval_runner.py --mode both --subset medium

# Hard subset (20 problems)
python humaneval_runner.py --mode both --subset hard

# Full benchmark (164 problems)
python humaneval_runner.py --mode both --subset full

# Just 5 problems for a quick test
python humaneval_runner.py --mode both --limit 5

# Debug mode - see raw model output
python humaneval_runner.py --mode both --debug
```

## Expected Output

```
======================================================================
HUMANEVAL BENCHMARK RESULTS
======================================================================

Metric                         Base Model      Puzzle Logic OS
----------------------------------------------------------------------
Problems solved                  45/164          62/164
Pass rate                        27.4%           37.8%
Avg attempts per problem         1.0             2.1
Recoveries (OS saved base fail)  N/A             17

----------------------------------------------------------------------
IMPROVEMENT: +10.4 percentage points
RELATIVE GAIN: 38% more problems solved
```

## The Simple Demos

If you just want to see the agent in action without running the full benchmark:

```bash
python demo.py                # Success demonstration
python demo_rejection.py      # Rejection demonstration
```

## The Omega Parameter

In the OS mode, Omega starts at **0.5** (balanced). A candidate is accepted if its structural tension (test failures) is below `1 - Omega = 0.5`. The OS tries up to k candidates and picks the one with the lowest tension.

If no candidate passes, Omega is temporarily raised for the next problem (the agent becomes more open). This demonstrates metacognitive adaptation.

## Limitations of the Prototype

- Simple regex-based code extraction from LLM output
- No reassembly engine yet (Phase 2 in ROADMAP.md)
- No persistent Omega decay across sessions (Phase 4)
- Only Python syntax + pytest constraints
- Belief Graph is minimal (function names only)
- HumanEval is relatively small (164 problems); larger benchmarks (HumanEval+, MBPP) exist

## Files

| File | Purpose |
|------|---------|
| `humaneval_runner.py` | **THE BENCHMARK -- run this** |
| `HumanEval.jsonl` | The 164-problem dataset (downloaded automatically) |
| `demo.py` | Simple success demonstration |
| `demo_rejection.py` | Rejection demonstration |
| `puzzle_logic_agent.py` | Main agent with Omega-gated loop |
| `lmstudio_client.py` | LM Studio API client |
| `constraint_engine.py` | Syntax + test validation |
| `belief_graph.py` | Code knowledge tracking |
