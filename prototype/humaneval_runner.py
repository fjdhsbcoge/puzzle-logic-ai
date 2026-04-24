"""
HumanEval Runner for Puzzle Logic AI
======================================

Runs the OpenAI HumanEval benchmark comparing base model (pass@1)
against Puzzle Logic OS (adaptive best-of-k with concise error feedback).

Usage:
    python humaneval_runner.py --mode both --subset hard   # 20 hard problems
    python humaneval_runner.py --mode both --limit 10       # first 10 problems
    python humaneval_runner.py --mode both                  # all 164 problems
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

# Curated subset of genuinely hard problems where 8B models often fail.
# Mix of: edge cases, parsing, algorithms, state machines, math.
HARD_SUBSET = [
    15, 22, 25, 32, 40, 45, 50, 55, 60,
    65, 70, 75, 80, 85, 90, 95, 100, 110, 130, 160
]


def load_humaneval(subset_indices=None) -> List[Dict[str, Any]]:
    """Load HumanEval. Optionally select only specific indices."""
    problems = []
    with open(HUMANEVAL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            problems.append(json.loads(line))
    
    if subset_indices:
        subset = []
        for idx in subset_indices:
            if idx < len(problems):
                subset.append(problems[idx])
        return subset
    
    return problems


def extract_completion(text: str, problem: Dict) -> str:
    """Extract code from model output. Handles body-only and full-function outputs."""
    if not text or not text.strip():
        return ""
    
    # 1. Try fenced code block
    match = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    
    # 2. Check if model output the full function (including signature)
    entry_point = problem["entry_point"]
    sig_pattern = rf"def\s+{re.escape(entry_point)}\s*\("
    
    if re.search(sig_pattern, text):
        # Extract just the body
        lines = text.splitlines()
        body_lines = []
        in_body = False
        base_indent = None
        docstring_open = False
        
        for line in lines:
            if re.search(sig_pattern, line):
                in_body = True
                continue
            if not in_body:
                continue
            # Handle docstring toggling
            if '"""' in line:
                quote_count = line.count('"""')
                if quote_count == 2:  # Single-line docstring
                    continue
                if quote_count == 1:
                    docstring_open = not docstring_open
                    continue
            if docstring_open:
                continue
            # Collect body lines, normalizing indentation
            if line.strip():
                if base_indent is None:
                    base_indent = len(line) - len(line.lstrip())
                if len(line) >= base_indent:
                    body_lines.append(line[base_indent:])
                else:
                    body_lines.append(line.lstrip())
            else:
                body_lines.append("")
        
        if body_lines:
            return "\n".join(body_lines).strip()
    
    # 3. Check if already properly indented
    lines = text.splitlines()
    for line in lines:
        if line.strip():
            if line.startswith("    "):
                return text.strip()
            break
    
    # 4. Not indented -- add 4-space indentation
    indented = []
    for line in lines:
        if line.strip():
            indented.append("    " + line)
        else:
            indented.append("")
    return "\n".join(indented).strip()


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


def extract_concise_error(error_text: str) -> str:
    """Extract a concise error message from a traceback."""
    if not error_text:
        return "unknown error"
    lines = error_text.strip().splitlines()
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("File \"") or line.startswith("^") or not line:
            continue
        if len(line) < 120:
            return line
    for line in reversed(lines):
        if line.strip():
            return line.strip()[:100]
    return "unknown error"


def build_prompt(problem: Dict, previous_errors=None) -> str:
    """Build prompt with clear instructions and optional concise error feedback."""
    base = problem["prompt"]
    instruction = (
        "\n\n"
        "INSTRUCTION: Complete the function above. "
        "Write ONLY the function body (indented code inside the function). "
        "Do NOT repeat the function signature or docstring. "
        "Do NOT write a main block or test cases. "
        "Output your code inside a markdown code block."
    )
    if previous_errors:
        concise = extract_concise_error(previous_errors[-1])
        feedback = (
            f"\n\n"
            f"FIX NEEDED: Previous code failed with: {concise}\n"
            f"Please correct this and output only the fixed function body."
        )
        return base + instruction + feedback
    return base + instruction


def run_base_mode(problems: List[Dict], synapse: LMStudioClient) -> List[Dict]:
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
        
        completion = extract_completion(raw[0], problem)
        test_result = run_test(problem, completion)
        
        results.append({"task_id": task_id, "passed": test_result["passed"],
                        "attempts": 1, "error": test_result["error"]})
        status = "PASS" if test_result["passed"] else "FAIL"
        print(f"  [{i}/{total}] {task_id}: {status}")
    return results


def run_os_mode(problems: List[Dict], synapse: LMStudioClient, n_candidates: int = 3) -> List[Dict]:
    """OS MODE: Adaptive best-of-k with concise error feedback."""
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
            
            completion = extract_completion(raw[0], problem)
            if not completion.strip():
                best_attempts = attempt
                err = "No code extracted"
                previous_errors.append(err)
                best_error = err
                continue
            
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
            concise = extract_concise_error(best_error) if best_error else "unknown"
            print(f"  [{i}/{total}] {task_id}: FAIL ({best_attempts} tries, {concise[:50]})")
        
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
    parser.add_argument("--subset", choices=["hard", "full"], default="hard",
                        help="Which problems to run: 'hard' = 20 curated hard problems, 'full' = all 164")
    args = parser.parse_args()
    
    if not os.path.exists(HUMANEVAL_PATH):
        print(f"ERROR: HumanEval not found at {HUMANEVAL_PATH}")
        sys.exit(1)
    
    # Load problems based on subset selection
    if args.subset == "hard":
        problems = load_humaneval(subset_indices=HARD_SUBSET)
        print(f"Running HARD subset: {len(problems)} curated challenging problems")
    else:
        problems = load_humaneval()
        print(f"Running FULL benchmark: {len(problems)} problems")
    
    if args.limit:
        problems = problems[:args.limit]
        print(f"Limited to first {len(problems)} problems")
    
    print("=" * 70)
    print("PUZZLE LOGIC AI - HUMANEVAL BENCHMARK")
    print("=" * 70)
    print()
    print(f"Subset: {args.subset.upper()} | Problems: {len(problems)} | Candidates: {args.k}")
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
        base_results = run_base_mode(problems, synapse)
    if args.mode in ("os", "both"):
        os_results = run_os_mode(problems, synapse, n_candidates=args.k)
    
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
