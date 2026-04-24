# Puzzle Logic AI

> **A single-parameter epistemology for artificial intelligence.**

---

## What This Is

Puzzle Logic AI is a fundamentally different approach to machine reasoning. Instead of treating knowledge as statistical pattern matching, it treats knowledge as **structural assembly** — empirical observations are puzzle pieces that must fit together via hard constraints. Pieces that don't fit are rejected. The system learns by assembling an increasingly coherent picture of reality.

The entire epistemic stance is controlled by **a single parameter: Omega (Ω)** — openness to being proved wrong.

This repository documents the concept, the neuroscience behind it, the formal architecture, and a roadmap for building a self-correcting coding agent based on these principles.

---

## The Core Insight

### The Puzzle Axiom

> **"The best approximation of reality is the test or a measurement."**

Every piece of knowledge enters the system as an empirical observation. There are no axioms, no assumed truths — only measurements and the constraints that bind them together. A false claim has no slot in the puzzle; it cannot be forced into place.

### The Single Parameter

> **Omega (Ω) ∈ [0, 1] — Openness to being proved wrong.**

After 25 years of empirical calibration, the core insight is that a reasoning system's entire stance toward contradiction can be captured by one number:

| Ω Value | Stance | Behavior |
|---------|--------|----------|
| **0.0** | Dogmatic | Never changes mind. Rejects all contradictions. |
| **0.3** | Expert | Low openness. Strong priors. Efficient recognition. |
| **0.5** | Balanced | Moderate openness. Rejects noise, accepts signal. |
| **0.8** | Novice | High openness. Exploratory. Accumulates patterns rapidly. |
| **1.0** | Chaotic | No stability. Every contradiction triggers full revision. |

The learning curve is a **decay of Ω** — from high openness (novice) to calibrated expertise (master).

---

## Architecture: Synapse × Operating System

Puzzle Logic AI separates two layers that current AI systems conflate:

```
┌─────────────────────────────────────┐
│     OPERATING SYSTEM (Puzzle Logic) │
│     ┌──────────┐  ┌─────────────┐   │
│     │ Belief   │  │  Ω          │   │
│     │ Graph    │  │  Controller │   │
│     └──────────┘  └─────────────┘   │
│     ┌─────────────────────────────┐  │
│     │   Constraint Engine         │  │
│     │   (Compiler / Tests / Types)│  │
│     └─────────────────────────────┘  │
└──────────────┬──────────────────────┘
               │ (proposes / validates)
┌──────────────┴──────────────────────┐
│     SYNAPSE (Neural Network)        │
│     ┌─────────────────────────────┐  │
│     │  DeepSeek / Qwen / etc.     │  │
│     │  Local model via LM Studio  │  │
│     └─────────────────────────────┘  │
└─────────────────────────────────────┘
```

| Layer | Function | Status |
|-------|----------|--------|
| **Synapse** | Proposes candidate code, generates hypotheses | Use existing models (DeepSeek, Qwen) |
| **Operating System** | Validates candidates against constraints, maintains belief graph, controls Ω | **To be built** |

The Synapse proposes. The OS disposes. This separation is what makes the system self-correcting.

---

## Why Current AI Is Different

| | Standard LLM | Puzzle Logic AI |
|---|---|---|
| **Truth criterion** | Statistical likelihood | Empirical fit to constraints |
| **Handling contradictions** | Soft weighting, averaging | Structural rejection or reassembly |
| **Confidence** | Probability score | Convergence of constraint satisfaction |
| **Falsification** | Requires retraining | Immediate (piece doesn't fit) |
| **Key parameters** | Dozens of hyperparameters | **One: Ω** |
| **Learns from use** | No | Yes (Ω decays with experience) |

---

## The Coding Agent Vision

The first application: a coding agent that actually learns your codebase.

1. **You describe a task** — "Add a tax calculation function"
2. **The Synapse proposes 5 candidate implementations**
3. **The OS evaluates each**: Does it compile? Do types match? Do tests pass? Does it fit the architecture?
4. **The Ω-gate decides**: If tension < (1 − Ω), accept. If tension exceeds threshold, reject or trigger reassembly.
5. **The agent learns**: Each accepted piece increases experience, decays Ω, builds the belief graph.

Current agents (Copilot, Cursor, Claude Code) have no operating system. They are synapse-only — sophisticated pattern matchers with no persistent model of your project, no constraint enforcement, and no ability to learn from structural contradictions.

---

## Documents in This Repository

| Document | What It Covers |
|----------|---------------|
| [`CONCEPT.md`](CONCEPT.md) | The core Puzzle Logic philosophy and epistemology |
| [`OMEGA_PARAMETER.md`](OMEGA_PARAMETER.md) | The Ω parameter formalization — precision-gated belief revision |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | The Synapse × OS architecture for the coding agent |
| [`ROADMAP.md`](ROADMAP.md) | Development phases, milestones, and open questions |
| [`REFERENCES.md`](REFERENCES.md) | Academic sources — neuroscience, philosophy, AI |

---

## Model Recommendation

**Primary target: DeepSeek R1-0528-Qwen3-8B** via [LM Studio](https://lmstudio.ai/models/deepseek/deepseek-r1-0528-qwen3-8b)

This model is particularly suited because:
- It is a **reasoning model** — its chain-of-thought output can serve as the bridge between Synapse and OS
- 8B parameters — runs locally on consumer hardware
- The reasoning traces provide natural "structural tension" signals the OS can evaluate
- Local execution keeps data private and eliminates API costs

Other compatible models: Qwen2.5-Coder 7B, DeepSeek-Coder 6.7B, CodeLlama 7B.

---

## Status

**Phase: Concept & Architecture**

This repository contains the conceptual framework, formal model, and architecture specification. Implementation has not yet begun. We are actively seeking collaborators with expertise in:

- Constraint programming and knowledge representation
- Local LLM inference and tool use
- Neuro-symbolic AI architectures
- Compiler and type system integration
- Truth maintenance systems

See [`ROADMAP.md`](ROADMAP.md) for detailed next steps.

---

## How to Contribute

This is an open research project. Contributions are welcome in several forms:

- **Discussion**: Open an issue to discuss the concept, challenge assumptions, or propose alternatives
- **Implementation**: Pick a component from the architecture and prototype it
- **Domain expertise**: Apply the Puzzle Logic framework to a domain you know well
- **Critique**: The framework values falsification. If you find a flaw, that is the most valuable contribution.

See [`ROADMAP.md`](ROADMAP.md) for specific tasks and priorities.

---

## License

MIT License — see [`LICENSE`](LICENSE).

---

> *"A puzzle only fits in one way."*
