"""
HumanEval Runner for Puzzle Logic AI
======================================

Runs the OpenAI HumanEval benchmark (164 Python programming problems)
comparing base model (pass@1) against Puzzle Logic OS (adaptive best-of-k
with CONCISE error feedback).

Usage:
    python humaneval_runner.py --mode base      # 1 candidate per problem
    python humaneval_runner.py --mode os       # up to 3 candidates with feedback
    python humaneval_runner.py --mode both     # run both, print comparison
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


def load_humaneval() -> List[Dict[str, Any]]:
    problems = []
    with open(HUMANEVAL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            problems.append(json.loads(line))
    return problems


def extract_completion(text: str, problem: Dict) -> str:
    """
    Extract code from model output.
    
    HumanEval prompts already include the function signature. The model should
    output only the function BODY. But sometimes it outputs the full function.
    This handles both cases and fixes indentation.
    """
    if not text or not text.strip():
        return ""
    
    # 1. Try fenced code block
    pattern = r"```(?:python)?\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    
    # 2. Check if the model output the full function (including signature)
    entry_point = problem["entry_point"]
    signature_pattern = rf"def\s+{re.escape(entry_point)}\s*\("
    
    if re.search(signature_pattern, text):
        # Model output the full function. Extract just the body.
        lines = text.splitlines()
        body_lines = []
        in_body = False
        base_indent = None
        
        for line in lines:
            # Skip the def line
            if re.search(signature_pattern, line):
                in_body = True
                continue
            # Skip docstring lines
            if in_body and '"""' in line:
                # Check if docstring ends on same line
                if line.strip().count('"""') == 2:
                    continue
                # Toggle docstring mode
                continue
            if in_body:
                # Skip empty lines at start of body
                if not body_lines and not line.strip():
                    continue
                # Calculate relative indentation
                if line.strip():
                    if base_indent is None:
                        base_indent = len(line) - len(line.lstrip())
                    # Remove the base indentation to make it absolute
                    if len(line) >= base_indent:
                        body_lines.append(line[base_indent:])
                    else:
                        body_lines.append(line.lstrip())
                else:
                    body_lines.append("")
        
        if body_lines:
            return "\n".join(body_lines).strip()
    
    # 3. Check if text is properly indented (function body format)
    lines = text.splitlines()
    if lines:
        first_content_line = None
        for line in lines:
            if line.strip():
                first_content_line = line
                break
        
        if first_content_line and first_content_line.startswith("    "):
            # Already indented - good, return as-is
            return text.strip()
        
        # 4. Not indented - add 4-space indentation to every non-empty line
        # (the prompt expects function body, which is indented)
        indented_lines = []
        for line in lines:
            if line.strip():
                indented_lines.append("    " + line)
            else:
                indented_lines.append("")
        
        if indented_lines:
            return "\n".join(indented_lines).strip()
    
    return text.strip()


def run_test(problem: Dict, completion: str) -> Dict:
    """Test a completion against HumanEval test cases."""
    # completion should be the function body (indented)
    # We concatenate: prompt (has signature) + body + test
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
    
    CRITICAL: The HumanEval prompt already contains the function signature.
    The model must output ONLY the function body (indented code).
    
    Error feedback is SHORT — one concise line. Verbose feedback confuses
    the model and causes malformed output.
    """
    base = problem["prompt"]
    
    # Instruction about what to output
    instruction = (
        "\n\n"
        "INSTRUCTION: Complete the function above. "
        "Write ONLY the function body (indented code inside the function). "
        "Do NOT repeat the function signature or docstring. "
        "Do NOT write a main block or test cases. "
        "Output your code inside a markdown code block."
    )
    
    if previous_errors:
        # Keep feedback SHORT — just the essential error, not a full traceback
        last_error = previous_errors[-1]
        # Extract just the error type and message, not the file path
        concise_error = extract_concise_error(last_error)
        
        feedback = (
            f"\n\n"
            f"FIX NEEDED: Your previous code failed with: {concise_error}\n"
            f"Please correct this and output only the fixed function body."
        )
        return base + instruction + feedback
    
    return base + instruction


def extract_concise_error(error_text: str) -> str:
    """
    Extract a concise error description from a traceback.
    
    'File "/tmp/xyz.py", line 23\n    return groups\n    ^^^^^^^^^^^^^\nSyntaxError: return outside function'
    
    Becomes: 'SyntaxError: return outside function'
    """
    if not error_text:
        return "unknown error"
    
    lines = error_text.strip().splitlines()
    
    # Look for the actual error line (usually the last line)
    for line in reversed(lines):
        line = line.strip()
        # Skip file path lines
        if line.startswith("File \"") or line.startswith("^") or not line:
            continue
        # This is likely the error message
        if len(line) < 120:  # Keep it concise
            return line
    
    # Fallback: return last non-empty line
    for line in reversed(lines):
        if line.strip():
            return line.strip()[:100]
    
    return "unknown error"


def run_base_mode(problems: List[Dict], synapse: LMStudioClient, limit: int = None) -> List[Dict]:
    """BASE MODE: pass@1 — 1 candidate, no feedback, no retry."""
    if limit:
        problems = problems[:limit]
    
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


def run_os_mode(problems: List[Dict], synapse: LMStudioClient, n_candidates: int = 3, limit: int = None) -> List[Dict]:
    """
    OS MODE: Adaptive best-of-k with CONCISE error feedback.
    
    Attempt 1: Base prompt
    Attempt 2+: Short error feedback added to prompt
    """
    if limit:
        problems = problems[:limit]
    
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
            print(f"  [{i}/{total}] {task_id}: FAIL ({best_attempts} tries, last: {concise[:50]})")
        
        results.append({
            "task_id": task_id,
            "passed": best_passed,
            "attempts": best_attempts,
            "error": best_error,
            "feedback_used": len(previous_errors) > 0
        })
    
    return results


def print_comparison(base_results: List[Dict], os_results: List[Dict]):
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
        relative = (os_passed - base_passed) / base_passed * 100
        print(f"RELATIVE GAIN: {relative:.0f}% more problems solved")
    elif improvement < 0:
        print(f"REGRESSION: OS scored {abs(improvement):.1f} points LOWER")
        print("This means error feedback is HARMING performance.")
        print("The feedback format needs further refinement.")
    
    print("\n" + "=" * 70)


def save_results(base_results, os_results, filename="humaneval_results.json"):
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["base", "os", "both"], default="both")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--output", type=str, default="humaneval_results.json")
    args = parser.parse_args()
    
    if not os.path.exists(HUMANEVAL_PATH):
        print(f"ERROR: HumanEval not found at {HUMANEVAL_PATH}")
        sys.exit(1)
    
    print("=" * 70)
    print("PUZZLE LOGIC AI — HUMANEVAL BENCHMARK")
    print("=" * 70)
    print()
    print("FIX APPLIED: Concise error feedback + smart code extraction")
    print("-" * 70)
    
    problems = load_humaneval()
    print(f"Loaded {len(problems)} problems")
    if args.limit:
        print(f"Running first {args.limit} problems")
    
    synapse = LMStudioClient()
    print("\n[CHECK] LM Studio...")
    if not synapse.check_health():
        print("  NOT RUNNING. Start LM Studio and load a model.")
        sys.exit(1)
    print("  OK")
    
    base_results = []
    os_results = []
    
    if args.mode in ("base", "both"):
        base_results = run_base_mode(problems, synapse, limit=args.limit)
    if args.mode in ("os", "both"):
        os_results = run_os_mode(problems, synapse, n_candidates=args.k, limit=args.limit)
    
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
