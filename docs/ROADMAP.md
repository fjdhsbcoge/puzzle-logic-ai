# Roadmap

## Status: Phase 0 — Concept & Architecture

We have the conceptual framework, formal model, and architecture specification. Implementation has not yet begun. This document outlines the path from concept to working system.

---

## Phase 1: Minimum Viable Prototype

**Goal:** Demonstrate that the Ω-gated decision loop works for a trivial coding task.

### Components
- [ ] **Synapse wrapper**: Interface to LM Studio (DeepSeek R1-0528-Qwen3-8B) via local API
- [ ] **Belief Graph (minimal)**: A simple data structure tracking function names, signatures, and types
- [ ] **Constraint Engine (hard constraints only)**: Compiler exit code, type checker output
- [ ] **Ω controller**: Fixed initial Ω (0.7), no decay yet
- [ ] **Decision loop**: Generate → Compile → Score → Accept/Reject

### Validation Task
Given a Python file with one function and one test, ask the agent to:
1. Add a second function
2. The OS checks: does it compile? Does the test still pass?
3. Accept or reject based on Ω-gated tension

### Success Criterion
The agent accepts code that compiles and passes tests, and rejects code that breaks them. The Ω parameter visibly shifts the acceptance threshold.

---

## Phase 2: Self-Correction

**Goal:** The agent triggers reassembly when code breaks constraints.

### Components
- [ ] **Reassembly Engine**: When a candidate is rejected, try minimal modifications
- [ ] **Dependency tracking**: Which beliefs are affected by a code change
- [ ] **Ω decay**: Experience counter, decay function, domain novelty detection
- [ ] **Belief Graph expansion**: Track function contracts, not just signatures

### Validation Task
Same as Phase 1, but now the agent:
1. Generates a candidate that breaks a test
2. Detects the structural tension
3. Revises its belief about the function's contract
4. Generates a corrected candidate

### Success Criterion
The agent recovers from its own errors without human intervention.

---

## Phase 3: Architecture Awareness

**Goal:** The agent maintains a model of project structure and architectural conventions.

### Components
- [ ] **Architectural constraints**: Detects patterns (MVC, layered architecture, etc.)
- [ ] **Style constraints**: Naming conventions, formatting, docstring requirements
- [ ] **Cross-module dependencies**: Tracks imports, interfaces between modules
- [ ] **Ω modulation**: Domain novelty detection, temporary Ω spikes for paradigm shifts

### Validation Task
A multi-file Python project with clear architectural conventions. The agent:
1. Understands the directory structure and module boundaries
2. Respects naming conventions when adding new code
3. Detects when a proposed change violates architectural boundaries
4. Adapts when a new paradigm is introduced (e.g., adding async code to a sync project)

### Success Criterion
The agent behaves like a junior developer who has read and understood the codebase.

---

## Phase 4: Persistent Expertise

**Goal:** The agent accumulates expertise across sessions and projects.

### Components
- [ ] **Belief Graph serialization**: Save/load the graph between sessions
- [ ] **Cross-project transfer**: Recognize similar patterns across different codebases
- [ ] **Metacognitive Ω controller**: Learn optimal Ω for different domains
- [ ] **Human-in-the-loop Level-3 reassembly**: Flag paradigm shifts for human review

### Validation Task
The agent works on the same project across multiple sessions. Over time:
- Ω decays from 0.8 to 0.3
- The agent makes fewer mistakes requiring reassembly
- It recognizes project-specific patterns without being reminded

### Success Criterion
The agent behaves like a developer who has been on the team for months.

---

## Open Questions

These are the hard problems that need solving:

1. **Constraint discovery**: How does the agent learn what the constraints *are* in a new codebase? In physics, constraints are explicit (Newton's laws). In code, many are implicit conventions.

2. **Tension quantification**: How do we weight different constraint violations (syntax error = 1.0, style mismatch = 0.2)? Is this learned or hardcoded?

3. **Reassembly cost**: How do we find the minimal belief revision efficiently? This is an NP-hard problem in general.

4. **Ω calibration**: How fast should Ω decay? Different domains may need different decay rates.

5. **Synapse quality**: How does Synapse quality affect the system? A worse model proposing more candidates may actually work better with a strong OS.

6. **Generalization beyond code**: Can this architecture generalize to other reasoning tasks (scientific inference, legal reasoning, medical diagnosis)?

---

## How to Contribute

### Immediate Needs
- **Prototype implementation**: A Python script demonstrating the Ω-gated loop
- **Synapse integration**: Code to call LM Studio's local API
- **Compiler/type checker integration**: Wrappers for `python -m py_compile`, `mypy`, etc.
- **Test harness**: A framework for running validation tasks and measuring success

### Discussion Wanted
- Challenge the single-parameter assumption — is Ω sufficient?
- Suggest domains where Puzzle Logic would fail
- Propose alternative Synapse architectures
- Share expertise on truth maintenance systems, constraint programming, or predictive processing

### Long-Term Collaborators
We are looking for people with deep expertise in:
- Neuro-symbolic AI architectures
- Compiler and type system design
- Knowledge representation and belief revision
- Local LLM deployment and optimization

---

*Last updated: April 2026*
