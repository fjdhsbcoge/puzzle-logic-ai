# Prototype: Puzzle Logic Coding Agent

This is a minimal but functional prototype demonstrating the Puzzle Logic architecture.

## What It Does

The agent takes a coding task, asks a local LLM (via LM Studio) to generate solutions, and **rejects candidates that fail empirical constraints**. Only code that compiles and passes tests is accepted.

## Architecture in This Prototype

```
demo.py → puzzle_logic_agent.py → lmstudio_client.py  (Synapse)
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

## Run

```bash
python demo.py
```

## Expected Output

The demo runs two tasks:
1. Add a `multiply(a, b)` function
2. Add a `divide(a, b)` function with zero-division handling

For each task, the agent:
- Generates 3 candidates from the Synapse
- Checks syntax (`python -m py_compile`)
- Runs existing tests (`pytest`)
- Computes structural tension
- Accepts or rejects based on Ω-gated threshold

## The Ω Parameter

In the demo, Ω starts at **0.5** (balanced). If no candidate passes, Ω is temporarily raised (the agent becomes more open).

Adjust it in `demo.py`:
```python
agent = PuzzleLogicAgent(omega=0.5)  # Try 0.2 (conservative) or 0.8 (receptive)
```

## Limitations of the Prototype

- Simple regex-based code extraction from LLM output
- No reassembly engine yet (Phase 2)
- No Ω decay over sessions (Phase 4)
- Only Python syntax + pytest constraints
- Belief Graph is minimal (function names only)

These are documented in the main project's `ROADMAP.md`.

## Files

| File | Purpose |
|------|---------|
| `demo.py` | Runnable demonstration |
| `puzzle_logic_agent.py` | Main agent with Ω-gated loop |
| `lmstudio_client.py` | LM Studio API client |
| `constraint_engine.py` | Syntax + test validation |
| `belief_graph.py` | Code knowledge tracking |
| `sample_project/calculator.py` | Target module to modify |
| `sample_project/test_calculator.py` | pytest test suite |
