"""
MBPP Baseline vs Contract Graph Comparison Runner
===================================================

Runs the SAME problems twice:
  1. BASELINE: Model alone, no hints, no learning
  2. CONTRACT GRAPH: Model + accumulated hints, learning enabled

This isolates the effect of the Contract Graph. Both runs see
identical problems in identical order. The only difference is whether
the graph provides hints and learns from successes.

Multi-model mode:
  Run the comparison across several models to see which benefits
  most from the Puzzle Logic OS layer.

Usage:
    # Single model comparison (50 problems)
    python mbpp_compare_runner.py --model qwen-4b-instruct-2507 --limit 50

    # Multi-model shootout
    python mbpp_compare_runner.py --models "qwen-4b-instruct-2507,deepseek-coder-v2-lite-instruct" --limit 30

    # Quick smoke test
    python mbpp_compare_runner.py --limit 10 --k 2 --debug
"""

import json
import os
import sys
import tempfile
import subprocess
import argparse
import re
import time
from typing import List, Dict, Any

from lmstudio_client import LMStudioClient
from contract_graph import ContractGraph

# Import utilities from the main runner
from mbpp_cg_runner import load_mbpp, extract_code, run_test, build_prompt


MBPP_PATH = os.path.join(os.path.dirname(__file__), "mbpp.jsonl")


def solve_problem(problem: Dict, synapse: LMStudioClient, cg: ContractGraph,
                  n_candidates: int = 3, learn: bool = True,
                  use_graph: bool = True, debug: bool = False,
                  max_tokens: int = 1024) -> Dict:
    """
    Solve a single problem. If use_graph=False, hints are disabled
    but the graph object still exists (for structural consistency).
    """
    task_id = problem["task_id"]
    
    contract_hint = ""
    if use_graph:
        contract_hint = cg.get_contract_hints(problem["text"], top_k=2)
        if contract_hint:
            print(f"    [CG] Using {len([l for l in contract_hint.split(chr(10)) if l.strip().startswith('-')])} learned contracts")
    
    prompt = build_prompt(problem, contract_hint)
    
    failure_history = []
    best_code = ""
    
    for attempt in range(1, n_candidates + 1):
        if failure_history and attempt >= 2:
            feedback = "\n\nNOTE: Previous attempt failed. Please try again."
            attempt_prompt = prompt + feedback
        else:
            attempt_prompt = prompt
        
        raw = synapse.generate(prompt=attempt_prompt, temperature=0.3, max_tokens=max_tokens, n=1)
        
        if not raw or not raw[0].strip():
            failure_history.append("empty")
            continue
        
        completion = extract_code(raw[0])
        if not completion:
            failure_history.append("extraction")
            continue
        
        best_code = completion
        test_result = run_test(problem, completion)
        
        if test_result["passed"]:
            if learn:
                cg.learn_from_solution(
                    task_id=task_id,
                    problem_text=problem["text"],
                    solution_code=completion,
                    attempts=attempt
                )
            return {
                "task_id": task_id,
                "passed": True,
                "attempts": attempt,
                "used_contract": bool(contract_hint),
                "error": None
            }
        else:
            failure_history.append(test_result["error"])
    
    return {
        "task_id": task_id,
        "passed": False,
        "attempts": n_candidates,
        "used_contract": bool(contract_hint),
        "error": failure_history[-1] if failure_history else "unknown"
    }


def run_phase(problems: List[Dict], synapse: LMStudioClient, cg: ContractGraph,
              n_candidates: int = 3, learn: bool = True, use_graph: bool = True,
              debug: bool = False, max_tokens: int = 1024, phase_name: str = "") -> List[Dict]:
    """Run one phase (baseline or CG) on the problem set."""
    results = []
    total = len(problems)
    
    print(f"\n{'='*70}")
    print(f"PHASE: {phase_name}")
    print(f"{'='*70}")
    print(f"Model: {synapse.model or 'default'}")
    print(f"Graph: {'hints ON, learning ON' if use_graph else 'hints OFF, learning OFF'}")
    print(f"Problems: {total} | Attempts per problem: {n_candidates}")
    print("-" * 70)
    
    start_time = time.time()
    
    for i, problem in enumerate(problems, 1):
        task_id = problem["task_id"]
        n_contracts = len(cg.nodes)
        print(f"\n[{i}/{total}] {task_id} | Graph: {n_contracts} contracts")
        
        result = solve_problem(problem, synapse, cg, n_candidates=n_candidates,
                               learn=learn, use_graph=use_graph, debug=debug,
                               max_tokens=max_tokens)
        results.append(result)
        
        status = "PASS" if result["passed"] else "FAIL"
        cg_ind = " (CG)" if result["used_contract"] else ""
        print(f"  Result: {status}{cg_ind} in {result['attempts']} attempt(s)")
    
    elapsed = time.time() - start_time
    passed = sum(1 for r in results if r["passed"])
    rate = passed / total * 100
    avg_attempts = sum(r["attempts"] for r in results) / total
    
    print("\n" + "-" * 70)
    print(f"Phase summary: {passed}/{total} passed ({rate:.1f}%) | Avg attempts: {avg_attempts:.1f} | Time: {elapsed:.0f}s")
    print("=" * 70)
    
    return results


def print_comparison(baseline: List[Dict], cg_run: List[Dict], problems: List[Dict]):
    """Print side-by-side comparison of baseline vs Contract Graph."""
    n = len(problems)
    
    base_passed = sum(1 for r in baseline if r["passed"])
    cg_passed = sum(1 for r in cg_run if r["passed"])
    base_rate = base_passed / n * 100
    cg_rate = cg_passed / n * 100
    delta = cg_rate - base_rate
    
    # Per-problem breakdown
    print("\n" + "=" * 70)
    print("SIDE-BY-SIDE COMPARISON (Baseline vs Contract Graph)")
    print("=" * 70)
    print(f"{'Problem':<15} {'Baseline':<12} {'+ CG':<12} {'Delta':<10} {'Hint used'}")
    print("-" * 70)
    
    improvements = 0
    regressions = 0
    first_cg_help = None
    
    for i in range(n):
        b_pass = baseline[i]["passed"]
        c_pass = cg_run[i]["passed"]
        b_str = "PASS" if b_pass else "FAIL"
        c_str = "PASS" if c_pass else "FAIL"
        delta_str = "+" if (c_pass and not b_pass) else ("-" if (b_pass and not c_pass) else "=")
        hint = "YES" if cg_run[i]["used_contract"] else "no"
        
        if c_pass and not b_pass:
            improvements += 1
            if first_cg_help is None:
                first_cg_help = i
        if b_pass and not c_pass:
            regressions += 1
        
        print(f"{problems[i]['task_id']:<15} {b_str:<12} {c_str:<12} {delta_str:<10} {hint}")
    
    print("-" * 70)
    print(f"{'TOTAL':<15} {base_passed}/{n} ({base_rate:.1f}%){'':<3} {cg_passed}/{n} ({cg_rate:.1f}%){'':<3} {delta:+.1f} pp")
    print("=" * 70)
    
    # Analysis
    print(f"\nProblems where CG helped (baseline FAIL → CG PASS): {improvements}")
    print(f"Problems where CG hurt  (baseline PASS → CG FAIL): {regressions}")
    if first_cg_help is not None:
        print(f"First problem helped by CG: #{first_cg_help + 1} ({problems[first_cg_help]['task_id']})")
    
    # Compounding check
    cg_contracts_used = sum(1 for r in cg_run if r["used_contract"])
    print(f"Contract hints retrieved across all problems: {cg_contracts_used}")
    
    if delta > 0:
        print(f"\n>>> Contract Graph IMPROVED performance by {delta:+.1f} percentage points <<<")
    elif delta < 0:
        print(f"\n>>> Contract Graph DECREASED performance by {delta:.1f} percentage points <<<")
    else:
        print(f"\n>>> Contract Graph had NO NET EFFECT on pass rate <<<")
    
    return {
        "n_problems": n,
        "baseline_passed": base_passed,
        "cg_passed": cg_passed,
        "baseline_rate": base_rate,
        "cg_rate": cg_rate,
        "delta_pp": delta,
        "improvements": improvements,
        "regressions": regressions,
        "contracts_used": cg_contracts_used,
    }


def run_single_model_comparison(problems: List[Dict], model_id: str, n_candidates: int,
                                max_tokens: int, timeout: int, debug: bool) -> Dict:
    """Run baseline + CG comparison for a single model."""
    print("\n" + "=" * 70)
    print(f"MODEL COMPARISON: {model_id}")
    print("=" * 70)
    
    synapse = LMStudioClient(model=model_id, timeout=timeout)
    if not synapse.check_health():
        print(f"[ERROR] LM Studio not running or model '{model_id}' not loaded.")
        return None
    
    # Phase 1: BASELINE (no hints, no learning)
    cg_baseline = ContractGraph(storage_path="_baseline_temp.json")
    baseline_results = run_phase(problems, synapse, cg_baseline,
                                 n_candidates=n_candidates, learn=False, use_graph=False,
                                 debug=debug, max_tokens=max_tokens, phase_name="BASELINE (model alone)")
    
    # Phase 2: CONTRACT GRAPH (hints ON, learning ON)
    # Fresh graph, but it will accumulate as it solves
    cg_path = f"contract_graph_{model_id.replace('/', '_')}.json"
    if os.path.exists(cg_path):
        os.remove(cg_path)
    cg_learning = ContractGraph(storage_path=cg_path)
    cg_results = run_phase(problems, synapse, cg_learning,
                           n_candidates=n_candidates, learn=True, use_graph=True,
                           debug=debug, max_tokens=max_tokens, phase_name="CONTRACT GRAPH (model + OS)")
    
    # Compare
    stats = print_comparison(baseline_results, cg_results, problems)
    stats["model"] = model_id
    stats["n_contracts_learned"] = len(cg_learning.nodes)
    
    # Show learned contracts
    print(f"\n[FINAL] Contract Graph learned {len(cg_learning.nodes)} contracts:")
    cg_learning.print_graph()
    
    return {
        "model": model_id,
        "baseline_results": baseline_results,
        "cg_results": cg_results,
        "stats": stats,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Baseline vs Contract Graph comparison on MBPP"
    )
    parser.add_argument("--model", type=str, default=None,
                        help="Single model to test")
    parser.add_argument("--models", type=str, default=None,
                        help="Comma-separated list of models for multi-model shootout")
    parser.add_argument("--limit", type=int, default=50,
                        help="Number of problems (default 50)")
    parser.add_argument("--k", type=int, default=3,
                        help="Attempts per problem")
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--output", type=str, default="mbpp_comparison.json")
    args = parser.parse_args()
    
    print("=" * 70)
    print("PUZZLE LOGIC AI — BASELINE vs CONTRACT GRAPH COMPARISON")
    print("=" * 70)
    print()
    print("This runs the SAME problems twice:")
    print("  1. BASELINE: Model alone, no hints, no learning")
    print("  2. CONTRACT GRAPH: Model + Puzzle Logic OS (hints + learning)")
    print()
    print("The delta shows exactly what the OS layer contributes.")
    print("=" * 70)
    
    # Load problems
    problems = load_mbpp()
    print(f"\nLoaded {len(problems)} problems from MBPP")
    problems = problems[:args.limit]
    print(f"Using first {len(problems)} problems for comparison")
    
    # Determine models to test
    models = []
    if args.models:
        models = [m.strip() for m in args.models.split(",")]
    elif args.model:
        models = [args.model]
    else:
        # Auto-detect first loaded model
        try:
            import requests
            r = requests.get("http://localhost:1234/v1/models", timeout=5)
            data = r.json()
            if data.get("data"):
                models = [data["data"][0]["id"]]
                print(f"Auto-detected model: {models[0]}")
            else:
                print("No models loaded in LM Studio. Exiting.")
                sys.exit(1)
        except Exception:
            print("Could not auto-detect model. Use --model or --models.")
            sys.exit(1)
    
    # Run comparison for each model
    all_results = []
    for model_id in models:
        result = run_single_model_comparison(
            problems, model_id, args.k, args.max_tokens, args.timeout, args.debug
        )
        if result:
            all_results.append(result)
    
    # Multi-model summary
    if len(all_results) > 1:
        print("\n" + "=" * 70)
        print("MULTI-MODEL SUMMARY")
        print("=" * 70)
        print(f"{'Model':<40} {'Baseline':<12} {'+ CG':<12} {'Delta':<10}")
        print("-" * 70)
        for r in all_results:
            s = r["stats"]
            print(f"{r['model']:<40} {s['baseline_rate']:>5.1f}%{'':<6} {s['cg_rate']:>5.1f}%{'':<6} {s['delta_pp']:>+5.1f} pp")
        print("=" * 70)
    
    # Save
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, default=str)
        print(f"\nResults saved to: {args.output}")
    except Exception as e:
        print(f"\n[Warning] Could not save JSON: {e}")
    
    print("\nDone.")


if __name__ == "__main__":
    main()
