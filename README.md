# Puzzle Logic AI

**A fundamentally different approach to AI reasoning.**

Traditional AI agents are statistical pattern matchers with no structural understanding of correctness. Puzzle Logic AI treats knowledge as a jigsaw puzzle: empirical observations are pieces, and hard constraints are the assembly rules. A claim is accepted only if it fits structurally — never because it "sounds plausible."

This repository contains both the **conceptual framework** and a **working prototype** demonstrating the approach on coding tasks.

---

## Core Idea

| Traditional AI | Puzzle Logic AI |
|---------------|-----------------|
| Pattern matching | Constraint satisfaction |
| "Probable" = true | "Fits" = true |
| Confidence scores | Structural tension |
| Monolithic model | Synapse (LLM) + OS (constraints) |

The entire epistemic stance is controlled by one parameter: **Omega** — openness to being proved wrong. High Omega (novice) explores wildly. Low Omega (expert) only accepts what structurally fits.

---

## What This Repo Contains

| Directory | Purpose |
|-----------|---------|
| `docs/` | Concept papers, architecture, references |
| `prototype/` | Research code — experiments, benchmarks, diagnostics |
| `product/` | **v1.0 CLI tool** — download and use immediately |

---

## Benchmark Results

### HumanEval (164 coding problems)

| Model | Baseline (pass@3) | + Puzzle Logic OS | Delta |
|-------|------------------|-------------------|-------|
| Qwen2.5-Coder-3B | 91.5% (150/164) | **98.2% (161/164)** | **+6.7 pp** |

- **11 problems** fixed by the Error-Pattern Graph
- **0 regressions** — never hurt a problem that already passed
- **Toolbox success rate**: 82% (14/17 times it helped)

### HumanEval+ (harder — 80× more tests per problem)

Run in progress. Expected baseline: ~55%, target with OS: ~65%.

See [RESULTS.md](RESULTS.md) for full methodology and analysis.

---

## Quick Start (5 Minutes)

### Prerequisites
- Python 3.10+
- [LM Studio](https://lmstudio.ai) with a model loaded (e.g., Qwen2.5-Coder-3B-Instruct)

### Install
```bash
git clone https://github.com/fjdhsbcoge/puzzle-logic-ai.git
cd puzzle-logic-ai/product
pip install requests
```

### Use It
```bash
python puzzle_logic_agent.py my_script.py --model qwen2.5-coder-3b-instruct
```

What happens:
1. Sends your script to the local LLM
2. Runs it
3. If it fails → searches error history → suggests fixes
4. If it passes → remembers the solution pattern for next time

---

## Architecture

```
┌──────────────┐     ┌─────────────────────┐     ┌──────────────┐
│   Synapse    │────▶│   Puzzle Logic OS   │────▶│   Output     │
│   (LLM)      │     │                     │     │              │
│  Generates   │     │  1. Empirical test  │     │  Pass/fail   │
│  candidates  │     │  2. Error extraction │     │  + learned   │
│              │     │  3. Pattern match   │     │  patterns    │
└──────────────┘     │  4. Structural fit  │     └──────────────┘
                     │  5. Accept/reject   │
                     └─────────────────────┘
                              │
                              ▼
                     ┌─────────────────────┐
                     │   Error-Pattern     │
                     │   Knowledge Graph     │
                     │  (persists across     │
                     │   sessions)           │
                     └─────────────────────┘
```

The OS layer is model-agnostic. It works with any local LLM: Qwen, DeepSeek, Llama, Mistral.

---

## Key Concepts

- **[CONCEPT.md](docs/CONCEPT.md)** — The epistemology: knowledge as structural assembly
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** — Synapse × OS × Omega design
- **[OMEGA_PARAMETER.md](docs/OMEGA_PARAMETER.md)** — The single parameter controlling belief
- **[REFERENCES.md](docs/REFERENCES.md)** — Free Energy Principle, precision weighting, constraint programming

---

## Contributing

This is early research. We need:
- More benchmark results (other models, other domains)
- Better error-pattern extraction (currently hardcoded strategies)
- A VS Code extension (prototype CLI exists)
- Causal error analysis (why did this fix work?)

Open an issue or PR. See [ROADMAP.md](docs/ROADMAP.md) for planned work.

---

## Citation

```bibtex
@misc{puzzlelogic2025,
  title={Puzzle Logic AI: Constraint-Satisfaction Reasoning for Local LLM Agents},
  author={[Your name]},
  year={2025},
  howpublished={\url{https://github.com/fjdhsbcoge/puzzle-logic-ai}}
}
```

---

## License

MIT
