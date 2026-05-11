# Changelog: From v2.0 to v2.4

## Philosophy Shift

The core philosophy hasn't changed -- empirical constraint satisfaction, knowledge as a jigsaw puzzle. But the *implementation* of that philosophy has evolved dramatically through real-world testing.

---

## What Changed

### v2.0 (Original Design) -> v2.4 (Current)

| Component | v2.0 (Old) | v2.4 (New) | Why |
|-----------|-----------|-----------|-----|
| **Knowledge Graph** | `ErrorPatternGraph` -- flat list of patterns | `CoherentKnowledgeGraph` -- with Omega, locality, and belief revision | The flat list couldn't build a coherent picture. Omega adds belief revision; locality distinguishes local from structural fixes |
| **Fix Strategy** | Static mapping from `infer_fix_strategy()` | Learned code deltas from failing -> passing code | The model learned what actually changed, not generic advice |
| **Confidence** | Naive increment/decrement | Multiplicative decay (x 0.8) + absolute boost (+0.1) | Multiplicative decay means patterns fade but are never truly forgotten |
| **Toolbox** | "Review each pattern and decide like a puzzle piece" | Local: direct fix. Unlocal: present the coherent picture | The 3B model couldn't handle the cognitive overhead of the old prompt |
| **Reassembly** | Didn't exist | Resets ALL same-type patterns to 0.5 when new fix discovered | A new validated constraint changes the entire picture -- everyone must re-earn their place |
| **Penalty** | None | Targeted: only the SPECIFIC shown patterns get penalized, not the whole error type | Penalizing all TypeErrors when only one pattern failed was too broad |
| **Quality Gate** | None | Toolbox only shown when verified patterns exist (times_fixed > 0) | Showing unverified generic advice poisoned the model |
| **Three-Tier Retry** | Same hint every retry | Attempt 2: high-conf verified. Attempt 3: low-conf verified. Fallback: raw error | Natural exploration-exploitation: exploit what works, explore what might |
| **Strategy Rotation** | Basic V2 only | Now in Advanced V2 fallback too | Without rotation, Advanced kept repeating failed strategies when toolbox was empty |
| **Lambda (Locality)** | Didn't exist | Auto-computed from error type + code delta size | Distinguishes "change one line" (NameError) from "restructure algorithm" (AssertionError) |
| **Benchmark** | HumanEval only | MBPP 420-problem three-way comparison | HumanEval was too easy (91%+ baseline). MBPP gives 38% baseline -- room to learn |
| **Runner** | `humaneval_compare_runner.py` | `mbpp_three_way_runner_v24.py` -- Baseline vs Basic V2 vs Advanced V2 | Three-way comparison isolates the value of each mechanism |
| **Pattern Protection** | Any fix overwrites matched pattern's strategy | No protection -- pollution is learning | Fix strategies collide and evolve naturally, like genes repurposing across domains |

---

## What Stayed The Same

| Component | Status |
|-----------|--------|
| **Core philosophy** | Empirical constraint satisfaction -- compiler output IS the constraint engine |
| **Synapse x OS architecture** | LLM generates candidates, OS validates against hard constraints |
| **Omega (Omega)** | Single parameter controlling openness to contradiction |
| **Error fingerprinting** | Extract (error_type, signature, failing_line) from tracebacks |
| **Subprocess sandbox** | `execute_code()` with timeout for safe execution |
| **Knowledge persistence** | JSON file that grows across sessions |
| **LM Studio / Ollama compatibility** | Works with any OpenAI-compatible local backend |

---

## Key Lessons Learned

1. **The 3B model is the bottleneck, not the architecture.** A 3B model can't consistently translate structured hints into correct code. The graph accumulates slowly because verification is rare.

2. **Retry + raw error is surprisingly strong.** Basic V2 (raw error + strategy rotation) consistently outperforms or matches the knowledge graph on small problem counts. The graph only helps when verified patterns have accumulated.

3. **The "coherent picture" emerges from decay, not structure.** We thought coherence would come from explicit graph edges. Instead, it comes from multiplicative decay killing bad patterns while good patterns survive and get reinforced.

4. **Pollution is feature, not bug.** Fix strategies collide and merge across problem types. This cross-domain transfer IS how generalization happens. The decay filters out the bad transfers.

5. **Never forget is more important than never fail.** A pattern that fixed something once stays in the graph at low confidence. It might help on a future problem where the context is right. Forgetting would lose that possibility.

---

*Last updated: 2026-04-28*
