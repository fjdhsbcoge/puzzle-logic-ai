"""
HumanEval Baseline vs Error-Pattern Knowledge Graph
====================================================

Runs the SAME HumanEval problems twice in one session:
  1. BASELINE: 1 attempt per problem, no hints, no learning
  2. ERROR-PATTERN: Up to 3 attempts, toolbox on retry, learning enabled

Then prints a side-by-side comparison.

Usage (overnight run):
    python humaneval_compare_runner.py --model qwen2.5-coder-3b-instruct --full

Usage (quick test):
    python humaneval_compare_runner.py --model qwen2.5-coder-3b-instruct --limit 10
"""

import json
import os
import sys
import tempfile
import subprocess
import argparse
import re
import time
from typing import List, Dict, Any, Optional

from lmstudio_client import LMStudioClient
from error_pattern_kg import ErrorPatternGraph, extract_error_fingerprint
from prompt_logger import PromptLogger


HUMANEVAL_PATH = os.path.join(os.path.dirname(__file__), "HumanEval.jsonl")


def load_humaneval() -> List[Dict]:
    problems = []
    with open(HUMANEVAL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            problems.append(json.loads(line))
    return problems


def extract_code(text: str) -> str:
    """Extract code from model output, handling Qwen's python tag."""
    if not text:
        return ""
    
    # Find all fenced blocks
    blocks = re.findall(r"```(?:\n|\r\n)?(?:python(?:\n|\r\n))?(.*?)```", text, re.DOTALL)
    
    for block in blocks:
        block = block.strip()
        if block and ('def ' in block or 'return' in block or 'for ' in block or 'if ' in block):
            # Strip leading "python\n" if present
            if block.startswith("python\n"):
                block = block[7:].strip()
            elif block.startswith("python"):
                block = block[6:].strip()
            return block
    
    # No code blocks. Check raw text.
    text = text.strip()
    if text and ('def ' in text or 'return' in text or 'for ' in text or 'if ' in text):
        return text
    
    return ""


def infer_function_name(test_code: str, entry_point: str = "") -> str:
    """Extract function name from test code.
    
    For HumanEval: use entry_point (e.g., 'has_close_elements').
    For MBPP: extract from assert statement.
    """
    # HumanEval provides the entry point directly
    if entry_point:
        return entry_point
    
    # MBPP-style: assert function_name(...)
    match = re.search(r"assert\s+(\w+)\s*\(", test_code)
    if match:
        return match.group(1)
    return ""


def fix_function_name(code: str, expected_name: str) -> str:
    """Rename function in code to match expected name."""
    if not expected_name or not code:
        return code
    match = re.search(r"def\s+(\w+)\s*\(", code)
    if not match:
        return code
    actual = match.group(1)
    if actual == expected_name:
        return code
    return re.sub(r"\b" + re.escape(actual) + r"\b", expected_name, code)


def run_test(problem: Dict, completion: str) -> Dict:
    """Test a completion against HumanEval test cases."""
    # For HumanEval, use the entry_point field for function name
    expected = infer_function_name(problem.get("test", ""), problem.get("entry_point", ""))
    if expected:
        # Only rename if names are clearly different
        match = re.search(r"def\s+(\w+)\s*\(", completion)
        if match and match.group(1) != expected:
            completion = fix_function_name(completion, expected)
    
    # HumanEval test code already includes check() calls.
    # We just concatenate: prompt + completion + test.
    test_program = (
        problem["prompt"] + "\n" +
        completion + "\n" +
        problem["test"] + "\n"
    )
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(test_program)
        temp_path = f.name
    
    try:
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


def build_prompt(problem: Dict, error_toolbox: str = "") -> str:
    """Build HumanEval prompt. Keep it minimal — the prompt already has the signature."""
    base = problem["prompt"]
    if error_toolbox:
        return base + "\n\n" + error_toolbox + "\n"
    return base


def solve_baseline(problem: Dict, synapse: LMStudioClient,
                   n_candidates: int = 3,
                   max_tokens: int = 1024,
                   logger: Optional[PromptLogger] = None) -> Dict:
    """Baseline: k attempts, no hints, no learning."""
    task_id = problem["task_id"]
    
    for attempt in range(1, n_candidates + 1):
        # Use raw HumanEval prompt — no extra instructions
        prompt = problem["prompt"]
        
        raw = synapse.generate(prompt=prompt, temperature=0.0, max_tokens=max_tokens, n=1)
        raw_text = raw[0] if raw and raw[0] else ""
        completion = extract_code(raw_text)
        
        test_result = run_test(problem, completion) if completion else {"passed": False, "error": "extraction"}
        
        if logger:
            logger.log(
                task_id=task_id, attempt=attempt,
                result="PASS" if test_result["passed"] else "FAIL",
                prompt=prompt, raw_response=raw_text,
                extracted_code=completion or "(extraction failed)",
                test_passed=test_result["passed"],
                test_error=test_result.get("error"),
                toolbox_used=False
            )
        
        if test_result["passed"]:
            return {
                "task_id": task_id,
                "passed": True,
                "attempts": attempt,
                "error": None
            }
    
    return {
        "task_id": task_id,
        "passed": False,
        "attempts": n_candidates,
        "error": "all attempts failed"
    }


def solve_with_error_graph(problem: Dict, synapse: LMStudioClient,
                            epg: ErrorPatternGraph,
                            n_candidates: int = 3,
                            max_tokens: int = 1024,
                            logger: Optional[PromptLogger] = None) -> Dict:
    """Error-Pattern mode: attempt 1 clean, then toolbox on retry."""
    task_id = problem["task_id"]
    failure_history = []
    last_error = ""
    
    for attempt in range(1, n_candidates + 1):
        error_toolbox = ""
        if failure_history and last_error:
            error_toolbox = epg.get_fix_toolbox(last_error, top_k=3)
        
        # Use raw HumanEval prompt + optional toolbox
        prompt = problem["prompt"]
        if error_toolbox:
            prompt = prompt + "\n\n" + error_toolbox + "\n"
        
        used_toolbox = bool(error_toolbox)
        
        raw = synapse.generate(prompt=prompt, temperature=0.0, max_tokens=max_tokens, n=1)
        raw_text = raw[0] if raw and raw[0] else ""
        completion = extract_code(raw_text)
        
        test_result = run_test(problem, completion) if completion else {"passed": False, "error": "extraction"}
        
        if logger:
            logger.log(
                task_id=task_id, attempt=attempt,
                result="PASS" if test_result["passed"] else "FAIL",
                prompt=prompt, raw_response=raw_text,
                extracted_code=completion or "(extraction failed)",
                test_passed=test_result["passed"],
                test_error=test_result.get("error"),
                toolbox_used=used_toolbox
            )
        
        if test_result["passed"]:
            if last_error:
                epg.record_fix(last_error)
            return {
                "task_id": task_id,
                "passed": True,
                "attempts": attempt,
                "used_toolbox": used_toolbox,
                "error": None
            }
        else:
            error_text = test_result.get("error", "unknown")
            failure_history.append(error_text)
            last_error = error_text
            epg.record_error(error_text, problem["prompt"][:200], completion or "")
    
    return {
        "task_id": task_id,
        "passed": False,
        "attempts": n_candidates,
        "used_toolbox": any(failure_history),
        "error": failure_history[-1]
    }


def run_phase(problems: List[Dict], synapse: LMStudioClient,
              epg: ErrorPatternGraph = None,
              n_candidates: int = 1,
              phase_name: str = "",
              max_tokens: int = 1024,
              logger: Optional[PromptLogger] = None) -> List[Dict]:
    """Run one phase (baseline or error-pattern)."""
    results = []
    total = len(problems)
    is_baseline = (epg is None)
    
    print(f"\n{'='*70}")
    print(f"PHASE: {phase_name}")
    print(f"{'='*70}")
    print(f"Problems: {total} | Attempts per problem: {n_candidates}")
    if logger:
        print(f"Logging to: {logger.path}")
    print("-" * 70)
    
    start = time.time()
    
    for i, problem in enumerate(problems, 1):
        task_id = problem["task_id"]
        n_patterns = len(epg.patterns) if epg else 0
        print(f"\n[{i}/{total}] {task_id} | Patterns: {n_patterns}")
        
        if is_baseline:
            result = solve_baseline(problem, synapse, n_candidates=n_candidates, max_tokens=max_tokens, logger=logger)
        else:
            result = solve_with_error_graph(problem, synapse, epg, n_candidates=n_candidates,
                                             max_tokens=max_tokens, logger=logger)
        
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        toolbox = " [T]" if result.get("used_toolbox") else ""
        print(f"  {status}{toolbox} in {result['attempts']} attempt(s)")
    
    elapsed = time.time() - start
    passed = sum(1 for r in results if r["passed"])
    rate = passed / total * 100
    
    print("\n" + "-" * 70)
    print(f"Phase summary: {passed}/{total} passed ({rate:.1f}%) | Time: {elapsed:.0f}s")
    print("=" * 70)
    
    return results


def print_comparison(baseline: List[Dict], error_run: List[Dict], problems: List[Dict]):
    """Print side-by-side comparison."""
    n = len(problems)
    base_passed = sum(1 for r in baseline if r["passed"])
    err_passed = sum(1 for r in error_run if r["passed"])
    base_rate = base_passed / n * 100
    err_rate = err_passed / n * 100
    delta = err_rate - base_rate
    
    improvements = sum(1 for i in range(n) if not baseline[i]["passed"] and error_run[i]["passed"])
    regressions = sum(1 for i in range(n) if baseline[i]["passed"] and not error_run[i]["passed"])
    
    print("\n" + "=" * 70)
    print("BASELINE vs ERROR-PATTERN KNOWLEDGE GRAPH")
    print("=" * 70)
    print(f"{'Problem':<15} {'Baseline':<12} {'+ Error KG':<12} {'Delta':<10}")
    print("-" * 70)
    
    for i in range(n):
        b = "PASS" if baseline[i]["passed"] else "FAIL"
        e = "PASS" if error_run[i]["passed"] else "FAIL"
        d = "+" if (not baseline[i]["passed"] and error_run[i]["passed"]) else \
            ("-" if (baseline[i]["passed"] and not error_run[i]["passed"]) else "=")
        print(f"{problems[i]['task_id']:<15} {b:<12} {e:<12} {d:<10}")
    
    print("-" * 70)
    print(f"{'TOTAL':<15} {base_passed}/{n} ({base_rate:.1f}%){'':<3} {err_passed}/{n} ({err_rate:.1f}%){'':<3} {delta:+.1f} pp")
    print("=" * 70)
    print(f"\nError KG helped:   {improvements} problems")
    print(f"Error KG hurt:     {regressions} problems")
    
    if delta > 0:
        print(f">>> Error-Pattern Graph IMPROVED by {delta:+.1f} pp <<<")
    elif delta < 0:
        print(f">>> Error-Pattern Graph DECREASED by {delta:.1f} pp <<<")
    else:
        print(">>> Error-Pattern Graph had NO NET EFFECT <<<")
    
    return {
        "n_problems": n,
        "baseline_passed": base_passed,
        "error_passed": err_passed,
        "baseline_rate": base_rate,
        "error_rate": err_rate,
        "delta_pp": delta,
        "improvements": improvements,
        "regressions": regressions,
    }


def main():
    parser = argparse.ArgumentParser(description="HumanEval: Baseline vs Error-Pattern Graph")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--full", action="store_true", help="Run all 164 problems")
    parser.add_argument("--limit", type=int, default=None, help="Limit to first N problems")
    parser.add_argument("--k", type=int, default=3, help="Max attempts in Error-Pattern mode")
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--log-prompts", type=str, default=None,
                        help="Log all interactions to file (e.g., humaneval.log)")
    parser.add_argument("--output", type=str, default="humaneval_comparison.json")
    args = parser.parse_args()
    
    print("=" * 70)
    print("HUMANEVAL: BASELINE vs ERROR-PATTERN KNOWLEDGE GRAPH")
    print("=" * 70)
    print()
    print("Phase 1: BASELINE — 3 attempts per problem, no hints")
    print("Phase 2: ERROR-PATTERN — 3 attempts per problem, toolbox on retry")
    print("=" * 70)
    
    if not os.path.exists(HUMANEVAL_PATH):
        print(f"\nERROR: HumanEval not found at {HUMANEVAL_PATH}")
        print("Download it: https://github.com/openai/human-eval")
        sys.exit(1)
    
    problems = load_humaneval()
    if args.limit:
        problems = problems[:args.limit]
    elif not args.full:
        # Default: first 50 problems (good overnight size)
        problems = problems[:50]
    
    print(f"\nLoaded {len(problems)} HumanEval problems")
    
    # Auto-detect model
    model_id = args.model
    if not model_id:
        try:
            import requests
            r = requests.get("http://localhost:1234/v1/models", timeout=5)
            data = r.json()
            model_id = data["data"][0]["id"]
            print(f"Auto-detected model: {model_id}")
        except Exception:
            print("Use --model to specify the model ID")
            sys.exit(1)
    
    synapse = LMStudioClient(model=model_id, timeout=args.timeout)
    if not synapse.check_health():
        print("LM Studio not running!")
        sys.exit(1)
    print(f"LM Studio OK (model={model_id})")
    
    # Prompt logger
    logger = PromptLogger(args.log_prompts) if args.log_prompts else None
    
    # Phase 1: BASELINE
    baseline_results = run_phase(
        problems, synapse, epg=None, n_candidates=args.k,
        phase_name="BASELINE (model alone, 3 attempts)",
        max_tokens=args.max_tokens, logger=logger
    )
    
    # Phase 2: ERROR-PATTERN GRAPH
    epg_path = f"error_patterns_humaneval_{model_id.replace('/', '_')}.json"
    if os.path.exists(epg_path):
        os.remove(epg_path)
    epg = ErrorPatternGraph(storage_path=epg_path)
    
    error_results = run_phase(
        problems, synapse, epg=epg, n_candidates=args.k,
        phase_name="ERROR-PATTERN GRAPH (model + OS)",
        max_tokens=args.max_tokens, logger=logger
    )
    
    # Comparison
    stats = print_comparison(baseline_results, error_results, problems)
    
    # Show learned patterns
    print(f"\n[FINAL] Error patterns learned: {len(epg.patterns)}")
    epg.print_graph()
    
    # Save
    all_data = {
        "model": model_id,
        "n_problems": len(problems),
        "baseline_results": baseline_results,
        "error_results": error_results,
        "stats": stats,
    }
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(all_data, f, indent=2, default=str)
        print(f"\nResults saved to: {args.output}")
    except Exception as e:
        print(f"[Warning] Could not save JSON: {e}")
    
    if logger:
        print(f"Prompt log saved to: {logger.path}")
    
    print("\nDone.")


if __name__ == "__main__":
    main()
