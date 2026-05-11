# 🏗️ Puzzle Logic Coding Agent: Architecture

## 🌐 Overview

A coding agent built on three layers:

1. **Synapse** — Local neural computation (pattern matching, candidate generation)
2. **Operating System** — Global constraint enforcement, belief assembly, Ω control
3. **Interface** — The empirical environment (compiler, type checker, test runner)

```
┌─────────────────────────────────────────────────────────────┐
│                    PUZZLE LOGIC OS (Global)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Belief      │  │  Constraint  │  │     Ω        │      │
│  │  Graph       │  │  Engine      │  │  Controller  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌─────────────────────────────────────────────────────┐    │
│  │         REASSEMBLY ENGINE (When contradicted)       │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              ↑ ↓
┌─────────────────────────────────────────────────────────────┐
│                    SYNAPTIC LAYER (Local)                    │
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  DeepSeek R1-0528-Qwen3-8B (or compatible model)    │   │
│   │  Running locally via LM Studio                      │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↑ ↓
┌─────────────────────────────────────────────────────────────┐
│                    INTERFACE LAYER (Environment)             │
│         ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│         │  Source  │  │ Compiler │  │  Tests   │          │
│         │   Code   │  │ (Syntax) │  │ (Logic)  │          │
│         └──────────┘  └──────────┘  └──────────┘          │
└─────────────────────────────────────────────────────────────┘
```

## ⚙️ The Control Flow

```
1. SYNAPSE proposes: "Here is a candidate code change"
           ↓
2. OS receives candidate piece p
           ↓
3. OS evaluates: Does p fit the current BELIEF GRAPH?
   - Syntax check (constraint: must compile)
   - Type check (constraint: must satisfy type system)
   - Test check (constraint: must not break existing tests)
   - Architectural check (constraint: must match design patterns)
           ↓
4. OS computes STRUCTURAL TENSION T(p)
   T = weighted sum of all constraint violations
           ↓
5. Ω-GATED DECISION:
   
   If T ≤ (1 − Ω):  → PIECE FITS → ACCEPT → Integrate into Belief Graph
   If T > (1 − Ω):  → CONTRADICTION → Two branches:
      
      5a. Reject the piece
          → "This code has no slot in our architecture"
          → Send negative reinforcement to Synapse
          
      5b. Trigger reassembly (puzzle is wrong)
          → "Our current model is incomplete; revise beliefs"
          → Find minimal revision to Belief Graph that accommodates p
          → If reassembly succeeds: ACCEPT + UPDATE
          → If reassembly fails: REJECT + FLAG FOR HUMAN REVIEW
```

## 🧠 The Belief Graph

Explicit structured representation of code knowledge:

```
BELIEF NODE (Code Entity)
├── identity: function name, class name, module path
├── signature: types, parameters, return value
├── contracts: preconditions, postconditions, invariants
├── dependencies: what this entity requires
├── dependents: what entities require this
├── test coverage: which tests validate this entity
├── confidence: how well-established this knowledge is (0–1)
└── source: where this knowledge came from

CONSTRAINT EDGE (Connection Rule)
├── source: BeliefNode A
├── target: BeliefNode B
├── type: 'type-compatibility' | 'interface-implementation' | 'dependency' | 'test-validates'
├── strength: how tight the fit must be (0–1)
└── validator: function that checks if constraint is satisfied
```

## 🔀 The Three-Level Reassembly Hierarchy

```
Level 1: Local rejection (piece doesn't fit this slot)
   → Try another piece. No belief revision.

Level 2: Local reassembly (nearby beliefs may be wrong)
   → Revise confidence of affected beliefs.
   → Try fitting the piece into a revised local structure.

Level 3: Global reassembly (fundamental contradiction)
   → Major Ω spike ("something is very wrong")
   → Consider: new paradigm? new requirement? misunderstanding?
   → Either reorganize the Belief Graph or flag for human review.
```

## ✨ Why This Is Different

| | GitHub Copilot | Claude Code | Puzzle Logic Agent |
|-----------|---------------|-------------|-------------------|
| **Code generation** | Pattern match | Reasoning + pattern | Synapse proposes, OS validates |
| **Project architecture** | No | Partial (RAG context) | Explicit Belief Graph |
| **Learns from errors** | No | Reactive (retry loop) | Errors = structural contradictions trigger reassembly |
| **Persistent model** | No | No | Persistent Belief Graph across sessions |
| **Rejects wrong code** | No | Sometimes | Constraint violation = structural rejection |
| **Learning curve** | Flat (static) | Flat (no learning) | Adaptive (Ω decays with experience) |
| **Explains suggestions** | No | Sometimes | Traces constraint satisfaction path |
| **Recovers from misunderstanding** | No | No | Dependency-directed backtracking |

## 🤖 Recommended Model

**DeepSeek R1-0528-Qwen3-8B** via [LM Studio](https://lmstudio.ai/models/deepseek/deepseek-r1-0528-qwen3-8b)

Particularly suited because:
- **Reasoning model** — chain-of-thought output serves as bridge between Synapse and OS
- 8B parameters — runs locally on consumer hardware
- Reasoning traces provide natural "structural tension" signals
- Local execution keeps data private

Compatible alternatives: Qwen2.5-Coder 7B, DeepSeek-Coder 6.7B.
