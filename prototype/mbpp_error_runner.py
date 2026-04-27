"""
MBPP Runner with Error-Pattern Knowledge Graph + Full Interaction Logging
=========================================================================

The LLM learns from compiler feedback. Every interaction is logged:
  - Full prompt sent to the model
  - Raw response from the model
  - Extracted code
  - Test result (pass/fail + error)

Usage:
    python mbpp_error_runner.py --model qwen2.5-coder-3b-instruct --limit 50 --log-prompts interactions.log
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
from contract_graph import ContractGraph
from error_pattern_kg import ErrorPatternGraph, extract_error_fingerprint
from mbpp_cg_runner import load_mbpp, extract_code, infer_function_name, fix_function_name
from prompt_logger import PromptLogger


MBPP_PATH = os.path.join(os.path.dirname(__file__), "mbpp.jsonl")


def run_test(problem: Dict, completion: str) -> Dict:
    """Run MBPP tests on a completion."""
    # Auto-fix function name mismatch
    expected = infer_function_name(problem["test_list"])
    if expected:
        completion = fix_function_name(completion, expected)
    
    tests = "\n".join(problem["test_list"])
    test_program = completion + "\n\n" + tests + "\n"
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(test_program)
        temp_path = f.name
    
    try:
        result = subprocess.run([sys.executable, temp_path], capture_output=True, text=True, timeout=5)
        passed = result.returncode == 0
        error = result.stderr if not passed else None
        if error and len(error) > 500:
            error = error[:500] + "..."
        return {"passed": passed, "error": error}
    except subprocess.TimeoutExpired:
        return {"passed": False, "error": "Timeout"}
    except Exception as e:
        return {"passed": False, "error": str(e)}
    finally:
        os.unlink(temp_path)


def build_prompt_with_error_hint(problem_text: str, error_hint: str = "") -> str:
    """Build prompt with optional error-based fix hint."""
    base = problem_text
    instruction = (
        "\n\nWrite a Python function to solve this. "
        "Output only the complete function inside a markdown code block."
    )
    if error_hint:
        return base + "\n\n" + error_hint + instruction
    return base + instruction


def solve_problem_with_errors(problem: Dict, synapse: LMStudioClient,
                               epg: ErrorPatternGraph,
                               n_candidates: int = 3, debug: bool = False,
                               max_tokens: int = 1024,
                               logger: Optional[PromptLogger] = None) -> Dict:
    """
    Solve a problem using error-pattern feedback.
    
    Attempt 1: Clean (no hint)
    Attempt 2+: If previous failed, inject error-pattern fix hint
    """
    task_id = problem["task_id"]
    problem_text = problem["text"]
    
    failure_history = []
    last_error = ""
    
    for attempt in range(1, n_candidates + 1):
        # Build prompt — only add toolbox if previous attempt failed
        error_toolbox = ""
        trigger_error = ""
        if failure_history and last_error:
            error_toolbox = epg.get_fix_toolbox(last_error, top_k=3)
            trigger_error = last_error
            if debug and error_toolbox:
                n_patterns = error_toolbox.count("Pattern ")
                print(f"    [Attempt {attempt}] Retrieved {n_patterns} error patterns from knowledge base")
        
        prompt = build_prompt_with_error_hint(problem_text, error_toolbox)
        
        # Generic retry note only if no toolbox available
        if failure_history and not error_toolbox:
            prompt += "\n\nNOTE: Previous attempt failed. Try a different approach."
        
        used_toolbox = bool(error_toolbox)
        
        raw = synapse.generate(prompt=prompt, temperature=0.0, max_tokens=max_tokens, n=1)
        raw_text = raw[0] if raw and raw[0] else ""
        
        completion = extract_code(raw_text)
        
        # LOG THIS ATTEMPT
        if logger:
            test_result = None
            if completion:
                test_result = run_test(problem, completion)
            else:
                test_result = {"passed": False, "error": "code extraction failed"}
            
            logger.log(
                task_id=task_id,
                attempt=attempt,
                result="PASS" if test_result["passed"] else "FAIL",
                prompt=prompt,
                raw_response=raw_text,
                extracted_code=completion if completion else "(extraction failed)",
                test_passed=test_result["passed"],
                test_error=test_result.get("error"),
                toolbox_used=used_toolbox
            )
        
        if not raw or not raw[0].strip():
            failure_history.append("empty")
            last_error = "empty response"
            epg.record_error("empty response", problem_text)
            continue
        
        if not completion:
            failure_history.append("extraction")
            last_error = "code extraction failed"
            epg.record_error("code extraction failed", problem_text)
            continue
        
        test_result = run_test(problem, completion)
        
        if test_result["passed"]:
            # SUCCESS! If we used an error hint, record the fix as validated
            if last_error:
                epg.record_fix(last_error, problem_text)
            return {
                "task_id": task_id,
                "passed": True,
                "attempts": attempt,
                "used_toolbox": used_toolbox,
                "error": None
            }
        else:
            # FAILURE — extract error, record it, try again with hint
            error_text = test_result.get("error", "unknown")
            failure_history.append(error_text)
            last_error = error_text
            
            # Record this error in the graph
            err_fp = epg.record_error(error_text, problem_text, completion)
            if debug:
                err_type, err_sig = extract_error_fingerprint(error_text)
                err_preview = error_text[:100].replace('\n', ' ')
                print(f"    [Attempt {attempt}] FAIL: [{err_type}] {err_preview}")
                if error_toolbox:
                    print(f"    [Attempt {attempt}] Toolbox presented but still failed")
    
    return {
        "task_id": task_id,
        "passed": False,
        "attempts": n_candidates,
        "used_toolbox": any(failure_history),
        "error": failure_history[-1] if failure_history else "unknown"
    }


def run_benchmark(problems: List[Dict], synapse: LMStudioClient,
                  epg: ErrorPatternGraph, n_candidates: int = 3,
                  debug: bool = False, max_tokens: int = 1024,
                  logger: Optional[PromptLogger] = None) -> List[Dict]:
    """Run full benchmark with Error-Pattern Graph feedback."""
    results = []
    total = len(problems)
    
    print(f"\n[RUNNING] MBPP with Error-Pattern Graph - {total} problems...")
    print("-" * 60)
    print("Strategy: Attempt 1 is always clean. Errors from attempt 1")
    print("trigger targeted fix hints for attempt 2+.")
    if logger:
        print(f"Logging all interactions to: {logger.path}")
    print("-" * 60)
    
    start_time = time.time()
    
    for i, problem in enumerate(problems, 1):
        task_id = problem["task_id"]
        n_patterns = len(epg.patterns)
        print(f"\n[{i}/{total}] {task_id} | Error patterns: {n_patterns}")
        
        result = solve_problem_with_errors(
            problem, synapse, epg,
            n_candidates=n_candidates, debug=debug, max_tokens=max_tokens,
            logger=logger
        )
        results.append(result)
        
        status = "PASS" if result["passed"] else "FAIL"
        toolbox_ind = " (toolbox)" if result.get("used_toolbox") else ""
        print(f"  Result: {status}{toolbox_ind} in {result['attempts']} attempt(s)")
    
    elapsed = time.time() - start_time
    passed = sum(1 for r in results if r["passed"])
    rate = passed / total * 100
    
    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed}/{total} passed ({rate:.1f}%) | Time: {elapsed:.0f}s")
    print(f"Error patterns learned: {len(epg.patterns)}")
    print("=" * 60)
    
    return results


def run_baseline(problems: List[Dict], synapse: LMStudioClient,
                 n_candidates: int = 3, debug: bool = False,
                 max_tokens: int = 1024,
                 logger: Optional[PromptLogger] = None) -> List[Dict]:
    """Run baseline with NO error feedback (no hints ever)."""
    results = []
    total = len(problems)
    
    print(f"\n[RUNNING] BASELINE (no error feedback) - {total} problems...")
    print("-" * 60)
    
    for i, problem in enumerate(problems, 1):
        task_id = problem["task_id"]
        print(f"\n[{i}/{total}] {task_id}")
        
        failure_history = []
        prompt = problem["text"] + "\n\nWrite a Python function to solve this. Output only the complete function inside a markdown code block."
        
        for attempt in range(1, n_candidates + 1):
            raw = synapse.generate(prompt=prompt, temperature=0.0, max_tokens=max_tokens, n=1)
            raw_text = raw[0] if raw and raw[0] else ""
            
            completion = extract_code(raw_text)
            
            # LOG THIS ATTEMPT
            if logger:
                test_result = None
                if completion:
                    test_result = run_test(problem, completion)
                else:
                    test_result = {"passed": False, "error": "code extraction failed"}
                
                logger.log(
                    task_id=task_id,
                    attempt=attempt,
                    result="PASS" if test_result["passed"] else "FAIL",
                    prompt=prompt,
                    raw_response=raw_text,
                    extracted_code=completion if completion else "(extraction failed)",
                    test_passed=test_result["passed"],
                    test_error=test_result.get("error"),
                    toolbox_used=False
                )
            
            if not raw or not raw[0].strip():
                failure_history.append("empty")
                continue
            
            if not completion:
                failure_history.append("extraction")
                continue
            
            test_result = run_test(problem, completion)
            
            if test_result["passed"]:
                results.append({
                    "task_id": task_id, "passed": True,
                    "attempts": attempt, "used_toolbox": False, "error": None
                })
                print(f"  Result: PASS in {attempt} attempt(s)")
                break
            else:
                failure_history.append(test_result.get("error", "fail"))
        else:
            results.append({
                "task_id": task_id, "passed": False,
                "attempts": n_candidates, "used_toolbox": False,
                "error": failure_history[-1] if failure_history else "unknown"
            })
            print(f"  Result: FAIL in {n_candidates} attempt(s)")
    
    passed = sum(1 for r in results if r["passed"])
    rate = passed / total * 100
    print(f"\nBASELINE: {passed}/{total} passed ({rate:.1f}%)")
    
    return results


def print_comparison(baseline: List[Dict], error_run: List[Dict], 
                     problems: List[Dict]):
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
    print("BASELINE vs ERROR-PATTERN GRAPH")
    print("=" * 70)
    print(f"{'Problem':<15} {'Baseline':<12} {'+ Error KG':<12} {'Delta':<10}")
    print("-" * 70)
    
    for i in range(n):
        b = "PASS" if baseline[i]["passed"] else "FAIL"
        e = "PASS" if error_run[i]["passed"] else "FAIL"
        d = "+" if (not baseline[i]["passed"] and error_run[i]["passed"]) else \
            ("-" if (baseline[i]["passed"] and not error_run[i]["passed"]) else "=")
        # Check if toolbox/contract was used (either field name)
        used = error_run[i].get("used_toolbox") or error_run[i].get("used_contract") or error_run[i].get("used_hint")
        hint_mark = " [T]" if used else ""
        print(f"{problems[i]['task_id']:<15} {b:<12} {e:<12} {d:<10}{hint_mark}")
    
    print("-" * 70)
    print(f"{'TOTAL':<15} {base_passed}/{n} ({base_rate:.1f}%){'':<3} {err_passed}/{n} ({err_rate:.1f}%){'':<3} {delta:+.1f} pp")
    print("=" * 70)
    print(f"\nError KG helped: {improvements} problems")
    print(f"Error KG hurt:   {regressions} problems")
    
    if delta > 0:
        print(f">>> Error-Pattern Graph IMPROVED by {delta:+.1f} pp <<<")
    elif delta < 0:
        print(f">>> Error-Pattern Graph DECREASED by {delta:.1f} pp <<<")
    else:
        print(">>> Error-Pattern Graph had NO NET EFFECT <<<")
    
    return {"baseline_rate": base_rate, "error_rate": err_rate, "delta_pp": delta,
            "improvements": improvements, "regressions": regressions}


def main():
    parser = argparse.ArgumentParser(
        description="MBPP with Error-Pattern Knowledge Graph"
    )
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--output", type=str, default="mbpp_error_results.json")
    parser.add_argument("--log-prompts", type=str, default=None,
                        help="Path to log all LLM interactions (e.g., interactions.log)")
    parser.add_argument("--baseline-only", action="store_true",
                        help="Run only baseline (no error feedback)")
    parser.add_argument("--error-only", action="store_true",
                        help="Run only error-pattern mode (skip baseline)")
    args = parser.parse_args()
    
    print("=" * 70)
    print("PUZZLE LOGIC AI — ERROR-PATTERN KNOWLEDGE GRAPH")
    print("=" * 70)
    print()
    print("The model learns from compiler feedback.")
    print("Attempt 1: clean. If it fails, search for similar past errors.")
    print("Attempt 2+: inject targeted fix hints based on actual errors.")
    print("=" * 70)
    
    # Load problems
    problems = load_mbpp()
    print(f"\nLoaded {len(problems)} problems from MBPP")
    problems = problems[:args.limit]
    print(f"Using first {len(problems)} problems")
    
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
    
    # Fresh Error-Pattern Graph
    epg_path = f"error_patterns_{model_id.replace('/', '_')}.json"
    if os.path.exists(epg_path):
        os.remove(epg_path)
    epg = ErrorPatternGraph(storage_path=epg_path)
    
    all_data = {}
    
    # Phase 1: Baseline
    if not args.error_only:
        baseline_results = run_baseline(
            problems, synapse, n_candidates=args.k,
            debug=args.debug, max_tokens=args.max_tokens,
            logger=logger
        )
        all_data["baseline_results"] = baseline_results
    
    # Phase 2: Error-Pattern Graph
    if not args.baseline_only:
        # Fresh graph
        if os.path.exists(epg_path):
            os.remove(epg_path)
        epg = ErrorPatternGraph(storage_path=epg_path)
        
        error_results = run_benchmark(
            problems, synapse, epg, n_candidates=args.k,
            debug=args.debug, max_tokens=args.max_tokens,
            logger=logger
        )
        all_data["error_results"] = error_results
        
        # Show learned error patterns
        print(f"\n[FINAL] Error patterns learned: {len(epg.patterns)}")
        epg.print_graph()
        stats = epg.get_stats()
        print(f"\n[STATS] {stats}")
    
    # Comparison
    if not args.baseline_only and not args.error_only:
        stats = print_comparison(baseline_results, error_results, problems)
        all_data["comparison"] = stats
    
    # Save results JSON
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(all_data, f, indent=2, default=str)
        print(f"\nResults saved to: {args.output}")
    except Exception as e:
        print(f"[Warning] Could not save JSON: {e}")
    
    if logger:
        print(f"\nInteraction log saved to: {logger.path}")
    
    print("\nDone.")


if __name__ == "__main__":
    main()
