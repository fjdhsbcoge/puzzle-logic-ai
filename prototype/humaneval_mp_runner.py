"""
HumanEval Runner WITH Mistake-Pattern Knowledge Graph
======================================================

This runner integrates the MP-KG (Mistake-Pattern Knowledge Graph).

RULE: Prevention hints are ONLY injected after the SECOND failure
of the same category on the same problem.

Flow per problem:
  Attempt 1: Generate solution
    - If passes: done
    - If fails: categorize error, record in MP-KG, NO injection
  Attempt 2: Generate solution (same prompt as attempt 1)
    - If passes: done  
    - If fails: categorize error. Is it SAME category as attempt 1?
      - YES: inject prevention rule into prompt
      - NO: just try again
  Attempt 3: Generate solution (with prevention rule if applicable)
    - If passes: mark pattern as helpful
    - If fails: record, done

This prevents prompt bloat while providing targeted help when stuck.
"""

import json
import os
import sys
import tempfile
import argparse
import re
from typing import List, Dict, Any
from collections import Counter

from lmstudio_client import LMStudioClient
from mistake_pattern_kg import MistakePatternKnowledgeGraph


HUMANEVAL_PATH = os.path.join(os.path.dirname(__file__), "HumanEval.jsonl")
MEDIUM_SUBSET = [3, 5, 8, 10, 12, 16, 26, 28, 29, 30, 31, 36, 42, 43, 48]


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


def build_prompt(problem: Dict, prevention_hint: str = "") -> str:
    """Build prompt with optional prevention hint."""
    base = problem["prompt"]
    instruction = (
        "\n\nComplete the function above. Output the code inside a markdown code block.\n"
        "You may output either the full function or just the function body."
    )
    if prevention_hint:
        # Place hint right before the problem for maximum relevance
        return (
            "PREVENTION HINT: " + prevention_hint + "\n\n" +
            "Now solve this problem:\n\n" + base + instruction
        )
    return base + instruction


def solve_problem(problem: Dict, synapse: LMStudioClient, mp_kg: MistakePatternKnowledgeGraph,
                  n_candidates: int = 3) -> Dict:
    """
    Solve a problem with Mistake-Pattern KG.
    
    Key rule: prevention hint only injected after 2nd failure of same category.
    """
    task_id = problem["task_id"]
    failure_categories = []  # Track error categories across attempts
    
    for attempt in range(1, n_candidates + 1):
        # Determine if we should inject a prevention hint
        prevention_hint = ""
        if attempt >= 2 and failure_categories:
            # Check if any category has failed at least twice
            hint = mp_kg.should_inject(failure_categories)
            if hint and attempt == 2:
                # Only inject on attempt 2 if it's the activation attempt
                prevention_hint = hint
                print(f"    [MP-KG] Activating prevention hint (2nd failure of same type)")
        
        prompt = build_prompt(problem, prevention_hint)
        
        raw = synapse.generate(prompt=prompt, temperature=0.3, max_tokens=1024, n=1)
        
        if not raw or not raw[0].strip():
            failure_categories.append("empty_generation")
            continue
        
        completion = extract_code(raw[0])
        if not completion:
            failure_categories.append("extraction_failure")
            continue
        
        test_result = run_test(problem, completion)
        
        if test_result["passed"]:
            # Success! If we used a prevention hint, record it as helpful
            if prevention_hint and failure_categories:
                # Find the category that triggered the hint
                counts = Counter(failure_categories)
                for cat, count in counts.items():
                    if count >= 2:
                        mp_kg.record_success_after_hint(cat)
                        print(f"    [MP-KG] Prevention rule for '{cat}' was HELPFUL")
                        break
            return {
                "task_id": task_id,
                "passed": True,
                "attempts": attempt,
                "used_prevention": bool(prevention_hint),
                "error": None
            }
        else:
            # Failure: categorize and record
            category = mp_kg.record_failure(task_id, test_result["error"])
            if category:
                failure_categories.append(category)
                print(f"    [MP-KG] Failure categorized as: {category}")
            else:
                failure_categories.append("uncategorized")
    
    return {
        "task_id": task_id,
        "passed": False,
        "attempts": n_candidates,
        "used_prevention": False,
        "error": "All attempts failed"
    }


def run_benchmark(problems: List[Dict], synapse: LMStudioClient,
                  mp_kg: MistakePatternKnowledgeGraph, n_candidates: int = 3) -> List[Dict]:
    """Run the full benchmark with Mistake-Pattern KG."""
    results = []
    total = len(problems)
    
    print(f"\n[RUNNING] With Mistake-Pattern KG - {total} problems...")
    print("-" * 60)
    
    for i, problem in enumerate(problems, 1):
        task_id = problem["task_id"]
        result = solve_problem(problem, synapse, mp_kg, n_candidates=n_candidates)
        results.append(result)
        
        status = "PASS" if result["passed"] else "FAIL"
        prevention_indicator = " (PREVENTION)" if result.get("used_prevention") else ""
        print(f"  [{i}/{total}] {task_id}: {status}{prevention_indicator} (attempts: {result['attempts']})")
    
    return results


def print_comparison(base_results: List[Dict], mp_results: List[Dict], mp_kg: MistakePatternKnowledgeGraph):
    """Print the comparison."""
    print("\n" + "=" * 70)
    print("HUMANEVAL: MISTAKE-PATTERN KNOWLEDGE GRAPH RESULTS")
    print("=" * 70)
    
    base_passed = sum(1 for r in base_results if r["passed"])
    mp_passed = sum(1 for r in mp_results if r["passed"])
    total = len(base_results)
    
    base_rate = base_passed / total * 100
    mp_rate = mp_passed / total * 100
    improvement = mp_rate - base_rate
    
    saved = sum(1 for b, m in zip(base_results, mp_results) if not b["passed"] and m["passed"])
    harmed = sum(1 for b, m in zip(base_results, mp_results) if b["passed"] and not m["passed"])
    prevention_uses = sum(1 for r in mp_results if r.get("used_prevention"))
    
    print(f"\n{'Metric':<35} {'Base':<12} {'MP-KG':<12}")
    print("-" * 70)
    print(f"{'Problems solved':<35} {base_passed}/{total:<12} {mp_passed}/{total}")
    print(f"{'Pass rate':<35} {base_rate:.1f}%{'':<8} {mp_rate:.1f}%")
    print(f"{'Problems saved by MP-KG':<35} {'-':<12} {saved}")
    print(f"{'Problems harmed by MP-KG':<35} {'-':<12} {harmed}")
    print(f"{'Prevention hints activated':<35} {'-':<12} {prevention_uses}")
    
    print("\n" + "-" * 70)
    print(f"IMPROVEMENT: {improvement:+.1f} percentage points")
    if improvement > 0 and base_passed > 0:
        print(f"RELATIVE GAIN: {(mp_passed - base_passed) / base_passed * 100:.0f}% more problems solved")
    elif improvement < 0:
        print(f"REGRESSION: MP-KG scored {abs(improvement):.1f} points LOWER")
    
    print("\n" + "=" * 70)
    
    # Show learned patterns
    mp_kg.print_contents()
    
    print("\n" + "=" * 70)
    print("INTERPRETATION")
    print("=" * 70)
    
    if saved > 0 and harmed == 0:
        print("SUCCESS: Mistake-pattern prevention enables genuine recovery.")
        print("The agent learned from failures and prevented repeats.")
    elif saved > harmed:
        print("POSITIVE: Net benefit from mistake-pattern prevention.")
    elif saved == 0 and harmed == 0:
        print("NEUTRAL: No change. The model did not get stuck on repeated errors.")
    else:
        print("STILL HURTING: The prevention rules are distracting the model.")
    
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["base", "mp", "both"], default="both")
    parser.add_argument("--subset", choices=["medium", "hard", "full"], default="medium")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--output", type=str, default="humaneval_mp_results.json")
    args = parser.parse_args()
    
    if not os.path.exists(HUMANEVAL_PATH):
        print(f"ERROR: HumanEval not found at {HUMANEVAL_PATH}")
        sys.exit(1)
    
    if args.subset == "medium":
        problems = load_humaneval(subset_indices=MEDIUM_SUBSET)
        print(f"MEDIUM subset: {len(problems)} problems")
    else:
        problems = load_humaneval()
        print(f"FULL benchmark: {len(problems)} problems")
    
    print("=" * 70)
    print("PUZZLE LOGIC AI - MISTAKE-PATTERN KNOWLEDGE GRAPH")
    print("=" * 70)
    print()
    print("RULE: Prevention hints ONLY injected after 2nd failure of same type.")
    print("This prevents prompt bloat while helping when genuinely stuck.")
    print()
    print("Example flow:")
    print("  Attempt 1: FAIL with 'empty input' -> record, NO injection")
    print("  Attempt 2: FAIL with 'empty input' -> NOW inject 'guard empty sequences'")
    print("  Attempt 3: Generate with prevention hint -> hopefully PASS")
    print("-" * 70)
    
    synapse = LMStudioClient()
    print("\n[CHECK] LM Studio...")
    if not synapse.check_health():
        print("  NOT RUNNING")
        sys.exit(1)
    print("  OK")
    
    # Fresh MP-KG
    mp_path = "mistake_patterns.json"
    if os.path.exists(mp_path):
        os.remove(mp_path)
    mp_kg = MistakePatternKnowledgeGraph(storage_path=mp_path)
    
    base_results = []
    mp_results = []
    
    if args.mode in ("base", "both"):
        print("\n" + "=" * 70)
        print("BASELINE (no mistake-pattern help)")
        print("=" * 70)
        # Run without MP-KG by temporarily using an empty one
        empty_kg = MistakePatternKnowledgeGraph(storage_path="/dev/null")
        base_results = run_benchmark(problems, synapse, empty_kg, n_candidates=args.k)
    
    if args.mode in ("mp", "both"):
        # Reset MP-KG to empty for fair comparison if both modes
        if args.mode == "both":
            if os.path.exists(mp_path):
                os.remove(mp_path)
            mp_kg = MistakePatternKnowledgeGraph(storage_path=mp_path)
        
        print("\n" + "=" * 70)
        print("MISTAKE-PATTERN KG")
        print("=" * 70)
        mp_results = run_benchmark(problems, synapse, mp_kg, n_candidates=args.k)
    
    if args.mode == "both" and base_results and mp_results:
        print_comparison(base_results, mp_results, mp_kg)
        
        data = {
            "benchmark": "HumanEval",
            "subset": args.subset,
            "n_problems": len(problems),
            "base_mode": {"pass_rate": sum(1 for r in base_results if r["passed"]) / len(base_results),
                          "results": base_results},
            "mp_mode": {"pass_rate": sum(1 for r in mp_results if r["passed"]) / len(mp_results),
                        "results": mp_results},
            "mp_kg_stats": mp_kg.get_stats()
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"\nResults saved to: {args.output}")
    
    if os.path.exists(mp_path):
        os.remove(mp_path)
    
    print("\nDone.")


if __name__ == "__main__":
    main()
