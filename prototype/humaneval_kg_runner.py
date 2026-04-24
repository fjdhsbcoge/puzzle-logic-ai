"""
HumanEval Runner WITH Knowledge Graph — Compact Pattern Edition
================================================================

This benchmark tests whether the Knowledge Graph enables GENERALIZATION
using COMPACT PATTERNS, not full code injection.

Design:
  1. SPLIT into train (~60%) and test (~40%) — disjoint sets
  2. Solve TRAIN problems WITHOUT KG -> store compact patterns in KG
  3. Solve TEST problems WITH and WITHOUT KG -> compare

Key fix: The KG injects only 1-2 line pattern descriptions into prompts.
Full solutions are stored for inspection but NEVER injected.
This prevents the model from anchoring to wrong code structure.

Usage:
    python humaneval_kg_runner.py --mode both --subset medium
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

MEDIUM_SUBSET = [3, 5, 8, 10, 12, 16, 26, 28, 29, 30, 31, 36, 42, 43, 48]
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
    if not text:
        return ""
    match = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    if "def " in text or "return" in text or "for " in text or "if " in text:
        return text.strip()
    return ""


def run_test(problem: Dict, completion: str) -> Dict:
    test_program = (
        problem["prompt"] + "\n" + completion + "\n" +
        problem["test"] + "\n" + f"check({problem['entry_point']})\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(test_program)
        temp_path = f.name
    try:
        import subprocess
        result = subprocess.run([sys.executable, temp_path], capture_output=True, text=True, timeout=5)
        passed = result.returncode == 0
        error = result.stderr if not passed else None
        if error and len(error) > 200:
            error = error[:200] + "..."
        return {"passed": passed, "error": error}
    except subprocess.TimeoutExpired:
        return {"passed": False, "error": "Timeout"}
    except Exception as e:
        return {"passed": False, "error": str(e)}
    finally:
        os.unlink(temp_path)


def build_prompt(problem: Dict, compact_hint: str = "") -> str:
    """Build prompt with optional compact pattern hint."""
    base = problem["prompt"]
    instruction = (
        "\n\nComplete the function above. Output the code inside a markdown code block.\n"
        "You may output either the full function or just the function body."
    )
    if compact_hint:
        # Place the hint BEFORE the problem so it frames thinking
        return compact_hint + "\n\nNow solve this problem:\n\n" + base + instruction
    return base + instruction


def solve_problem(problem: Dict, synapse: LMStudioClient, kg: ValidatedKnowledgeGraph,
                  n_candidates: int = 3, use_kg: bool = True, store_in_kg: bool = True) -> Dict:
    """Solve a single problem. Optionally use KG compact hints."""
    task_id = problem["task_id"]

    # Get compact hint from KG
    compact_hint = ""
    if use_kg:
        compact_hint = kg.build_compact_prompt(problem["prompt"], problem["entry_point"])
        if compact_hint:
            print(f"    [KG] Compact hint: {compact_hint[:80]}...")

    prompt = build_prompt(problem, compact_hint)
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
            if store_in_kg:
                kg.add_solution(
                    task_id=task_id,
                    problem_description=problem["prompt"].split("\n")[1] if len(problem["prompt"].split("\n")) > 1 else task_id,
                    solution_code=completion,
                    compact_pattern="",  # Auto-generated
                    reasoning_trace="",
                    test_summary="All tests passed",
                    attempts=attempt
                )
            return {"task_id": task_id, "passed": True, "attempts": attempt,
                    "used_kg": bool(compact_hint), "error": None}
        else:
            previous_errors.append(test_result["error"])

    return {"task_id": task_id, "passed": False, "attempts": n_candidates,
            "used_kg": bool(compact_hint), "error": previous_errors[-1] if previous_errors else "unknown"}


def run_benchmark(problems: List[Dict], synapse: LMStudioClient, kg: ValidatedKnowledgeGraph,
                  n_candidates: int = 3, use_kg: bool = True, store_in_kg: bool = True) -> List[Dict]:
    """Run benchmark on a set of problems."""
    results = []
    total = len(problems)
    mode_name = "WITH KG compact hints" if use_kg else "WITHOUT Knowledge Graph"
    print(f"\n[RUNNING] {mode_name} - {total} problems...")
    print("-" * 60)

    for i, problem in enumerate(problems, 1):
        task_id = problem["task_id"]
        result = solve_problem(problem, synapse, kg, n_candidates=n_candidates,
                               use_kg=use_kg, store_in_kg=store_in_kg)
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        kg_indicator = " (KG hint)" if result.get("used_kg") else ""
        print(f"  [{i}/{total}] {task_id}: {status}{kg_indicator} (attempts: {result['attempts']})")

    return results


def print_comparison(train_results, test_baseline, test_with_kg, kg_stats):
    print("\n" + "=" * 70)
    print("HUMANEVAL: KNOWLEDGE GRAPH GENERALIZATION TEST")
    print("COMPACT PATTERN EDITION")
    print("=" * 70)

    train_passed = sum(1 for r in train_results if r["passed"])
    test_base_passed = sum(1 for r in test_baseline if r["passed"])
    test_kg_passed = sum(1 for r in test_with_kg if r["passed"])

    print(f"\n--- TRAIN SET ({len(train_results)} problems) ---")
    print(f"  Solved: {train_passed}/{len(train_results)} -> compact patterns stored in KG")

    print(f"\n--- TEST SET ({len(test_baseline)} problems, COMPLETELY NEW) ---")
    print(f"  Without KG: {test_base_passed}/{len(test_baseline)} passed")
    print(f"  With KG:    {test_kg_passed}/{len(test_baseline)} passed")

    improvement = (test_kg_passed - test_base_passed) / len(test_baseline) * 100 if test_baseline else 0
    kg_saved = sum(1 for b, k in zip(test_baseline, test_with_kg) if not b["passed"] and k["passed"])
    kg_harmed = sum(1 for b, k in zip(test_baseline, test_with_kg) if b["passed"] and not k["passed"])

    print(f"\n--- KEY METRIC ---")
    print(f"  Improvement: {improvement:+.1f} percentage points")
    print(f"  Problems saved by compact hints: {kg_saved}")
    print(f"  Problems harmed: {kg_harmed}")

    if kg_saved > 0 and kg_harmed == 0:
        print("\nSUCCESS: Compact pattern hints enable genuine generalization.")
    elif kg_saved > kg_harmed:
        print("\nPOSITIVE: Net benefit from compact pattern hints.")
    elif kg_harmed > 0:
        print("\nSTILL HURTING: Need further prompt tuning.")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["train", "test", "both"], default="both")
    parser.add_argument("--subset", choices=["medium", "hard", "full"], default="medium")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--output", type=str, default="humaneval_kg_results.json")
    args = parser.parse_args()

    if not os.path.exists(HUMANEVAL_PATH):
        print(f"ERROR: HumanEval not found at {HUMANEVAL_PATH}")
        sys.exit(1)

    if args.subset == "medium":
        problems = load_humaneval(subset_indices=MEDIUM_SUBSET)
        print(f"MEDIUM subset: {len(problems)} problems")
    elif args.subset == "hard":
        from humaneval_runner import HARD_SUBSET
        problems = load_humaneval(subset_indices=HARD_SUBSET)
        print(f"HARD subset: {len(problems)} problems")
    else:
        problems = load_humaneval()
        print(f"FULL benchmark: {len(problems)} problems")

    train_problems = problems[:TRAIN_COUNT]
    test_problems = problems[TRAIN_COUNT:]

    print(f"Split: {len(train_problems)} TRAIN + {len(test_problems)} TEST")

    print("=" * 70)
    print("PUZZLE LOGIC AI - KNOWLEDGE GRAPH (COMPACT PATTERNS)")
    print("=" * 70)
    print()
    print("Key fix: KG injects only 1-2 line pattern hints, NEVER full code.")
    print("Full solutions stored for inspection only.")
    print()
    print("Train: 9 problems solved WITHOUT KG -> compact patterns extracted")
    print("Test:  6 NEW problems solved WITH and WITHOUT KG hints -> compare")
    print("-" * 70)

    synapse = LMStudioClient()
    print("\n[CHECK] LM Studio...")
    if not synapse.check_health():
        print("  NOT RUNNING")
        sys.exit(1)
    print("  OK")

    kg_path = "humaneval_kg_compact.json"
    if os.path.exists(kg_path):
        os.remove(kg_path)
    kg = ValidatedKnowledgeGraph(storage_path=kg_path)

    if args.mode in ("train", "both"):
        print("\n" + "=" * 70)
        print("PHASE 1: TRAIN (no KG help, auto-extract compact patterns)")
        print("=" * 70)
        train_results = run_benchmark(train_problems, synapse, kg,
                                      n_candidates=args.k, use_kg=False, store_in_kg=True)
        print(f"\n[LEARNED] {kg.get_stats()['n_solutions']} compact patterns stored")
        kg.print_contents()

    if args.mode in ("test", "both"):
        print("\n" + "=" * 70)
        print("PHASE 2A: TEST WITHOUT KG (baseline)")
        print("=" * 70)
        test_baseline = run_benchmark(test_problems, synapse, kg,
                                      n_candidates=args.k, use_kg=False, store_in_kg=False)

        # Remove any test solutions that leaked into KG
        for result in test_baseline:
            kg.solutions = [s for s in kg.solutions if s.task_id != result["task_id"]]
        kg._save()

        print("\n" + "=" * 70)
        print("PHASE 2B: TEST WITH KG compact hints")
        print("=" * 70)
        test_with_kg = run_benchmark(test_problems, synapse, kg,
                                     n_candidates=args.k, use_kg=True, store_in_kg=False)

    if args.mode == "both":
        print_comparison(train_results, test_baseline, test_with_kg, kg.get_stats())

    if os.path.exists(kg_path):
        os.remove(kg_path)

    print("\nDone.")


if __name__ == "__main__":
    main()
