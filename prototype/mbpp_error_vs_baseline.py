"""
MBPP Error-Pattern Graph vs Saved Baseline
===========================================

Loads a previously saved baseline result and runs ONLY the
Error-Pattern Graph phase for comparison. No need to re-run baseline.

Usage:
    # Load baseline from previous comparison, run error-pattern phase
    python mbpp_error_vs_baseline.py --baseline mbpp_comparison.json --model qwen-4b-instruct-2507
"""

import json
import os
import sys
import argparse

from lmstudio_client import LMStudioClient
from error_pattern_kg import ErrorPatternGraph
from mbpp_error_runner import run_benchmark, run_test, print_comparison, PromptLogger
from mbpp_cg_runner import load_mbpp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=str, required=True,
                        help="Path to saved baseline JSON (e.g., mbpp_comparison.json)")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--output", type=str, default="mbpp_error_vs_baseline.json")
    parser.add_argument("--log-prompts", type=str, default=None,
                        help="Path to log all prompts (e.g., prompts.log)")
    args = parser.parse_args()
    
    print("=" * 70)
    print("ERROR-PATTERN GRAPH vs SAVED BASELINE")
    print("=" * 70)
    print(f"Loading baseline from: {args.baseline}")
    
    # Load saved baseline
    with open(args.baseline, "r", encoding="utf-8") as f:
        saved_data = json.load(f)
    
    # Handle both formats: list (from comparison) and dict
    if isinstance(saved_data, list):
        saved_data = saved_data[0]
    
    baseline_results = saved_data.get("baseline_results", saved_data.get("baseline", []))
    baseline_count = sum(1 for r in baseline_results if r["passed"])
    print(f"  Baseline: {baseline_count}/{len(baseline_results)} passed ({baseline_count/len(baseline_results)*100:.1f}%)")
    
    # Load problems
    problems = load_mbpp()[:args.limit]
    print(f"\nRunning Error-Pattern Graph on {len(problems)} problems...")
    
    # Setup
    model_id = args.model
    if not model_id:
        try:
            import requests
            r = requests.get("http://localhost:1234/v1/models", timeout=5)
            model_id = r.json()["data"][0]["id"]
        except Exception:
            print("Use --model")
            sys.exit(1)
    
    synapse = LMStudioClient(model=model_id, timeout=args.timeout)
    if not synapse.check_health():
        print("LM Studio not running!")
        sys.exit(1)
    
    # Prompt logger
    logger = PromptLogger(args.log_prompts) if args.log_prompts else None
    
    # Fresh Error-Pattern Graph
    epg_path = f"error_patterns_{model_id.replace('/', '_')}.json"
    if os.path.exists(epg_path):
        os.remove(epg_path)
    epg = ErrorPatternGraph(storage_path=epg_path)
    
    # Run only error-pattern phase
    error_results = run_benchmark(
        problems, synapse, epg, n_candidates=args.k,
        debug=args.debug, max_tokens=args.max_tokens, logger=logger
    )
    
    # Compare against saved baseline
    error_passed = sum(1 for r in error_results if r["passed"])
    base_passed = sum(1 for r in baseline_results if r["passed"])
    n = min(len(baseline_results), len(error_results))
    
    # Trim baseline to match current run length if different
    baseline_trimmed = baseline_results[:n]
    error_trimmed = error_results[:n]
    
    stats = print_comparison(baseline_trimmed, error_trimmed, problems[:n])
    stats["model"] = model_id
    stats["n_contracts_learned"] = len(epg.patterns)
    
    # Show learned patterns
    print(f"\n[FINAL] Error patterns learned: {len(epg.patterns)}")
    epg.print_graph()
    
    # Save
    all_data = {
        "baseline_source": args.baseline,
        "baseline_passed": base_passed,
        "error_passed": error_passed,
        "error_results": error_results,
        "stats": stats,
    }
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(all_data, f, indent=2, default=str)
        print(f"\nResults saved to: {args.output}")
    except Exception as e:
        print(f"[Warning] Could not save: {e}")
    
    if logger:
        print(f"\nPrompt log saved to: {logger.path}")
    
    print("\nDone.")


if __name__ == "__main__":
    main()
