"""
HumanEval Runner for Puzzle Logic AI
======================================

Runs the OpenAI HumanEval benchmark (164 Python programming problems)
comparing base model (pass@1) against Puzzle Logic OS (best-of-k selection
WITH error feedback -- the model sees its mistakes and tries again).

Usage:
    python humaneval_runner.py --mode base      # 1 candidate per problem
    python humaneval_runner.py --mode os       # up to 3 candidates with feedback
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
import re
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
    """Extract code from model output. Handles multiple formats."""
    if not text or not text.strip():
        return ""
    
    # 1. Try fenced code block
    pattern = r"```(?:python)?\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # 2. Try indented code blocks (4 spaces)
    lines = text.splitlines()
    code_lines = []
    in_code = False
    for line in lines:
        if line.startswith("    ") or line.startswith("\t"):
            code_lines.append(line.lstrip())
            in_code = True
        elif in_code and line.strip() == "":
            code_lines.append("")
        elif in_code:
            break
    if code_lines:
        return "\n".join(code_lines).strip()
    
    # 3. Look for function definition and extract from there
    func_match = re.search(r"(def\s+\w+\s*\(.*\).*?:\n)", text)
    if func_match:
        start_idx = func_match.start()
        return text[start_idx:].strip()
    
    # 4. Fallback: return everything (model may have just output raw code)
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
        if error and len(error) > 300:
            error = error[:300] + "..."
        return {"passed": passed, "error": error}
    except subprocess.TimeoutExpired:
        return {"passed": False, "error": "Timeout"}
    except Exception as e:
        return {"passed": False, "error": str(e)}
    finally:
        os.unlink(temp_path)


def build_prompt(problem: Dict, previous_errors: List[str] = None) -> str:
    """
    Build the prompt for the model.
    If previous errors exist, include them so the model can learn from mistakes.
    """
    base_prompt = problem["prompt"]
    
    if previous_errors:
        # Add feedback about what went wrong
        feedback = "\n\nIMPORTANT: Your previous attempt(s) failed.\n"
        for i, err in enumerate(previous_errors, 1):
            feedback += f"\nAttempt {i} failed with:\n{err}\n"
        feedback += "\nPlease fix the code to handle these issues. "
        feedback += "Output only the corrected function inside a markdown code block."
        
        return base_prompt + feedback
    
    return base_prompt


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
            max_tokens=1024,
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
    PUZZLE LOGIC OS MODE: Adaptive best-of-k with ERROR FEEDBACK.
    
    Key difference from base mode: when a candidate fails, the model
    SEES the error and generates a corrected version. The OS maintains
    a "previous_errors" list that accumulates across attempts.
    
    This is genuine in-context adaptation: same model, same weights,
    but the INPUT changes based on empirical feedback.
    """
    if limit:
        problems = problems[:limit]
    
    results = []
    total = len(problems)
    
    print(f"\n[OS MODE] Running adaptive best-of-{n_candidates} on {total} problems...")
    print("         With ERROR FEEDBACK between attempts.")
    print("-" * 60)
    
    for i, problem in enumerate(problems, 1):
        task_id = problem["task_id"]
        
        best_passed = False
        best_attempts = 0
        best_error = None
        previous_errors = []  # Accumulated error feedback
        
        for attempt in range(1, n_candidates + 1):
            # Build prompt with accumulated error feedback
            prompt = build_prompt(problem, previous_errors if previous_errors else None)
            
            # Generate ONE candidate at a time (sequential, not parallel)
            # This allows error feedback from attempt N to influence attempt N+1
            raw = synapse.generate(
                prompt=prompt,
                temperature=0.3,  # moderate temp for some exploration
                max_tokens=1024,
                n=1
            )
            
            if not raw or not raw[0].strip():
                best_attempts = attempt
                best_error = f"Attempt {attempt}: Empty generation"
                previous_errors.append(best_error)
                print(f"  [{i}/{total}] {task_id}: Attempt {attempt} EMPTY")
                continue
            
            completion = extract_code_block(raw[0])
            
            if not completion.strip():
                best_attempts = attempt
                best_error = f"Attempt {attempt}: Extracted code is empty"
                previous_errors.append(best_error)
                print(f"  [{i}/{total}] {task_id}: Attempt {attempt} NO CODE")
                continue
            
            # Test the candidate
            test_result = run_test(problem, completion)
            best_attempts = attempt
            
            if test_result["passed"]:
                best_passed = True
                best_error = None
                print(f"  [{i}/{total}] {task_id}: PASS (attempt {attempt}/{n_candidates})")
                break  # Success! Stop trying.
            else:
                # Failure -- capture error for feedback
                err_msg = f"Attempt {attempt} failed: {test_result['error']}"
                previous_errors.append(err_msg)
                best_error = test_result["error"]
                print(f"  [{i}/{total}] {task_id}: Attempt {attempt} FAIL -> {test_result['error'][:60]}")
        
        # Record result
        results.append({
            "task_id": task_id,
            "passed": best_passed,
            "attempts": best_attempts,
            "error": best_error,
            "feedback_used": len(previous_errors) > 0
        })
    
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
    feedback_recoveries = 0
    for b, o in zip(base_results, os_results):
        if not b["passed"] and o["passed"]:
            recoveries += 1
            if o.get("feedback_used"):
                feedback_recoveries += 1
    
    # Count problems where feedback was actually used
    feedback_used_count = sum(1 for r in os_results if r.get("feedback_used"))
    
    print(f"\n{'Metric':<30} {'Base Model':<15} {'Puzzle Logic OS':<15}")
    print("-" * 70)
    print(f"{'Problems solved':<30} {base_passed}/{total:<15} {os_passed}/{total}")
    print(f"{'Pass rate':<30} {base_rate:.1f}%{'':<10} {os_rate:.1f}%")
    print(f"{'Avg attempts per problem':<30} {'1.0':<15} {sum(r['attempts'] for r in os_results)/total:.1f}")
    print(f"{'Recoveries (OS saved base fail)':<30} {'N/A':<15} {recoveries}")
    print(f"{'Problems using error feedback':<30} {'N/A':<15} {feedback_used_count}")
    
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
        print("Error feedback + empirical selection significantly outperforms blind acceptance.")
    elif improvement > 5:
        print("The Puzzle Logic shows MODERATE advantage.")
        print("Adaptive candidate generation with error feedback provides a measurable boost.")
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
    print("ADAPTATION MECHANISM (OS vs Base)")
    print("=" * 70)
    print("Base Model:")
    print("  - Generates 1 candidate per problem")
    print("  - Never sees error messages")
    print("  - Same prompt every time")
    print("  - Static behavior")
    print()
    print("Puzzle Logic OS:")
    print("  - Generates up to k candidates SEQUENTIALLY")
    print("  - Candidate N receives error feedback from attempts 1..N-1")
    print("  - The prompt CHANGES based on empirical results")
    print("  - The model adapts IN-CONTEXT (same weights, different input)")
    print()
    print("This is real adaptation: the model learns from its mistakes")
    print("within a single problem, without any weight updates.")
    print("=" * 70)


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
                        help="Run mode: base (pass@1), os (adaptive best-of-k), or both")
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
    print()
    print("Comparing: BASE MODEL (static, 1-shot) vs PUZZLE LOGIC OS (adaptive, feedback)")
    print()
    print("ADAPTATION MECHANISM:")
    print("  Base:  Model generates 1 candidate. If it fails, problem is failed.")
    print("  OS:    Model generates candidate 1. If it fails, the ERROR MESSAGE")
    print("         is added to the prompt. Model generates candidate 2 with")
    print("         awareness of the previous mistake. This repeats up to k times.")
    print()
    print("Key insight: Same model weights. Different input. Real in-context learning.")
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
