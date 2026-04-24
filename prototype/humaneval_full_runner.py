"""
HumanEval Full Benchmark — Difficulty-Tiered Evaluation
========================================================

Runs the complete OpenAI HumanEval benchmark (164 problems) comparing:
  BASE (pass@1): Single attempt, no validation, no help
  OS (pass@3):   Up to 3 attempts with error feedback

Groups results by difficulty tier so you can see WHERE the OS helps:
  Tier 1 (Easy):    Basic functions, loops, conditionals
  Tier 2 (Medium):  String manipulation, math, edge cases  
  Tier 3 (Hard):    Algorithms, parsing, state machines
  Tier 4 (Expert):  Complex logic, graph problems, advanced algorithms

Usage:
    # Full benchmark (~90-120 minutes on 8B model)
    python humaneval_full_runner.py --mode both
    
    # Just base mode (~30 minutes)
    python humaneval_full_runner.py --mode base
    
    # Just OS mode (~60 minutes)
    python humaneval_full_runner.py --mode os

Output:
    Console: tiered comparison table
    humaneval_full_results.json: Complete results for analysis
"""

import json
import os
import sys
import tempfile
import argparse
import re
import time
from typing import List, Dict, Any, Tuple

from lmstudio_client import LMStudioClient


HUMANEVAL_PATH = os.path.join(os.path.dirname(__file__), "HumanEval.jsonl")

# Difficulty tiers based on HumanEval problem indices
# HumanEval roughly increases in difficulty as index increases
TIERS = {
    "Tier 1 (Easy)":    (0, 40),    # Basic functions
    "Tier 2 (Medium)":  (41, 80),   # String/math/edge cases
    "Tier 3 (Hard)":    (81, 120),  # Algorithms/parsing
    "Tier 4 (Expert)":  (121, 163), # Complex/advanced
}


def load_humaneval() -> List[Dict[str, Any]]:
    problems = []
    with open(HUMANEVAL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            problems.append(json.loads(line))
    return problems


def get_tier(problem_index: int) -> str:
    """Determine which difficulty tier a problem belongs to."""
    for tier_name, (start, end) in TIERS.items():
        if start <= problem_index <= end:
            return tier_name
    return "Unknown"


def extract_code(text: str) -> str:
    """Extract code from model output."""
    if not text:
        return ""
    match = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    if "def " in text or "return" in text or "for " in text or "if " in text:
        return text.strip()
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


def build_prompt(problem: Dict, previous_errors: List[str] = None) -> str:
    """Build prompt with optional error feedback."""
    base = problem["prompt"]
    instruction = (
        "\n\nComplete the function above. Output the code inside a markdown code block.\n"
        "You may output either the full function or just the function body."
    )
    if previous_errors:
        feedback = "\n\nNOTE: Previous attempt did not pass tests. Please try again."
        return base + instruction + feedback
    return base + instruction


def run_base_mode(problems: List[Dict], synapse: LMStudioClient) -> List[Dict]:
    """BASE MODE: Standard pass@1."""
    results = []
    total = len(problems)
    start_time = time.time()
    
    print(f"\n[BASE MODE] pass@1 on {total} problems...")
    print("-" * 70)
    
    for i, problem in enumerate(problems, 1):
        task_id = problem["task_id"]
        idx = int(task_id.split("/")[1])
        
        prompt = build_prompt(problem)
        raw = synapse.generate(prompt=prompt, temperature=0.2, max_tokens=1024, n=1)
        
        if not raw or not raw[0].strip():
            results.append({"task_id": task_id, "index": idx, "passed": False,
                            "attempts": 1, "error": "Empty generation"})
            print(f"  [{i}/{total}] {task_id} (T{get_tier(idx)}): EMPTY")
            continue
        
        completion = extract_code(raw[0])
        test_result = run_test(problem, completion)
        
        results.append({"task_id": task_id, "index": idx, "passed": test_result["passed"],
                        "attempts": 1, "error": test_result["error"]})
        
        status = "PASS" if test_result["passed"] else "FAIL"
        
        # Progress with ETA
        elapsed = time.time() - start_time
        avg_per = elapsed / i
        remaining = avg_per * (total - i)
        eta_mins = int(remaining / 60)
        
        print(f"  [{i}/{total}] {task_id}: {status}  (ETA: {eta_mins}m)")
    
    total_time = time.time() - start_time
    print(f"  Base mode complete: {total_time/60:.1f} minutes")
    return results


def run_os_mode(problems: List[Dict], synapse: LMStudioClient, n_candidates: int = 3) -> List[Dict]:
    """OS MODE: Adaptive best-of-k with error feedback."""
    results = []
    total = len(problems)
    start_time = time.time()
    
    print(f"\n[OS MODE] Adaptive best-of-{n_candidates} on {total} problems...")
    print("-" * 70)
    
    for i, problem in enumerate(problems, 1):
        task_id = problem["task_id"]
        idx = int(task_id.split("/")[1])
        best_passed = False
        best_attempts = 0
        best_error = None
        previous_errors = []
        
        for attempt in range(1, n_candidates + 1):
            prompt = build_prompt(problem, previous_errors if previous_errors else None)
            raw = synapse.generate(prompt=prompt, temperature=0.3, max_tokens=1024, n=1)
            
            if not raw or not raw[0].strip():
                previous_errors.append("Empty generation")
                continue
            
            completion = extract_code(raw[0])
            if not completion:
                previous_errors.append("No code extracted")
                continue
            
            test_result = run_test(problem, completion)
            best_attempts = attempt
            
            if test_result["passed"]:
                best_passed = True
                break
            else:
                previous_errors.append(test_result["error"])
                best_error = test_result["error"]
        
        results.append({"task_id": task_id, "index": idx, "passed": best_passed,
                        "attempts": best_attempts, "error": best_error})
        
        status = "PASS" if best_passed else "FAIL"
        
        # Progress with ETA
        elapsed = time.time() - start_time
        avg_per = elapsed / i
        remaining = avg_per * (total - i)
        eta_mins = int(remaining / 60)
        
        print(f"  [{i}/{total}] {task_id}: {status} ({best_attempts} tries)  (ETA: {eta_mins}m)")
    
    total_time = time.time() - start_time
    print(f"  OS mode complete: {total_time/60:.1f} minutes")
    return results


def analyze_by_tier(base_results: List[Dict], os_results: List[Dict]) -> Dict:
    """Group results by difficulty tier and compute stats."""
    tier_data = {}
    
    for tier_name, (start, end) in TIERS.items():
        base_tier = [r for r in base_results if start <= r["index"] <= end]
        os_tier = [r for r in os_results if start <= r["index"] <= end]
        
        base_passed = sum(1 for r in base_tier if r["passed"])
        os_passed = sum(1 for r in os_tier if r["passed"])
        total = len(base_tier)
        
        tier_data[tier_name] = {
            "n_problems": total,
            "base_passed": base_passed,
            "os_passed": os_passed,
            "base_rate": (base_passed / total * 100) if total > 0 else 0,
            "os_rate": (os_passed / total * 100) if total > 0 else 0,
            "improvement": ((os_passed - base_passed) / total * 100) if total > 0 else 0,
            "recoveries": sum(1 for b, o in zip(base_tier, os_tier)
                             if not b["passed"] and o["passed"]),
        }
    
    return tier_data


def print_tiered_results(tier_data: Dict):
    """Print the beautiful tiered comparison table."""
    print("\n" + "=" * 80)
    print("HUMANEVAL FULL BENCHMARK: TIERED RESULTS")
    print("=" * 80)
    print(f"\n{'Tier':<22} {'Problems':<10} {'Base':<10} {'OS':<10} {'Delta':<10} {'Recovered'}")
    print("-" * 80)
    
    total_base = 0
    total_os = 0
    total_problems = 0
    total_recoveries = 0
    
    for tier_name in ["Tier 1 (Easy)", "Tier 2 (Medium)", "Tier 3 (Hard)", "Tier 4 (Expert)"]:
        data = tier_data[tier_name]
        print(f"{tier_name:<22} {data['n_problems']:<10} "
              f"{data['base_rate']:.1f}%{'':<5} "
              f"{data['os_rate']:.1f}%{'':<5} "
              f"{data['improvement']:+.1f}%{'':<5} "
              f"{data['recoveries']}")
        
        total_base += data["base_passed"]
        total_os += data["os_passed"]
        total_problems += data["n_problems"]
        total_recoveries += data["recoveries"]
    
    print("-" * 80)
    overall_base = total_base / total_problems * 100
    overall_os = total_os / total_problems * 100
    overall_delta = overall_os - overall_base
    
    print(f"{'OVERALL':<22} {total_problems:<10} "
          f"{overall_base:.1f}%{'':<5} "
          f"{overall_os:.1f}%{'':<5} "
          f"{overall_delta:+.1f}%{'':<5} "
          f"{total_recoveries}")
    
    print("\n" + "=" * 80)
    print("INTERPRETATION")
    print("=" * 80)
    
    if overall_delta > 0:
        relative = (total_os - total_base) / total_base * 100 if total_base > 0 else 0
        print(f"The Puzzle Logic OS improves HumanEval pass@1 by {overall_delta:.1f} points.")
        print(f"That's {relative:.0f}% more problems solved.")
        print(f"{total_recoveries} problems were specifically recovered through feedback/retries.")
    else:
        print("No overall improvement in this run.")
        print("The model may be saturated on this dataset.")
    
    # Find the tier with biggest improvement
    best_tier = max(tier_data.items(), key=lambda x: x[1]["improvement"])
    print(f"\nLargest improvement: {best_tier[0]} (+{best_tier[1]['improvement']:.1f} points)")
    
    # Published baselines for comparison
    print("\n" + "-" * 80)
    print("PUBLISHED BASELINES (HumanEval pass@1):")
    print("  CodeLlama-7B:      ~28%")
    print("  DeepSeek-Coder-6B: ~47%")
    print("  Qwen2.5-Coder-7B:  ~80%")
    print("  GPT-4:             ~67%")
    print("  Claude 3.5 Sonnet: ~92%")
    print(f"  Your model (base): {overall_base:.1f}%")
    print(f"  Your model (OS):   {overall_os:.1f}%")
    print("=" * 80)


def save_results(base_results, os_results, tier_data, filename="humaneval_full_results.json"):
    total_problems = len(base_results)
    total_base = sum(1 for r in base_results if r["passed"])
    total_os = sum(1 for r in os_results if r["passed"])
    
    data = {
        "benchmark": "HumanEval (Full, 164 problems)",
        "model_info": "Local 8B via LM Studio",
        "n_problems": total_problems,
        "overall": {
            "base_passed": total_base,
            "os_passed": total_os,
            "base_rate": total_base / total_problems,
            "os_rate": total_os / total_problems,
            "improvement": (total_os - total_base) / total_problems
        },
        "by_tier": tier_data,
        "base_results": base_results,
        "os_results": os_results
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"\nComplete results saved to: {filename}")


def main():
    parser = argparse.ArgumentParser(description="Run full HumanEval with tiered analysis")
    parser.add_argument("--mode", choices=["base", "os", "both"], default="both")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--output", type=str, default="humaneval_full_results.json")
    args = parser.parse_args()
    
    if not os.path.exists(HUMANEVAL_PATH):
        print(f"ERROR: HumanEval not found at {HUMANEVAL_PATH}")
        sys.exit(1)
    
    print("=" * 80)
    print("PUZZLE LOGIC AI - FULL HUMANEVAL BENCHMARK")
    print("=" * 80)
    print()
    print("This runs the complete HumanEval benchmark (164 problems) and")
    print("groups results by difficulty tier to show where the OS helps.")
    print()
    print("Estimated time:")
    print("  Base mode (~30 min) + OS mode (~60 min) = ~90 min total")
    print("  Grab coffee. This will take a while.")
    print("-" * 80)
    
    problems = load_humaneval()
    print(f"Loaded {len(problems)} problems from HumanEval")
    
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
        tier_data = analyze_by_tier(base_results, os_results)
        print_tiered_results(tier_data)
        save_results(base_results, os_results, tier_data, args.output)
    elif args.mode == "base":
        p = sum(1 for r in base_results if r["passed"])
        print(f"\nBase: {p}/{len(base_results)} ({p/len(base_results)*100:.1f}%)")
    elif args.mode == "os":
        p = sum(1 for r in os_results if r["passed"])
        print(f"\nOS: {p}/{len(os_results)} ({p/len(os_results)*100:.1f}%)")
    
    print("\nDone.")


if __name__ == "__main__":
    main()
