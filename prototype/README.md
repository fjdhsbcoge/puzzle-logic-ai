# Prototype: Puzzle Logic Coding Agent

This is a minimal but functional prototype demonstrating the Puzzle Logic architecture.

## What It Does

The agent takes a coding task, asks a local LLM (via LM Studio) to generate solutions, and **rejects candidates that fail empirical constraints**. Only code that compiles and passes tests is accepted.

## Architecture in This Prototype

```
benchmark_runner.py → puzzle_logic_agent.py → lmstudio_client.py  (Synapse)
                                ↓
                       constraint_engine.py  (OS — hard constraints)
                                ↓
                       belief_graph.py       (OS — knowledge tracking)
```

## Prerequisites

1. **LM Studio** installed (https://lmstudio.ai)
2. A model loaded — we recommend **DeepSeek R1-0528-Qwen3-8B**
3. The local server started (Developer tab → Start Server)
4. Python 3.8+
5. `pip install requests pytest`

## Run the Benchmark

The benchmark is the most important demo. It compares the **base model** (1-shot generation, no validation) against the **Puzzle Logic OS** (3-candidate generation + empirical selection).

```bash
python benchmark_runner.py
```

### What the Benchmark Measures

| Metric | Base Model | Puzzle Logic OS |
|--------|-----------|-----------------|
| **Candidates per task** | 1 | Up to 3 |
| **Validation** | None | Syntax + pytest |
| **Selection strategy** | Accept whatever the model outputs | Pick the candidate with the LOWEST structural tension |
| **Retry on failure?** | No — task is failed | Yes — tries next candidate |

### The Hypothesis

On tasks with **hidden edge cases** (zero division, empty lists, case-insensitive palindromes, cache eviction order), models often produce wrong code. The base model accepts this wrong code blindly. The Puzzle Logic OS detects the failure through constraint validation and selects a better candidate.

**Expected result:** Puzzle Logic OS should show a higher success rate, especially on medium/hard tasks.

### Benchmark Tasks (6 total)

| # | Task | Difficulty | Hidden Trap |
|---|------|-----------|-------------|
| 1 | `multiply(a, b)` | Easy | None — sanity check |
| 2 | `safe_divide(a, b)` | Medium | Must return `None` on zero, not crash |
| 3 | `is_palindrome(s)` | Medium | Must ignore case, spaces, punctuation |
| 4 | `list_average(nums)` | Medium | Must return `0.0` for empty list |
| 5 | `LRUCache` class | Hard | Must evict least-recently-used correctly |
| 6 | `fibonacci(n)` | Hard | Must use memoization/iteration for large n |

## Run the Simple Demos

If you just want to see the agent in action without the benchmark overhead:

```bash
python demo.py                # Success demonstration
python demo_rejection.py      # Rejection demonstration
```

## The Ω Parameter

In the benchmark, Ω starts at **0.5** (balanced). The OS accepts a candidate if its structural tension is below `1 - Ω = 0.5`.

If no candidate passes, Ω is temporarily raised (the agent becomes more open for the next task). This demonstrates **metacognitive adaptation**.

## Limitations of the Prototype

- Simple regex-based code extraction from LLM output
- No reassembly engine yet (Phase 2)
- No persistent Ω decay across sessions (Phase 4)
- Only Python syntax + pytest constraints
- Belief Graph is minimal (function names only)
- The base model may be "too good" and pass everything — try a weaker model to see the OS advantage

These are documented in the main project's `ROADMAP.md`.

## Files

| File | Purpose |
|------|---------|
| `benchmark_runner.py` | **The benchmark — run this first** |
| `benchmark_suite.py` | 6 benchmark tasks with hidden traps |
| `demo.py` | Simple success demonstration |
| `demo_rejection.py` | Rejection demonstration |
| `puzzle_logic_agent.py` | Main agent with Ω-gated loop |
| `lmstudio_client.py` | LM Studio API client |
| `constraint_engine.py` | Syntax + test validation |
| `belief_graph.py` | Code knowledge tracking |
| `sample_project/calculator.py` | Target module for demos |
| `sample_project/test_calculator.py` | pytest test suite for demos |
