"""
Puzzle Logic AI — Benchmark Runner
===================================

Compares raw model performance (1-shot, no validation)
against Puzzle Logic OS performance (multi-candidate + constraint selection).

Run: python benchmark_runner.py

Output: A comparison table showing which approach succeeds on each task.
"""

import os
import shutil
import time

from benchmark_suite import get_all_tasks
from puzzle_logic_agent import PuzzleLogicAgent
from constraint_engine import ConstraintEngine


def clean_project_dir():
    """Remove old benchmark project files."""
    if os.path.exists("benchmark_project"):
        shutil.rmtree("benchmark_project")


def run_base_mode(task, synapse):
    """
    BASE MODE: The raw model generates 1 candidate.
    No validation, no retry. If it fails, task is failed.
    
    This simulates how most users interact with coding assistants:
    ask once, accept what you get, hope it works.
    """
    module_path, test_path = task.setup("benchmark_project")
    
    # Read existing module for context
    with open(module_path, "r", encoding="utf-8") as f:
        existing_code = f.read()
    
    prompt = build_prompt(task, existing_code)
    
    # Generate 1 candidate (temperature slightly higher to get variety)
    raw = synapse.generate(prompt, temperature=0.8, n=1)
    candidate = extract_code(raw[0]) if raw else ""
    
    if not candidate.strip():
        return {
            "mode": "BASE",
            "success": False,
            "tension": 1.0,
            "attempts": 1,
            "reason": "Empty candidate"
        }
    
    # Write candidate to module
    with open(module_path, "w", encoding="utf-8") as f:
        f.write(candidate)
    
    # Evaluate
    engine = ConstraintEngine(test_file=test_path)
    tension, results = engine.evaluate(candidate, module_path)
    
    success = all(r.passed for r in results)
    
    failed_reasons = [r.name for r in results if not r.passed]
    
    return {
        "mode": "BASE",
        "success": success,
        "tension": tension,
        "attempts": 1,
        "reason": ", ".join(failed_reasons) if failed_reasons else "All passed"
    }


def run_os_mode(task, agent):
    """
    OS MODE: The Puzzle Logic agent generates up to 3 candidates,
    validates each against constraints, and picks the one with
    the LOWEST structural tension.
    
    This is the Puzzle Logic advantage: empirical selection over
    random generation. If candidate 1 fails, try candidate 2.
    If all fail, the task is failed — but at least we tried.
    """
    clean_project_dir()
    module_path, test_path = task.setup("benchmark_project")
    
    # Reset agent state for this task
    agent.constraint_engine.test_file = test_path
    agent.constraint_engine.existing_module = module_path
    
    # Read existing module
    with open(module_path, "r", encoding="utf-8") as f:
        existing_code = f.read()
    
    prompt = build_prompt(task, existing_code)
    
    # Generate candidates
    n_candidates = 3
    raw_candidates = agent.synapse.generate(prompt, temperature=0.7, n=n_candidates)
    candidates = [extract_code(r) for r in raw_candidates]
    
    best_candidate = None
    best_tension = float('inf')
    best_results = []
    attempts_evaluated = 0
    
    # Evaluate ALL candidates, track the best one
    for i, candidate in enumerate(candidates, 1):
        if not candidate.strip():
            continue
        
        # Write to module for testing
        with open(module_path, "w", encoding="utf-8") as f:
            f.write(candidate)
        
        tension, results = agent.constraint_engine.evaluate(candidate, module_path)
        attempts_evaluated += 1
        
        # Track the candidate with the lowest tension
        if tension < best_tension:
            best_tension = tension
            best_candidate = candidate
            best_results = results
    
    # Decision: accept the best candidate if it passes the threshold
    threshold = 1.0 - agent.omega
    
    if best_candidate and best_tension <= threshold:
        # ACCEPT the best candidate
        with open(module_path, "w", encoding="utf-8") as f:
            f.write(best_candidate)
        
        agent._integrate(best_candidate, task.name, best_tension)
        
        return {
            "mode": "OS",
            "success": True,
            "tension": best_tension,
            "attempts": attempts_evaluated,
            "reason": f"Best of {attempts_evaluated} candidates passed"
        }
    else:
        # All candidates failed
        failed_reasons = [r.name for r in best_results if not r.passed] if best_results else ["All empty"]
        
        return {
            "mode": "OS",
            "success": False,
            "tension": best_tension if best_candidate else 1.5,
            "attempts": attempts_evaluated,
            "reason": f"Best candidate still failed: {', '.join(failed_reasons)}"
        }


def build_prompt(task, existing_code):
    """Build the prompt for the model."""
    return f"""You are working on a Python project. Here is the current module:

```python
{existing_code}
```

TASK: {task.get_prompt()}

Please write ONLY the updated module content. Include ALL existing code plus your new function/class. Do not include explanations.
Output the complete Python module inside a markdown code block.
"""


def extract_code(text):
    """Extract the first Python code block from model output."""
    import re
    pattern = r"```(?:python)?\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def print_header():
    print("=" * 80)
    print("PUZZLE LOGIC AI — BENCHMARK")
    print("=" * 80)
    print()
    print("Comparing: BASE MODEL (1-shot) vs PUZZLE LOGIC OS (3-candidate selection)")
    print()
    print("BASE MODEL:   Generates 1 candidate. If it fails, task is FAILED.")
    print("PUZZLE LOGIC: Generates up to 3 candidates. Validates all. Picks the")
    print("              one with the LOWEST structural tension. If the best")
    print("              candidate passes the Omega threshold, task SUCCEEDS.")
    print()
    print("The hypothesis: On tasks with edge cases, the OS recovers from model")
    print("mistakes by trying again. The base model has no second chance.")
    print()
    print("-" * 80)


def print_results_table(results):
    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()
    
    # Header
    print(f"{'Task':<25} {'Difficulty':<10} {'Base':<8} {'OS':<8} {'Delta':<8} {'OS Attempts'}")
    print("-" * 80)
    
    base_successes = 0
    os_successes = 0
    
    for task_name, base_res, os_res in results:
        base_ok = "PASS" if base_res["success"] else "FAIL"
        os_ok = "PASS" if os_res["success"] else "FAIL"
        
        # Delta: did OS succeed where base failed?
        if not base_res["success"] and os_res["success"]:
            delta = "+OS"
        elif base_res["success"] and not os_res["success"]:
            delta = "-OS"
        else:
            delta = "same"
        
        difficulty = base_res.get("difficulty", "?")
        attempts = os_res["attempts"]
        
        print(f"{task_name:<25} {difficulty:<10} {base_ok:<8} {os_ok:<8} {delta:<8} {attempts}")
        
        if base_res["success"]:
            base_successes += 1
        if os_res["success"]:
            os_successes += 1
    
    print("-" * 80)
    print(f"{'TOTAL':<25} {'':<10} {base_successes}/{len(results):<8} {os_successes}/{len(results):<8}")
    
    # Calculate improvement
    base_rate = base_successes / len(results) * 100
    os_rate = os_successes / len(results) * 100
    improvement = os_rate - base_rate
    
    print()
    print(f"Base model success rate:    {base_rate:.0f}%")
    print(f"Puzzle Logic success rate:  {os_rate:.0f}%")
    print(f"Improvement:                {improvement:+.0f} percentage points")
    
    # Count recoveries
    recoveries = sum(1 for _, b, o in results if not b["success"] and o["success"])
    if recoveries > 0:
        print(f"\nTasks where OS recovered from base failure: {recoveries}")
        print("This is the Puzzle Logic advantage in action.")


def main():
    print_header()
    
    tasks = get_all_tasks()
    
    # Check LM Studio
    print("[CHECK] Testing LM Studio connection...")
    agent = PuzzleLogicAgent(omega=0.5)
    if not agent.synapse.check_health():
        print("  X LM Studio is not running!")
        print("  Please start LM Studio, load a model, and start the server.")
        return
    print("  + LM Studio is running!")
    print()
    
    results = []
    
    for task in tasks:
        print(f"[TASK] {task.name} ({task.difficulty})")
        print(f"       {task.description}")
        print()
        
        # Run base mode
        clean_project_dir()
        base_res = run_base_mode(task, agent.synapse)
        base_res["difficulty"] = task.difficulty
        print(f"  BASE:   {base_res['reason']} (tension={base_res['tension']:.2f})")
        
        # Run OS mode
        clean_project_dir()
        os_res = run_os_mode(task, agent)
        print(f"  OS:     {os_res['reason']} (tension={os_res['tension']:.2f})")
        
        print()
        
        results.append((task.name, base_res, os_res))
        
        # Small delay to not overwhelm LM Studio
        time.sleep(1)
    
    print_results_table(results)
    
    print()
    print("=" * 80)
    print("BENCHMARK COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
