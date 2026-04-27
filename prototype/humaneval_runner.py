"""
HumanEval Runner for Puzzle Logic AI
======================================

Runs HumanEval benchmark comparing base model (pass@1)
against Puzzle Logic OS (adaptive best-of-k with feedback).

Usage:
    python humaneval_runner.py --mode both --subset medium    # 15 medium problems
    python humaneval_runner.py --mode both --subset hard      # 20 hard problems
    python humaneval_runner.py --mode both --subset full      # all 164
    python humaneval_runner.py --mode both --limit 5          # first 5 of subset
"""

import json
import os
import sys
import tempfile
import argparse
import re
from typing import List, Dict, Any

from lmstudio_client import LMStudioClient


HUMANEVAL_PATH = os.path.join(os.path.dirname(__file__), "HumanEval.jsonl")

# MEDIUM: 15 problems an 8B model should solve ~40-70% in base mode.
# Focus: string manipulation, simple loops, one clear edge case.
MEDIUM_SUBSET = [3, 5, 8, 10, 12, 16, 26, 28, 29, 30, 31, 36, 42, 43, 48]

# HARD: 20 problems requiring algorithms or complex logic.
HARD_SUBSET = [
    15, 22, 25, 32, 40, 45, 50, 55, 60,
    65, 70, 75, 80, 85, 90, 95, 100, 110, 130, 160
]


def load_humaneval(subset_indices=None) -> List[Dict[str, Any]]:
    problems = []
    with open(HUMANEVAL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            problems.append(json.loads(line))
    if subset_indices:
        return [problems[i] for i in subset_indices if i < len(problems)]
    return problems


def extract_code(text: str) -> str:
    """
    Extract code from model output.
    
    HumanEval evaluation: prompt (with function signature) + completion + test.
    The completion can be:
      - Just the function body (indented code) -> works
      - Full function with 'def' -> works (overrides prompt's definition)
      - Multiple fenced blocks -> we take the first one with code
    
    We just need valid Python code, nothing fancy.
    """
    if not text:
        return ""
    
    # 1. Extract all fenced code blocks
    blocks = re.findall(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    
    # 2. Pick the first block that contains actual Python code
    for block in blocks:
        block = block.strip()
        if block and ('def ' in block or 'return' in block or 'for ' in block or 'if ' in block):
            return block
    
    # 3. No code blocks found. Check if raw text contains Python
    text = text.strip()
    if text and ('def ' in text or 'return' in text or 'for ' in text or 'if ' in text or '=' in text):
        return text
    
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
        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True, text=True, timeout=5
        )
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


def build_prompt(problem: Dict, previous_errors=None) -> str:
    """Build prompt with clear instructions and minimal feedback."""
    base = problem["prompt"]
    
    # Core instruction - always present
    instruction = (
        "\n\n"
        "Complete the function above. Output the code inside a markdown code block.\n"
        "You may output either the full function or just the function body."
    )
    
    if previous_errors:
        # VERY minimal feedback. Just tell it to try again.
        # Detailed error traces confuse reasoning models.
        feedback = (
            "\n\n"
            "NOTE: Your previous attempt did not pass the tests. "
            "Please try again and make sure the code handles all cases."
        )
        return base + instruction + feedback
    
    return base + instruction


def run_base_mode(problems: List[Dict], synapse: LMStudioClient, debug: bool = False) -> List[Dict]:
    """BASE MODE: pass@1."""
    results = []
    total = len(problems)
    print(f"\n[BASE MODE] pass@1 on {total} problems...")
    print("-" * 60)
    
    for i, problem in enumerate(problems, 1):
        task_id = problem["task_id"]
        prompt = build_prompt(problem)
        raw = synapse.generate(prompt=prompt, temperature=0.2, max_tokens=1024, n=1)
        
        if not raw or not raw[0].strip():
            results.append({"task_id": task_id, "passed": False, "attempts": 1,
                            "error": "Empty generation"})
            print(f"  [{i}/{total}] {task_id}: EMPTY")
            continue
        
        if debug:
            print(f"\n  [DEBUG] Raw output:\n{raw[0][:500]}...")
        
        completion = extract_code(raw[0])
        
        if debug and not completion:
            print(f"  [DEBUG] Extraction returned empty!")
        
        test_result = run_test(problem, completion)
        
        results.append({"task_id": task_id, "passed": test_result["passed"],
                        "attempts": 1, "error": test_result["error"]})
        status = "PASS" if test_result["passed"] else "FAIL"
        print(f"  [{i}/{total}] {task_id}: {status}")
    
    return results


def run_os_mode(problems: List[Dict], synapse: LMStudioClient, n_candidates: int = 3, debug: bool = False) -> List[Dict]:
    """OS MODE: Adaptive best-of-k with minimal feedback."""
    results = []
    total = len(problems)
    print(f"\n[OS MODE] Adaptive best-of-{n_candidates} on {total} problems...")
    print("-" * 60)
    
    for i, problem in enumerate(problems, 1):
        task_id = problem["task_id"]
        best_passed = False
        best_attempts = 0
        best_error = None
        previous_errors = []
        
        for attempt in range(1, n_candidates + 1):
            prompt = build_prompt(problem, previous_errors if previous_errors else None)
            raw = synapse.generate(prompt=prompt, temperature=0.3, max_tokens=1024, n=1)
            
            if not raw or not raw[0].strip():
                best_attempts = attempt
                err = "Empty generation"
                previous_errors.append(err)
                best_error = err
                continue
            
            if debug:
                print(f"\n  [DEBUG] Attempt {attempt} raw:\n{raw[0][:500]}...")
            
            completion = extract_code(raw[0])
            
            if not completion.strip():
                best_attempts = attempt
                err = "No code extracted"
                previous_errors.append(err)
                best_error = err
                continue
            
            if debug:
                print(f"  [DEBUG] Extracted ({len(completion)} chars):\n{completion[:300]}...")
            
            test_result = run_test(problem, completion)
            best_attempts = attempt
            
            if test_result["passed"]:
                best_passed = True
                best_error = None
                print(f"  [{i}/{total}] {task_id}: PASS (a{attempt})")
                break
            else:
                err = test_result["error"]
                previous_errors.append(err)
                best_error = err
        
        if not best_passed:
            print(f"  [{i}/{total}] {task_id}: FAIL ({best_attempts} tries)")
        
        results.append({
            "task_id": task_id, "passed": best_passed, "attempts": best_attempts,
            "error": best_error, "feedback_used": len(previous_errors) > 0
        })
    
    return results


def print_comparison(base_results, os_results):
    print("\n" + "=" * 70)
    print("HUMANEVAL BENCHMARK RESULTS")
    print("=" * 70)
    
    base_passed = sum(1 for r in base_results if r["passed"])
    os_passed = sum(1 for r in os_results if r["passed"])
    total = len(base_results)
    base_rate = base_passed / total * 100
    os_rate = os_passed / total * 100
    improvement = os_rate - base_rate
    
    recoveries = sum(1 for b, o in zip(base_results, os_results) if not b["passed"] and o["passed"])
    regressions = sum(1 for b, o in zip(base_results, os_results) if b["passed"] and not o["passed"])
    feedback_used = sum(1 for r in os_results if r.get("feedback_used"))
    
    print(f"\n{'Metric':<35} {'Base':<12} {'OS':<12}")
    print("-" * 70)
    print(f"{'Problems solved':<35} {base_passed}/{total:<12} {os_passed}/{total}")
    print(f"{'Pass rate':<35} {base_rate:.1f}%{'':<8} {os_rate:.1f}%")
    print(f"{'Recoveries (OS saved base fail)':<35} {'-':<12} {recoveries}")
    print(f"{'Regressions (OS broke base pass)':<35} {'-':<12} {regressions}")
    print(f"{'Problems using feedback':<35} {'-':<12} {feedback_used}")
    print("\n" + "-" * 70)
    print(f"IMPROVEMENT: {improvement:+.1f} percentage points")
    if improvement > 0 and base_passed > 0:
        print(f"RELATIVE GAIN: {(os_passed - base_passed) / base_passed * 100:.0f}% more problems solved")
    elif improvement < 0:
        print(f"REGRESSION: OS scored {abs(improvement):.1f} points LOWER")
    print("=" * 70)


def save_results(base_results, os_results, filename="humaneval_results.json"):
    data = {
        "benchmark": "HumanEval",
        "n_problems": len(base_results),
        "base_mode": {"pass_rate": sum(1 for r in base_results if r["passed"]) / len(base_results),
                      "results": base_results},
        "os_mode": {"pass_rate": sum(1 for r in os_results if r["passed"]) / len(os_results),
                    "results": os_results}
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"\nResults saved to: {filename}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["base", "os", "both"], default="both")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit to first N problems from the selected set")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--output", type=str, default="humaneval_results.json")
    parser.add_argument("--subset", choices=["medium", "hard", "full"], default="medium",
                        help="Which problems: 'medium' = 15 easier (default), 'hard' = 20 challenging, 'full' = all 164")
    parser.add_argument("--debug", action="store_true",
                        help="Print raw model output for diagnosis")
    args = parser.parse_args()
    
    if not os.path.exists(HUMANEVAL_PATH):
        print(f"ERROR: HumanEval not found at {HUMANEVAL_PATH}")
        sys.exit(1)
    
    if args.subset == "medium":
        problems = load_humaneval(subset_indices=MEDIUM_SUBSET)
        print(f"Running MEDIUM subset: {len(problems)} problems (8B model should solve ~40-70%)")
    elif args.subset == "hard":
        problems = load_humaneval(subset_indices=HARD_SUBSET)
        print(f"Running HARD subset: {len(problems)} problems")
    else:
        problems = load_humaneval()
        print(f"Running FULL benchmark: {len(problems)} problems")
    
    if args.limit:
        problems = problems[:args.limit]
        print(f"Limited to first {len(problems)} problems")
    
    print("=" * 70)
    print("PUZZLE LOGIC AI - HUMANEVAL BENCHMARK")
    print("=" * 70)
    print(f"Subset: {args.subset.upper()} | Problems: {len(problems)} | Candidates: {args.k}")
    if args.debug:
        print("DEBUG MODE: Raw outputs will be printed")
    print("-" * 70)
    
    synapse = LMStudioClient()
    print("\n[CHECK] LM Studio...")
    if not synapse.check_health():
        print("  NOT RUNNING. Start LM Studio and load a model.")
        sys.exit(1)
    print("  OK")
    
    base_results = []
    os_results = []
    
    if args.mode in ("base", "both"):
        base_results = run_base_mode(problems, synapse, debug=args.debug)
    if args.mode in ("os", "both"):
        os_results = run_os_mode(problems, synapse, n_candidates=args.k, debug=args.debug)
    
    if args.mode == "both" and base_results and os_results:
        print_comparison(base_results, os_results)
        save_results(base_results, os_results, args.output)
    elif args.mode == "base":
        p = sum(1 for r in base_results if r["passed"])
        print(f"\nBase: {p}/{len(base_results)} ({p/len(base_results)*100:.1f}%)")
    elif args.mode == "os":
        p = sum(1 for r in os_results if r["passed"])
        print(f"\nOS: {p}/{len(os_results)} ({p/len(os_results)*100:.1f}%)")
    
    print("\nDone.")


if __name__ == "__main__":
    main()
