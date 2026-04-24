# The Omega (Ω) Parameter: Openness to Being Proved Wrong

## 25 Years of Calibration, One Number

The core insight of Puzzle Logic AI is that a reasoning system's entire epistemic stance — how it handles contradiction, when it changes its mind, when it holds firm — can be captured by **a single parameter**.

## Definition

**Ω ∈ [0, 1]** — *Precision-Weighted Receptivity*, or simply **Openness to being proved wrong**.

It controls how much structural contradiction (misfit) is required before the existing belief network is allowed to reorganize.

## The Decision Rule

For each incoming observation piece *p*:

1. Compute structural tension: **T(p)** = the degree to which *p* contradicts the current assembled puzzle
2. Compare to threshold: **(1 − Ω)**
3. Decide:

```
If T(p) > (1 − Ω):
    → ACCEPT the contradiction
    → Trigger local or global reassembly (update beliefs)
    → "I was proved wrong; the puzzle changes"
Else:
    → REJECT the piece
    → "This piece does not fit; it is false/incompatible"
```

## The Ω Spectrum

| Ω Value | Name | Behavior |
|---------|------|----------|
| **0.0** | Dogmatic | No contradiction can ever trigger reassembly. All conflicting data is rejected. |
| **0.2** | Conservative | Very strong evidence required to change mind. Most misfits rejected. |
| **0.5** | Balanced | Moderate contradiction triggers reassembly. The "reasonable threshold." |
| **0.8** | Receptive | Even small contradictions trigger updates. Highly adaptive. |
| **1.0** | Chaotic | Any misfit immediately triggers full reassembly. No stability. |

## The Learning Curve: Ω Decay

Expertise develops as Ω decays over experience:

| Phase | Ω | Description |
|-------|---|-------------|
| **Tabula Rasa** | 0.95 | Accept almost everything. Accumulate raw patterns rapidly. |
| **Pattern Accumulation** | 0.75 | Starting to reject obvious nonsense. Recognizing idioms. |
| **Structure Formation** | 0.55 | Major contradictions trigger reassembly. Architecture understood. |
| **Expert Consolidation** | 0.30 | Strong priors. Instantly recognizes anti-patterns. |
| **Master** | 0.15 + modulation | Base Ω is low, but selectively raised for genuinely novel domains. |

### The Decay Function

```python
omega = omega_asymptote + (omega_initial - omega_asymptote) * exp(-experience / tau)
```

With three modulating factors:
- **Experience**: Drives the base decay
- **Domain novelty**: Temporarily boosts Ω for unfamiliar territory
- **Recent success rate**: If predictions keep failing, raise Ω ("Maybe my model is wrong")

## Neuroscience Foundation

This parameter has a biological implementation. Under the Free Energy Principle (Karl Friston):

- The brain maintains a **generative model** of reality (the assembled puzzle)
- **Prediction errors** occur when reality contradicts the model
- **Neuromodulators** (dopamine, acetylcholine) control the **gain** on error neurons
- High gain = high Ω (errors are amplified, beliefs update easily)
- Low gain = low Ω (errors are suppressed, beliefs resist change)

Clinical evidence confirms that dysregulated precision weighting produces recognizable pathologies:
- **Too closed** → delusional rigidity
- **Too open** → OCD-like doubt and paralysis

Your 25-year calibration was the development of a healthy metacognitive Ω controller.

## Why This Matters for AI

Current AI systems have no Ω. They:
- Average conflicting information rather than rejecting it structurally
- Have no explicit belief graph to reorganize
- Cannot say "this piece does not fit" — only "this is plausible with probability 0.73"
- Require dozens of hyperparameters instead of one
- Do not learn from structural contradictions

Puzzle Logic AI puts Ω at the center. The system's entire epistemic stance is transparent, tunable, and grounded in empirical constraint satisfaction.
