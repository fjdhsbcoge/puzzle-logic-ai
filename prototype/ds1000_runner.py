"""
DS-1000 Runner with Error-Pattern Knowledge Graph
==================================================

Runs the DS-1000 data-science benchmark (1000 problems).
The Error-Pattern Graph learns from compiler feedback and accumulates
validated fix patterns across the entire run.

Key features for overnight runs:
  - INCREMENTAL SAVE: Error patterns are saved after every success
  - RESUME: Can continue from previous error_patterns.json
  - PROGRESS LOG: Writes summary every 50 problems to progress.log
  - DOMAIN COHERENCE: Data science tasks share common errors:
      * NameError: missing pandas/numpy imports
      * KeyError: wrong column names
      * TypeError: string vs numeric operations
      * AttributeError: DataFrame method typos

Usage:
    # Fresh start (recommended for controlled experiment)
    python ds1000_runner.py --model qwen2.5-coder-3b-instruct --limit 1000

    # Resume from previous run
    python ds1000_runner.py --model qwen2.5-coder-3b-instruct --limit 1000 --resume

    # Quick test
    python ds1000_runner.py --model qwen2.5-coder-3b-instruct --limit 50
"""

import json
import os
import sys
import tempfile
import subprocess
import argparse
import re
import time
import traceback
from typing import List, Dict, Any, Optional

from lmstudio_client import LMStudioClient
from error_pattern_kg import ErrorPatternGraph, extract_error_fingerprint
from mbpp_cg_runner import extract_code, infer_function_name, fix_function_name
from prompt_logger import PromptLogger


def load_ds1000() -> List[Dict]:
    """Load DS-1000 dataset from HuggingFace."""
    try:
        from datasets import load_dataset
        ds = load_dataset("xlangai/DS-1000", split="test")
        problems = []
        for i, item in enumerate(ds):
            problems.append({
                "task_id": f"DS1000/{i}",
                "text": item.get("prompt", item.get("text", "")),
                "test_list": [item.get("test", "")] if item.get("test") else [],
                "metadata": {
                    "library": item.get("lib", "unknown"),
                    "source": item.get("origin", "unknown"),
                }
            })
        return problems
    except Exception as e:
        print(f"[ERROR] Could not load DS-1000 from HuggingFace: {e}")
        print("Trying local file...")
        return load_ds1000_local()


def load_ds1000_local() -> List[Dict]:
    """Fallback: load from local ds1000.jsonl if available."""
    path = os.path.join(os.path.dirname(__file__), "ds1000.jsonl")
    if not os.path.exists(path):
        return []
    problems = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            item = json.loads(line)
            problems.append({
                "task_id": f"DS1000/{i}",
                "text": item.get("prompt", item.get("text", "")),
                "test_list": [item.get("test", "")] if item.get("test") else [],
            })
    return problems


def run_test(problem: Dict, completion: str) -> Dict:
    """Execute generated code + test in sandbox."""
    expected = infer_function_name(problem["test_list"])
    if expected:
        completion = fix_function_name(completion, expected)
    
    tests = "\n".join(problem["test_list"])
    # DS-1000 tests often need pandas/numpy/scipy
    imports = "import pandas as pd\nimport numpy as np\nimport scipy\nimport math\n\n"
    test_program = imports + completion + "\n\n" + tests + "\n"
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(test_program)
        temp_path = f.name
    
    try:
        result = subprocess.run([sys.executable, temp_path], capture_output=True, text=True, timeout=10)
        passed = result.returncode == 0
        error = result.stderr if not passed else None
        if error and len(error) > 500:
            error = error[:500] + "..."
        return {"passed": passed, "error": error}
    except subprocess.TimeoutExpired:
        return {"passed": False, "error": "Timeout (10s)"}
    except Exception as e:
        return {"passed": False, "error": str(e)}
    finally:
        os.unlink(temp_path)


def build_prompt(problem_text: str, error_toolbox: str = "") -> str:
    """Build prompt with optional error-pattern toolbox."""
    base = problem_text.strip()
    instruction = (
        "\n\nWrite Python code to solve this. "
        "Output only the complete solution inside a markdown code block."
    )
    if error_toolbox:
        return base + "\n\n" + error_toolbox + instruction
    return base + instruction


def solve_problem(problem: Dict, synapse: LMStudioClient,
                  epg: ErrorPatternGraph, n_candidates: int = 3,
                  debug: bool = False, max_tokens: int = 1024,
                  logger: Optional[PromptLogger] = None) -> Dict:
    """Solve one DS-1000 problem with error-pattern feedback."""
    task_id = problem["task_id"]
    problem_text = problem["text"]
    
    failure_history = []
    last_error = ""
    
    for attempt in range(1, n_candidates + 1):
        error_toolbox = ""
        trigger_error = ""
        if failure_history and last_error:
            error_toolbox = epg.get_fix_toolbox(last_error, top_k=3)
            trigger_error = last_error
            if debug and error_toolbox:
                n_patterns = error_toolbox.count("Pattern ")
                print(f"    [Attempt {attempt}] Retrieved {n_patterns} patterns")
        
        prompt = build_prompt(problem_text, error_toolbox)
        if failure_history and not error_toolbox:
            prompt += "\n\nNOTE: Previous attempt failed. Try a different approach."
        
        used_toolbox = bool(error_toolbox)
        
        try:
            raw = synapse.generate(prompt=prompt, temperature=0.0, max_tokens=max_tokens, n=1)
            raw_text = raw[0] if raw and raw[0] else ""
        except Exception as e:
            raw_text = ""
            if debug:
                print(f"    [Attempt {attempt}] Generation error: {e}")
        
        completion = extract_code(raw_text)
        
        if logger:
            test_result_early = run_test(problem, completion) if completion else {"passed": False, "error": "extraction"}
            logger.log(
                task_id=task_id, attempt=attempt,
                result="PASS" if test_result_early["passed"] else "FAIL",
                prompt=prompt, raw_response=raw_text,
                extracted_code=completion or "(extraction failed)",
                test_passed=test_result_early["passed"],
                test_error=test_result_early.get("error"),
                toolbox_used=used_toolbox
            )
        
        if not raw_text.strip():
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
            if last_error:
                epg.record_fix(last_error, problem_text)
            return {
                "task_id": task_id, "passed": True,
                "attempts": attempt, "used_toolbox": used_toolbox,
                "error": None
            }
        else:
            error_text = test_result.get("error", "unknown")
            failure_history.append(error_text)
            last_error = error_text
            epg.record_error(error_text, problem_text, completion)
            if debug:
                err_type, _ = extract_error_fingerprint(error_text)
                print(f"    [Attempt {attempt}] FAIL: [{err_type}] {error_text[:80]}")
    
    return {
        "task_id": task_id, "passed": False,
        "attempts": n_candidates, "used_toolbox": any(failure_history),
        "error": failure_history[-1] if failure_history else "unknown"
    }


def run_benchmark(problems: List[Dict], synapse: LMStudioClient,
                  epg: ErrorPatternGraph, n_candidates: int = 3,
                  debug: bool = False, max_tokens: int = 1024,
                  logger: Optional[PromptLogger] = None,
                  output_path: str = "ds1000_results.json",
                  progress_path: str = "ds1000_progress.log") -> List[Dict]:
    """Run full DS-1000 benchmark with incremental saves."""
    results = []
    total = len(problems)
    
    print(f"\n[DS-1000] Running {total} problems...")
    print(f"Error patterns file: {epg.storage_path}")
    print(f"Results file: {output_path}")
    print("-" * 60)
    
    start_time = time.time()
    last_save = time.time()
    
    for i, problem in enumerate(problems, 1):
        task_id = problem["task_id"]
        n_patterns = len(epg.patterns)
        
        print(f"\n[{i}/{total}] {task_id} | Patterns: {n_patterns}")
        
        result = solve_problem(problem, synapse, epg, n_candidates=n_candidates,
                               debug=debug, max_tokens=max_tokens, logger=logger)
        results.append(result)
        
        status = "PASS" if result["passed"] else "FAIL"
        toolbox_mark = " [T]" if result.get("used_toolbox") else ""
        print(f"  {status}{toolbox_mark} in {result['attempts']} attempts")
        
        # Incremental save every 10 problems AND every 5 minutes
        now = time.time()
        if i % 10 == 0 or (now - last_save) > 300:
            epg._save()
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump({"results": results, "patterns": len(epg.patterns)}, f, default=str)
            last_save = now
            
            # Write progress summary
            passed = sum(1 for r in results if r["passed"])
            rate = passed / i * 100
            elapsed = now - start_time
            eta = (elapsed / i) * (total - i) if i > 0 else 0
            
            progress_line = (
                f"[{time.strftime('%H:%M:%S')}] {i}/{total} | "
                f"{passed} passed ({rate:.1f}%) | "
                f"{len(epg.patterns)} patterns | "
                f"ETA: {eta/60:.0f}m\n"
            )
            with open(progress_path, "a", encoding="utf-8") as f:
                f.write(progress_line)
            print(f"  [SAVED] Progress logged")
    
    # Final save
    epg._save()
    elapsed = time.time() - start_time
    passed = sum(1 for r in results if r["passed"])
    rate = passed / total * 100
    
    print("\n" + "=" * 60)
    print(f"FINAL: {passed}/{total} passed ({rate:.1f}%)")
    print(f"Error patterns learned: {len(epg.patterns)}")
    print(f"Total time: {elapsed/60:.1f} minutes")
    print("=" * 60)
    
    return results


def main():
    parser = argparse.ArgumentParser(description="DS-1000 with Error-Pattern Knowledge Graph")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--output", type=str, default="ds1000_results.json")
    parser.add_argument("--log-prompts", type=str, default=None)
    parser.add_argument("--resume", action="store_true",
                        help="Continue from existing error_patterns file")
    args = parser.parse_args()
    
    print("=" * 70)
    print("DS-1000 with ERROR-PATTERN KNOWLEDGE GRAPH")
    print("=" * 70)
    print(f"Target: {args.limit} data-science problems")
    print("This will take several hours. Progress is saved every 10 problems.")
    print("=" * 70)
    
    # Load problems
    problems = load_ds1000()
    if not problems:
        print("Could not load DS-1000. Please download it first:")
        print("  https://github.com/xlangai/DS-1000")
        sys.exit(1)
    
    print(f"\nLoaded {len(problems)} problems from DS-1000")
    problems = problems[:args.limit]
    
    # Setup model
    model_id = args.model
    if not model_id:
        try:
            import requests
            r = requests.get("http://localhost:1234/v1/models", timeout=5)
            model_id = r.json()["data"][0]["id"]
            print(f"Auto-detected: {model_id}")
        except Exception:
            print("Use --model to specify model ID")
            sys.exit(1)
    
    synapse = LMStudioClient(model=model_id, timeout=args.timeout)
    if not synapse.check_health():
        print("LM Studio not running!")
        sys.exit(1)
    print(f"LM Studio OK")
    
    # Error-Pattern Graph (resume or fresh)
    epg_path = f"error_patterns_{model_id.replace('/', '_')}_ds1000.json"
    if not args.resume and os.path.exists(epg_path):
        print(f"\nRemoving old patterns file: {epg_path}")
        os.remove(epg_path)
    
    epg = ErrorPatternGraph(storage_path=epg_path)
    print(f"Error patterns: {len(epg.patterns)} (file: {epg_path})")
    
    # Logger
    logger = PromptLogger(args.log_prompts) if args.log_prompts else None
    
    # Run
    results = run_benchmark(
        problems, synapse, epg, n_candidates=args.k,
        debug=args.debug, max_tokens=args.max_tokens,
        logger=logger, output_path=args.output
    )
    
    # Final stats
    stats = epg.get_stats()
    print(f"\n[STATS] {json.dumps(stats, indent=2)}")
    
    print(f"\nResults: {args.output}")
    print(f"Patterns: {epg_path}")
    if logger:
        print(f"Log: {logger.path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
