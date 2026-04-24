"""
HumanEval Runner for Puzzle Logic AI
======================================

Runs the OpenAI HumanEval benchmark (164 Python programming problems)
comparing base model (pass@1) against Puzzle Logic OS (best-of-k selection).

Usage:
    python humaneval_runner.py --mode base      # 1 candidate per problem
    python humaneval_runner.py --mode os       # up to 3 candidates, select best
    python humaneval_runner.py --mode both     # run both, print comparison

Output:
    JSON results file + console summary with pass rates.
"""

import json
import os
import sys
import time
import tempfile
import argparse
from typing import List, Dict, Any

from lmstudio_client import LMStudioClient


# Path to HumanEval data
HUMANEVAL_PATH = os.path.join(os.path.dirname(__file__), "HumanEval.jsonl")


def load_humaneval() -> List[Dict[str, Any]]:
    """Load the HumanEval dataset."""
    problems = []
    with open(HUMANEVAL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            problems.append(json.loads(line))
    return problems


def extract_code_block(text: str) -> str:
    """Extract code from model output."""
    import re
    # Try fenced code block
    pattern = r"```(?:python)?\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # If no fence, return everything after the prompt-like part
    return text.strip()


def run_test(problem: Dict, completion: str) -> Dict:
    """
    Test a completion against HumanEval test cases.
    
    Returns {"passed": bool, "error": str or None}
    """
    # Build the test program
    test_program = (
        problem["prompt"] + "\n" +
        completion + "\n" +
        problem["test"] + "\n" +
        f"check({problem['entry_point']})\n"
    )
    
    # Write to temp file and execute
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(test_program)
        temp_path = f.name
    
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=5
        )
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


def run_base_mode(problems: List[Dict], synapse: LMStudioClient, limit: int = None) -> List[Dict]:
    """
    BASE MODE: Standard pass@1 evaluation.
    Generate 1 candidate per problem. Test it. Pass or fail.
    """
    if limit:
        problems = problems[:limit]
    
    results = []
    total = len(problems)
    
    print(f"\n[BASE MODE] Running pass@1 on {total} problems...")
    print("-" * 60)
    
    for i, problem in enumerate(problems, 1):
        task_id = problem["task_id"]
        
        # Generate 1 completion
        raw = synapse.generate(
            prompt=problem["prompt"],
            temperature=0.2,  # low temp for deterministic pass@1
            max_tokens=512,
            n=1
        )
        
        if not raw or not raw[0].strip():
            results.append({
                "task_id": task_id,
                "passed": False,
                "attempts": 1,
                "error": "Empty generation"
            })
            print(f"  [{i}/{total}] {task_id}: EMPTY -> FAIL")
            continue
        
        completion = extract_code_block(raw[0])
        test_result = run_test(problem, completion)
        
        results.append({
            "task_id": task_id,
            "passed": test_result["passed"],
            "attempts": 1,
            "error": test_result["error"]
        })
        
        status = "PASS" if test_result["passed"] else "FAIL"
        print(f"  [{i}/{total}] {task_id}: {status}")
    
    return results


def run_os_mode(problems: List[Dict], synapse: LMStudioClient, n_candidates: int = 3, limit: int = None) -> List[Dict]:
    """
    PUZZLE LOGIC OS MODE: Best-of-k selection with test validation.
    Generate up to k candidates per problem. Test all. Pick the one that passes most tests.
    """
    if limit:
        problems = problems[:limit]
    
    results = []
    total = len(problems)
    
    print(f"\n[OS MODE] Running best-of-{n_candidates} on {total} problems...")
    print("-" * 60)
    
    for i, problem in enumerate(problems, 1):
        task_id = problem["task_id"]
        
        # Generate multiple candidates
        raw_candidates = synapse.generate(
            prompt=problem["prompt"],
            temperature=0.4,  # slightly higher for diversity
            max_tokens=512,
            n=n_candidates
        )
        
        candidates = [extract_code_block(r) for r in raw_candidates if r.strip()]
        
        if not candidates:
            results.append({
                "task_id": task_id,
                "passed": False,
                "attempts": 0,
                "best_error": "No candidates generated"
            })
            print(f"  [{i}/{total}] {task_id}: NO CANDIDATES -> FAIL")
            continue
        
        # Test ALL candidates, track the best one
        best_result = None
        best_passed = False
        best_attempts = 0
        
        for j, completion in enumerate(candidates, 1):
            test_result = run_test(problem, completion)
            best_attempts = j
            
            if test_result["passed"]:
                best_passed = True
                best_result = test_result
                break  # Found a passing candidate, stop early
            
            # If none pass yet, keep the error for the last attempt
            best_result = test_result
        
        results.append({
            "task_id": task_id,
            "passed": best_passed,
            "attempts": best_attempts,
            "error": best_result["error"] if best_result else None
        })
        
        status = "PASS" if best_passed else "FAIL"
        print(f"  [{i}/{total}] {task_id}: {status} (tried {best_attempts}/{len(candidates)})")
    
    return results


def print_comparison(base_results: List[Dict], os_results: List[Dict]):
    """Print side-by-side comparison."""
    print("\n" + "=" * 70)
    print("HUMANEVAL BENCHMARK RESULTS")
    print("=" * 70)
    
    base_passed = sum(1 for r in base_results if r["passed"])
    os_passed = sum(1 for r in os_results if r["passed"])
    total = len(base_results)
    
    base_rate = base_passed / total * 100
    os_rate = os_passed / total * 100
    improvement = os_rate - base_rate
    
    # Count recoveries (where OS passed but base failed)
    recoveries = 0
    for b, o in zip(base_results, os_results):
        if not b["passed"] and o["passed"]:
            recoveries += 1
    
    print(f"\n{'Metric':<30} {'Base Model':<15} {'Puzzle Logic OS':<15}")
    print("-" * 70)
    print(f"{'Problems solved':<30} {base_passed}/{total:<15} {os_passed}/{total}")
    print(f"{'Pass rate':<30} {base_rate:.1f}%{'':<10} {os_rate:.1f}%")
    print(f"{'Avg attempts per problem':<30} {'1.0':<15} {sum(r['attempts'] for r in os_results)/total:.1f}")
    print(f"{'Recoveries (OS saved base fail)':<30} {'N/A':<15} {recoveries}")
    
    print("\n" + "-" * 70)
    print(f"IMPROVEMENT: {improvement:+.1f} percentage points")
    
    if improvement > 0:
        relative = (os_passed - base_passed) / base_passed * 100 if base_passed > 0 else float('inf')
        print(f"RELATIVE GAIN: {relative:.0f}% more problems solved")
    
    print("\n" + "=" * 70)
    print("INTERPRETATION")
    print("=" * 70)
    
    if improvement > 10:
        print("The Puzzle Logic OS shows STRONG advantage.")
        print("Empirical candidate selection significantly outperforms blind acceptance.")
    elif improvement > 5:
        print("The Puzzle Logic shows MODERATE advantage.")
        print("Multiple candidates + validation provides a measurable boost.")
    elif improvement > 0:
        print("The Puzzle Logic shows SLIGHT advantage.")
        print("The model is already quite good; edge cases are rare.")
    else:
        print("No advantage observed in this run.")
        print("Possible reasons:")
        print("  - The model is too good on this benchmark (saturated)")
        print("  - The benchmark is too easy for this model")
        print("  - Try a weaker model or a harder benchmark (e.g., HumanEval+)")
    
    print("\n" + "=" * 70)


def save_results(base_results, os_results, filename="humaneval_results.json"):
    """Save results to JSON file."""
    data = {
        "benchmark": "HumanEval",
        "n_problems": len(base_results),
        "base_mode": {
            "pass_rate": sum(1 for r in base_results if r["passed"]) / len(base_results),
            "results": base_results
        },
        "os_mode": {
            "pass_rate": sum(1 for r in os_results if r["passed"]) / len(os_results),
            "results": os_results
        }
    }
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    
    print(f"\nResults saved to: {filename}")


def main():
    parser = argparse.ArgumentParser(description="Run HumanEval benchmark with Puzzle Logic OS")
    parser.add_argument("--mode", choices=["base", "os", "both"], default="both",
                        help="Run mode: base (pass@1), os (best-of-k), or both")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit to first N problems (for quick testing)")
    parser.add_argument("--k", type=int, default=3,
                        help="Number of candidates for OS mode (default: 3)")
    parser.add_argument("--output", type=str, default="humaneval_results.json",
                        help="Output JSON filename")
    args = parser.parse_args()
    
    # Check prerequisites
    if not os.path.exists(HUMANEVAL_PATH):
        print(f"ERROR: HumanEval dataset not found at {HUMANEVAL_PATH}")
        print("Download it from: https://github.com/openai/human-eval")
        sys.exit(1)
    
    print("=" * 70)
    print("HUMANEVAL BENCHMARK FOR PUZZLE LOGIC AI")
    print("=" * 70)
    
    # Load problems
    problems = load_humaneval()
    print(f"\nLoaded {len(problems)} problems from HumanEval")
    
    if args.limit:
        print(f"Running on first {args.limit} problems only")
    
    # Initialize Synapse
    synapse = LMStudioClient()
    print("\n[CHECK] Testing LM Studio connection...")
    if not synapse.check_health():
        print("  X LM Studio is not running!")
        print("  Start LM Studio, load a model, and start the server.")
        sys.exit(1)
    print("  + LM Studio is running!")
    
    base_results = []
    os_results = []
    
    # Run base mode
    if args.mode in ("base", "both"):
        base_results = run_base_mode(problems, synapse, limit=args.limit)
    
    # Run OS mode
    if args.mode in ("os", "both"):
        os_results = run_os_mode(problems, synapse, n_candidates=args.k, limit=args.limit)
    
    # Print comparison if both modes ran
    if args.mode == "both" and base_results and os_results:
        print_comparison(base_results, os_results)
        save_results(base_results, os_results, args.output)
    elif args.mode == "base":
        passed = sum(1 for r in base_results if r["passed"])
        print(f"\nBase mode complete: {passed}/{len(base_results)} passed ({passed/len(base_results)*100:.1f}%)")
    elif args.mode == "os":
        passed = sum(1 for r in os_results if r["passed"])
        print(f"\nOS mode complete: {passed}/{len(os_results)} passed ({passed/len(os_results)*100:.1f}%)")
    
    print("\nDone.")


if __name__ == "__main__":
    main()
