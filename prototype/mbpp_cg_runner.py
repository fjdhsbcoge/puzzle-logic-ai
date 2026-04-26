"""
MBPP Runner with Contract Graph Learning
========================================

The Contract Graph starts EMPTY. As the model solves problems,
it extracts and stores validated contracts. Later problems can
retrieve relevant contracts as guidance.

This demonstrates genuine compounding expertise:
  Problem 1: solved from scratch -> contract learned
  Problem 2: solved with hint from Problem 1's contract
  Problem 50: solved with 30+ learned contracts in graph
  
The graph discovers Python's structure empirically — not from
human specification, but from observing what worked.

Usage:
    python mbpp_cg_runner.py --limit 50     # Quick test
    python mbpp_cg_runner.py               # Full 974 problems (overnight)
"""

import json
import os
import sys
import tempfile
import subprocess
import argparse
import re
from typing import List, Dict, Any

from lmstudio_client import LMStudioClient
from contract_graph import ContractGraph


# Try to load MBPP from HuggingFace datasets, fallback to local file
MBPP_PATH = os.path.join(os.path.dirname(__file__), "mbpp.jsonl")


def load_mbpp() -> List[Dict[str, Any]]:
    """Load MBPP dataset. Try HuggingFace first, then local JSONL."""
    problems = []
    
    # Try local file first
    if os.path.exists(MBPP_PATH):
        with open(MBPP_PATH, "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                problems.append({
                    "task_id": f"MBPP/{data.get('task_id', len(problems))}",
                    "text": data.get("text", ""),
                    "code": data.get("code", ""),
                    "test_list": data.get("test_list", []),
                    "test_list_2": data.get("test_list_2", []),
                    "canonical_solution": data.get("canonical_solution", ""),
                })
        return problems
    
    # Try HuggingFace datasets
    try:
        from datasets import load_dataset
        ds = load_dataset("mbpp", split="train")
        for i, item in enumerate(ds):
            problems.append({
                "task_id": f"MBPP/{i}",
                "text": item.get("text", ""),
                "code": item.get("code", ""),
                "test_list": item.get("test_list", []),
                "test_list_2": item.get("test_list_2", []),
                "canonical_solution": item.get("canonical_solution", ""),
            })
        # Save to local file for future runs
        with open(MBPP_PATH, "w", encoding="utf-8") as f:
            for p in problems:
                f.write(json.dumps(p) + "\n")
        return problems
    except Exception as e:
        print(f"Could not load MBPP: {e}")
        print("Install with: pip install datasets")
        print("Or download manually from https://huggingface.co/datasets/mbpp")
        sys.exit(1)


def extract_code(text: str) -> str:
    """Extract code from model response.
    
    R1 reasoning models output reasoning first, then code at the END.
    We search backward from the end of the text to find the actual code.
    """
    if not text:
        return ""
    
    # Strategy 1: Find the LAST fenced code block (R1 puts code at end)
    # Use finditer to get all matches, then take the last one
    matches = list(re.finditer(r"```(?:python)?\n(.*?)```", text, re.DOTALL))
    if matches:
        return matches[-1].group(1).strip()
    
    # Strategy 2: Find the LAST occurrence of "def " and extract from there
    # This handles cases where there's no markdown fence
    last_def = text.rfind("def ")
    if last_def != -1:
        # Extract from def to end, then clean up trailing text
        candidate = text[last_def:]
        # Stop at double newline followed by non-indented text (explanation)
        lines = candidate.split("\n")
        code_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue  # Skip blank lines in code
            code_lines.append(line)
            # Heuristic: if we see a line that looks like explanation (starts with capital, not code)
            if stripped[0].isupper() and not stripped.startswith(("def ", "return", "if ", "for ", "while ", "try", "with ", "class ", "import ", "from ")):
                # Check if next line is also non-code
                break
        if code_lines:
            return "\n".join(code_lines).strip()
    
    # Strategy 3: Look for any line that starts with def/import/class
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("def ", "import ", "from ", "class ")):
            # Extract from here to end
            idx = text.find(line)
            return text[idx:].strip()
    
    return ""


def run_test(problem: Dict, completion: str) -> Dict:
    """Run MBPP tests on a completion."""
    # Build test program
    tests = "\n".join(problem["test_list"])
    test_program = completion + "\n\n" + tests + "\n"
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(test_program)
        temp_path = f.name
    
    try:
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


def build_prompt(problem: Dict, contract_hint: str = "") -> str:
    """Build prompt with optional contract graph hint."""
    base = problem["text"]
    instruction = (
        "\n\nWrite a Python function to solve this. "
        "Put the complete function inside a markdown code block at the very end of your response. "
        "Do NOT write explanation after the code block."
    )
    if contract_hint:
        return contract_hint + "\n\nNow solve this problem:\n\n" + base + instruction
    return base + instruction


def solve_problem(problem: Dict, synapse: LMStudioClient, cg: ContractGraph,
                  n_candidates: int = 3, learn: bool = True, debug: bool = False,
                  max_tokens: int = 2048) -> Dict:
    """
    Solve a single problem with optional Contract Graph learning.
    
    If learn=True and solution passes: extract contract, add to graph.
    """
    task_id = problem["task_id"]
    
    # Get contract hint from graph
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
        
        if debug:
            print(f"    [Attempt {attempt}] Raw response length: {len(raw[0]) if raw else 0}")
            if raw and raw[0].strip():
                preview = raw[0][:150].replace('\n', '\\n')
                end_preview = raw[0][-300:].replace('\n', '\\n')
                print(f"    [Attempt {attempt}] Start: {preview}...")
                print(f"    [Attempt {attempt}] End: ...{end_preview}")
        
        if not raw or not raw[0].strip():
            failure_history.append("empty")
            if debug:
                print(f"    [Attempt {attempt}] FAIL: empty response")
            continue
        
        completion = extract_code(raw[0])
        if not completion:
            failure_history.append("extraction")
            if debug:
                print(f"    [Attempt {attempt}] FAIL: code extraction failed")
                print(f"    Contains 'def ': {'def ' in raw[0]}")
                print(f"    Contains '```': {'```' in raw[0]}")
            continue
        
        if debug:
            code_preview = completion[:200].replace('\n', '\\n')
            print(f"    [Attempt {attempt}] Extracted ({len(completion)} chars): {code_preview}...")
            if "def " in completion:
                print(f"    [Attempt {attempt}] OK: contains 'def '")
        
        best_code = completion
        test_result = run_test(problem, completion)
        
        if debug and not test_result["passed"]:
            err = test_result.get("error", "unknown")
            err_preview = err[:200].replace('\n', ' ') if err else ""
            print(f"    [Attempt {attempt}] TEST ERROR: {err_preview}")
        
        if test_result["passed"]:
            # SUCCESS! Learn from this solution
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
    
    if debug:
        print(f"    All {n_candidates} attempts failed. History: {failure_history}")
    
    return {
        "task_id": task_id,
        "passed": False,
        "attempts": n_candidates,
        "used_contract": bool(contract_hint),
        "error": failure_history[-1] if failure_history else "unknown"
    }


def run_benchmark(problems: List[Dict], synapse: LMStudioClient,
                  cg: ContractGraph, n_candidates: int = 3, debug: bool = False,
                  max_tokens: int = 2048) -> List[Dict]:
    """Run full benchmark with Contract Graph learning."""
    results = []
    total = len(problems)
    
    print(f"\n[RUNNING] MBPP with Contract Graph - {total} problems...")
    print("-" * 60)
    
    if debug and problems:
        p0 = problems[0]
        print("\n[DEBUG] First problem details:")
        print(f"  Text: {p0['text'][:200]}...")
        print(f"  Tests: {p0['test_list']}")
        print()
    
    for i, problem in enumerate(problems, 1):
        task_id = problem["task_id"]
        
        # Show progress
        n_contracts = len(cg.nodes)
        print(f"\n[{i}/{total}] {task_id} | Graph has {n_contracts} contracts")
        
        result = solve_problem(problem, synapse, cg, n_candidates=n_candidates, learn=True, debug=debug, max_tokens=max_tokens)
        results.append(result)
        
        status = "PASS" if result["passed"] else "FAIL"
        cg_indicator = " (CG)" if result["used_contract"] else ""
        print(f"  Result: {status}{cg_indicator} in {result['attempts']} attempt(s)")
    
    return results


def print_sliding_window(results: List[Dict], window: int = 50):
    """
    Print pass rate in sliding windows to show compounding.
    """
    print("\n" + "=" * 70)
    print("SLIDING WINDOW ANALYSIS (Compounding Effect)")
    print("=" * 70)
    print(f"\n{'Window':<20} {'Problems':<12} {'Passed':<12} {'Rate':<12} {'Avg Attempts'}")
    print("-" * 70)
    
    for start in range(0, len(results), window):
        end = min(start + window, len(results))
        window_results = results[start:end]
        
        passed = sum(1 for r in window_results if r["passed"])
        n = len(window_results)
        rate = passed / n * 100
        avg_attempts = sum(r["attempts"] for r in window_results) / n
        
        print(f"Problems {start}-{end-1:<7} {n:<12} {passed}/{n:<10} {rate:.1f}%{'':<5} {avg_attempts:.1f}")
    
    # Overall
    total_passed = sum(1 for r in results if r["passed"])
    total = len(results)
    overall_rate = total_passed / total * 100
    overall_avg = sum(r["attempts"] for r in results) / total
    
    print("-" * 70)
    print(f"{'OVERALL':<20} {total:<12} {total_passed}/{total:<10} {overall_rate:.1f}%{'':<5} {overall_avg:.1f}")
    print("=" * 70)
    
    # Show first vs last window comparison
    if len(results) >= window * 2:
        first_pass = sum(1 for r in results[:window] if r["passed"]) / window * 100
        last_pass = sum(1 for r in results[-window:] if r["passed"]) / window * 100
        print(f"\nFirst {window} problems: {first_pass:.1f}%")
        print(f"Last {window} problems:  {last_pass:.1f}%")
        print(f"Compounding: {last_pass - first_pass:+.1f} percentage points")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit to first N problems (for testing)")
    parser.add_argument("--k", type=int, default=3,
                        help="Number of attempts per problem")
    parser.add_argument("--output", type=str, default="mbpp_cg_results.json")
    parser.add_argument("--debug", action="store_true",
                        help="Print detailed per-attempt diagnostics")
    parser.add_argument("--model", type=str, default="deepseek-r1-distill-qwen-7b",
                        help="LM Studio model ID to use")
    parser.add_argument("--max-tokens", type=int, default=2048,
                        help="Max tokens per generation (R1 needs 2048+ for reasoning+code)")
    parser.add_argument("--timeout", type=int, default=600,
                        help="HTTP timeout in seconds (default 600 = 10 minutes)")
    args = parser.parse_args()
    
    print("=" * 70)
    print("PUZZLE LOGIC AI - CONTRACT GRAPH LEARNING ON MBPP")
    print("=" * 70)
    print()
    print("The Contract Graph starts EMPTY.")
    print("Each successful solution adds a learned contract.")
    print("Later problems use accumulated contracts as hints.")
    print()
    print("This demonstrates: the agent DISCOVERS Python's structure")
    print("through experience, not from human specification.")
    print("-" * 70)
    
    # Load problems
    problems = load_mbpp()
    print(f"\nLoaded {len(problems)} problems from MBPP")
    
    if args.limit:
        problems = problems[:args.limit]
        print(f"Limited to first {len(problems)} problems")
    
    # Setup
    synapse = LMStudioClient(model=args.model, timeout=args.timeout)
    print(f"\n[CHECK] LM Studio (model={args.model}, timeout={args.timeout}s)...")
    if not synapse.check_health():
        print("  NOT RUNNING")
        sys.exit(1)
    print("  OK")
    
    # Fresh Contract Graph
    cg_path = "contract_graph.json"
    if os.path.exists(cg_path):
        os.remove(cg_path)
    cg = ContractGraph(storage_path=cg_path)
    print(f"\n[INIT] Contract Graph is empty: {len(cg.nodes)} contracts")
    
    # Run benchmark
    results = run_benchmark(problems, synapse, cg, n_candidates=args.k, debug=args.debug, max_tokens=args.max_tokens)
    
    # Analysis
    print_sliding_window(results, window=50)
    
    # Show final graph
    print(f"\n[FINAL] Contract Graph learned {len(cg.nodes)} contracts")
    cg.print_graph()
    
    stats = cg.get_stats()
    print(f"\n[STATS] Unique patterns: {stats['n_unique_patterns']}")
    print(f"        Top patterns: {list(stats['top_patterns'].keys())[:5]}")
    print(f"        Top guards: {list(stats['top_preconditions'].keys())[:5]}")
    
    # Save results
    data = {
        "benchmark": "MBPP",
        "n_problems": len(problems),
        "n_contracts_learned": len(cg.nodes),
        "overall_pass_rate": sum(1 for r in results if r["passed"]) / len(results),
        "contract_stats": stats,
        "results": results
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"\nResults saved to: {args.output}")
    
    # Cleanup
    if os.path.exists(cg_path):
        os.remove(cg_path)
    
    print("\nDone.")


if __name__ == "__main__":
    main()
