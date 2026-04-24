"""
HumanEval Runner WITH Knowledge Graph — Generalization Test
=============================================================

This benchmark tests whether the Knowledge Graph enables GENERALIZATION,
not memorization.

Design:
  1. SPLIT problems into two disjoint sets:
     - TRAIN set: ~60% of problems (solved without KG, stored in KG)
     - TEST set:  ~40% of problems (never seen before)
  2. Solve TRAIN problems WITHOUT knowledge graph help
     → Store every success in the ValidatedKnowledgeGraph
  3. Solve TEST problems WITH knowledge graph help
     → KG retrieves SIMILAR past solutions as few-shot examples
     → Model has NEVER seen these exact problems before
  4. ALSO solve TEST problems WITHOUT knowledge graph
     → Baseline: how well does the model do on its own?
  5. Compare: does KG help on genuinely new problems?

This tests the REAL question: does accumulating validated knowledge
about one set of problems help you solve a DIFFERENT set?
"""

import json
import os
import sys
import tempfile
import argparse
import re
from typing import List, Dict, Any

from lmstudio_client import LMStudioClient
from validated_knowledge_graph import ValidatedKnowledgeGraph


HUMANEVAL_PATH = os.path.join(os.path.dirname(__file__), "HumanEval.jsonl")

# Medium subset — 15 problems total
MEDIUM_SUBSET = [3, 5, 8, 10, 12, 16, 26, 28, 29, 30, 31, 36, 42, 43, 48]

# Split: first 9 are TRAIN, last 6 are TEST
# TRAIN (indices 0-8): 3, 5, 8, 10, 12, 16, 26, 28, 29
# TEST  (indices 9-14): 30, 31, 36, 42, 43, 48
TRAIN_COUNT = 9


def load_humaneval(subset_indices=None) -> List[Dict[str, Any]]:
    problems = []
    with open(HUMANEVAL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            problems.append(json.loads(line))
    if subset_indices:
        return [problems[i] for i in subset_indices if i < len(problems)]
    return problems


def extract_code(text: str) -> str:
    """Extract code from model output."""
    if not text:
        return ""
    match = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    if "def " in text or "return" in text or "for " in text or "if " in text:
        return text.strip()
    return ""


def run_test(problem: Dict, completion: str) -> Dict:
    """Test a completion against HumanEval test cases."""
    test_program = (
        problem["prompt"] + "\n" +
        completion + "\n" +
        problem["test"] + "\n" +
        f"check({problem['entry_point']})\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(test_program)
        temp_path = f.name
    try:
        import subprocess
        result = subprocess.run([sys.executable, temp_path], capture_output=True, text=True, timeout=5)
        passed = result.returncode == 0
        error = result.stderr if not passed else None
        if error and len(error) > 300:
            error = error[:300] + "..."
        return {"passed": passed, "error": error}
    except subprocess.TimeoutExpired:
        return {"passed": False, "error": "Timeout"}
    except Exception as e:
        return {"passed": False, "error": str(e)}
    finally:
        os.unlink(temp_path)


def build_prompt(problem: Dict, few_shot: str = "") -> str:
    """Build prompt with optional few-shot from knowledge graph."""
    base = problem["prompt"]
    instruction = (
        "\n\nComplete the function above. Output the code inside a markdown code block.\n"
        "You may output either the full function or just the function body."
    )
    if few_shot:
        return few_shot + "\n\nNow solve this new problem:\n\n" + base + instruction
    return base + instruction


def solve_problem(problem: Dict, synapse: LMStudioClient, kg: ValidatedKnowledgeGraph,
                  n_candidates: int = 3, use_kg: bool = True) -> Dict:
    """Solve a single problem with optional Knowledge Graph assistance."""
    task_id = problem["task_id"]
    
    # Get few-shot example from KG if available
    few_shot = ""
    if use_kg:
        few_shot = kg.build_few_shot_prompt(problem["prompt"], problem["entry_point"])
        if few_shot:
            print(f"    [KG] Found similar past solution as few-shot example")
    
    prompt = build_prompt(problem, few_shot)
    
    previous_errors = []
    
    for attempt in range(1, n_candidates + 1):
        if previous_errors:
            feedback = "\n\nNOTE: Previous attempt did not pass tests. Please try again."
            attempt_prompt = prompt + feedback
        else:
            attempt_prompt = prompt
        
        raw = synapse.generate(prompt=attempt_prompt, temperature=0.3, max_tokens=1024, n=1)
        
        if not raw or not raw[0].strip():
            previous_errors.append("Empty generation")
            continue
        
        completion = extract_code(raw[0])
        if not completion:
            previous_errors.append("No code extracted")
            continue
        
        test_result = run_test(problem, completion)
        
        if test_result["passed"]:
            # Store in KG if this is a training problem
            kg.add_solution(
                task_id=task_id,
                problem_description=problem["prompt"].split("\n")[1] if len(problem["prompt"].split("\n")) > 1 else task_id,
                solution_code=completion,
                reasoning_trace="",
                test_summary="All tests passed",
                attempts=attempt
            )
            return {
                "task_id": task_id,
                "passed": True,
                "attempts": attempt,
                "used_kg": bool(few_shot),
                "error": None
            }
        else:
            previous_errors.append(test_result["error"])
    
    return {
        "task_id": task_id,
        "passed": False,
        "attempts": n_candidates,
        "used_kg": bool(few_shot),
        "error": previous_errors[-1] if previous_errors else "unknown"
    }


def run_benchmark(problems: List[Dict], synapse: LMStudioClient, kg: ValidatedKnowledgeGraph,
                  n_candidates: int = 3, use_kg: bool = True) -> List[Dict]:
    """Run benchmark on a set of problems."""
    results = []
    total = len(problems)
    
    mode_name = "WITH Knowledge Graph" if use_kg else "WITHOUT Knowledge Graph"
    print(f"\n[RUNNING] {mode_name} - {total} problems...")
    print("-" * 60)
    
    for i, problem in enumerate(problems, 1):
        task_id = problem["task_id"]
        result = solve_problem(problem, synapse, kg, n_candidates=n_candidates, use_kg=use_kg)
        results.append(result)
        
        status = "PASS" if result["passed"] else "FAIL"
        kg_indicator = " (KG)" if result["used_kg"] else ""
        print(f"  [{i}/{total}] {task_id}: {status}{kg_indicator} (attempts: {result['attempts']})")
    
    return results


def print_comparison(train_results: List[Dict], test_baseline: List[Dict], test_with_kg: List[Dict],
                     kg_stats: Dict):
    """Print the generalization comparison."""
    print("\n" + "=" * 70)
    print("HUMANEVAL: KNOWLEDGE GRAPH GENERALIZATION TEST")
    print("=" * 70)
    
    train_passed = sum(1 for r in train_results if r["passed"])
    test_base_passed = sum(1 for r in test_baseline if r["passed"])
    test_kg_passed = sum(1 for r in test_with_kg if r["passed"])
    
    print(f"\n--- TRAIN SET ({len(train_results)} problems, NEVER seen by test) ---")
    print(f"  Solved: {train_passed}/{len(train_results)} -> stored in Knowledge Graph")
    
    print(f"\n--- TEST SET ({len(test_baseline)} problems, COMPLETELY NEW) ---")
    print(f"  Without KG: {test_base_passed}/{len(test_baseline)} passed")
    print(f"  With KG:    {test_kg_passed}/{len(test_baseline)} passed")
    
    improvement = (test_kg_passed - test_base_passed) / len(test_baseline) * 100
    
    # How many were saved by KG?
    kg_saved = sum(1 for b, k in zip(test_baseline, test_with_kg)
                   if not b["passed"] and k["passed"])
    kg_harmed = sum(1 for b, k in zip(test_baseline, test_with_kg)
                    if b["passed"] and not k["passed"])
    
    print(f"\n--- KEY METRIC: GENERALIZATION ---")
    print(f"  Improvement: {improvement:+.1f} percentage points")
    print(f"  NEW problems saved by KG: {kg_saved}")
    print(f"  NEW problems harmed by KG: {kg_harmed}")
    print(f"  Knowledge Graph entries: {kg_stats['n_solutions']}")
    
    print("\n" + "=" * 70)
    print("INTERPRETATION")
    print("=" * 70)
    
    if kg_saved > 0 and kg_harmed == 0:
        print("SUCCESS: The Knowledge Graph enables genuine generalization.")
        print("The agent solved NEW problems by applying knowledge from OLD problems.")
        print("This is NOT memorization — the test problems were never seen before.")
    elif kg_saved > 0:
        print("PARTIAL: The Knowledge Graph helps on some new problems,")
        print("but causes regressions on others. The few-shot examples")
        print("sometimes confuse the model.")
    elif improvement > 0:
        print("MODEST: Slight improvement, but not from generalization.")
        print("The multi-candidate mechanism is the main driver.")
    else:
        print("NO GENERALIZATION: The Knowledge Graph did not help on new problems.")
        print("Possible reasons:")
        print("  - Train and test problems are too different")
        print("  - The similarity matching is too crude")
        print("  - The model doesn't know how to adapt examples to new contexts")
    
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset", choices=["medium", "hard", "full"], default="medium")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--output", type=str, default="humaneval_kg_results.json")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    
    if not os.path.exists(HUMANEVAL_PATH):
        print(f"ERROR: HumanEval not found at {HUMANEVAL_PATH}")
        sys.exit(1)
    
    # Load problems
    if args.subset == "medium":
        problems = load_humaneval(subset_indices=MEDIUM_SUBSET)
        print(f"MEDIUM subset: {len(problems)} problems")
    elif args.subset == "hard":
        problems = load_humaneval(subset_indices=HARD_SUBSET)
        print(f"HARD subset: {len(problems)} problems")
    else:
        problems = load_humaneval()
        print(f"FULL benchmark: {len(problems)} problems")
    
    # Split into train and test
    train_problems = problems[:TRAIN_COUNT]
    test_problems = problems[TRAIN_COUNT:]
    
    print(f"Split: {len(train_problems)} TRAIN + {len(test_problems)} TEST")
    print(f"Train problems: {[p['task_id'] for p in train_problems]}")
    print(f"Test problems:  {[p['task_id'] for p in test_problems]}")
    
    print("=" * 70)
    print("PUZZLE LOGIC AI - KNOWLEDGE GRAPH GENERALIZATION TEST")
    print("=" * 70)
    print()
    print("This benchmark tests whether the Knowledge Graph enables")
    print("GENERALIZATION to new problems, not just memorization.")
    print()
    print("Train set: 9 problems solved WITHOUT KG -> stored in KG")
    print("Test set:  6 problems the model has NEVER seen")
    print("           solved WITH and WITHOUT KG -> compare")
    print()
    print("Key question: Does knowing about 'count vowels' help")
    print("             the model solve 'count consonants'?")
    print("-" * 70)
    
    synapse = LMStudioClient()
    print("\n[CHECK] LM Studio...")
    if not synapse.check_health():
        print("  NOT RUNNING")
        sys.exit(1)
    print("  OK")
    
    # Setup fresh knowledge graph
    kg_path = "humaneval_knowledge_graph.json"
    if os.path.exists(kg_path):
        os.remove(kg_path)
    kg = ValidatedKnowledgeGraph(storage_path=kg_path)
    
    # Phase 1: Train — solve train problems WITHOUT KG
    print("\n" + "=" * 70)
    print("PHASE 1: TRAIN (no KG help)")
    print("=" * 70)
    train_results = run_benchmark(train_problems, synapse, kg, n_candidates=args.k, use_kg=False)
    
    # Show what was learned
    stats = kg.get_stats()
    print(f"\n[LEARNED] {stats['n_solutions']} solutions stored in Knowledge Graph")
    kg.print_contents()
    kg.save_readable("kg_after_train.txt")
    
    # Phase 2: Test baseline — solve test problems WITHOUT KG
    print("\n" + "=" * 70)
    print("PHASE 2A: TEST WITHOUT KG (baseline)")
    print("=" * 70)
    test_baseline_results = run_benchmark(test_problems, synapse, kg, n_candidates=args.k, use_kg=False)
    
    # IMPORTANT: Remove test solutions from KG so they can't be memorized
    # The KG should only contain train solutions
    # (The solve_problem function stores successes, so we need to remove test ones)
    for result in test_baseline_results:
        kg.solutions = [s for s in kg.solutions if s.task_id != result["task_id"]]
    kg._save()
    
    # Phase 3: Test with KG — solve SAME test problems WITH KG
    print("\n" + "=" * 70)
    print("PHASE 2B: TEST WITH KG (generalization)")
    print("=" * 70)
    print("The model has NEVER seen these test problems.")
    print("But it has validated solutions for similar train problems.")
    print("-" * 70)
    test_kg_results = run_benchmark(test_problems, synapse, kg, n_candidates=args.k, use_kg=True)
    
    # Show final KG state
    print(f"\n[FINAL] Knowledge Graph after all phases:")
    kg.print_contents()
    kg.save_readable("kg_final.txt")
    
    # Comparison
    print_comparison(train_results, test_baseline_results, test_kg_results, kg.get_stats())
    
    # Save results
    data = {
        "benchmark": "HumanEval",
        "subset": args.subset,
        "train_problems": [p["task_id"] for p in train_problems],
        "test_problems": [p["task_id"] for p in test_problems],
        "train_results": train_results,
        "test_baseline": test_baseline_results,
        "test_with_kg": test_kg_results,
        "kg_stats": kg.get_stats()
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"\nResults saved to: {args.output}")
    
    # Cleanup
    if os.path.exists(kg_path):
        os.remove(kg_path)
    
    print("\nDone.")


if __name__ == "__main__":
    main()
