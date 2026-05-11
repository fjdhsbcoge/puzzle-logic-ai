"""
MBPP Three-Way Benchmark Runner v2.5 — CONCURRENT
===================================================

Fixes the 5% GPU utilization problem by running Baseline + Basic modes
concurrently across a batch of problems. Advanced stays sequential (needs KG state).

  1. BASELINE    — 3 clean attempts, no error information
  2. BASIC V2    — 3 attempts; raw error + strategy rotation on retry
  3. ADVANCED V2 — 3 attempts; high-confidence toolbox (>= 0.5) on attempts 2 AND 3

Architecture:
  For each BATCH of N problems:
    Phase 1 (concurrent, ThreadPool): Run Baseline + Basic for all N problems
    Phase 2 (sequential, main thread): Run Advanced for all N problems (updates KG)

Usage:
    python mbpp_three_way_runner_v25.py --model qwen2.5-coder-7b-instruct --limit 20 --workers 4
    python mbpp_three_way_runner_v25.py --model qwen2.5-coder-3b-instruct --limit 974 --workers 4
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# ── Import v2.5 engine ──────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_SCRIPT_DIR)
_PRODUCT_DIR = os.path.join(_PARENT_DIR, "product")
sys.path.insert(0, _PRODUCT_DIR)
sys.path.insert(1, _SCRIPT_DIR)

from puzzle_logic_agent import (
    execute_code, extract_code, extract_error_fingerprint,
    CoherentKnowledgeGraph, StrategyExtractor, AttemptTracker,
    LMStudioClient, green, red, yellow, bold, cyan,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MBPP_PATH  = os.path.join(_SCRIPT_DIR, "mbpp.jsonl")
MBPP_URL   = ("https://raw.githubusercontent.com/google-research/"
              "google-research/master/mbpp/mbpp.jsonl")
SAVE_EVERY = 10
TIMEOUT    = 5


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

def download_mbpp():
    if os.path.exists(MBPP_PATH):
        return
    print("  Downloading MBPP dataset (one-time)...")
    try:
        urllib.request.urlretrieve(MBPP_URL, MBPP_PATH)
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(1)


def load_mbpp(path: str, limit: int = None) -> List[Dict]:
    problems = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            try:
                p = json.loads(line)
                all_tests = list(p.get("test_list", []))
                challenge = p.get("challenge_test_list", [])
                if challenge:
                    all_tests.extend(challenge)
                problems.append({
                    "task_id":         f"MBPP/{p.get('task_id', i)}",
                    "text":            p.get("text", ""),
                    "code":            p.get("code", ""),
                    "test_list":       all_tests,
                    "test_setup_code": p.get("test_setup_code", ""),
                })
            except Exception:
                continue
    return problems


# ---------------------------------------------------------------------------
# Function name helpers
# ---------------------------------------------------------------------------

def infer_function_name(canonical_code: str, test_list: List[str]) -> str:
    if canonical_code:
        m = re.search(r"def\s+(\w+)\s*\(", canonical_code)
        if m:
            return m.group(1)
    for test in test_list:
        m = re.search(r"(\w+)\s*\(", test)
        if m:
            return m.group(1)
    return ""


def extract_generated_name(code: str) -> str:
    m = re.search(r"def\s+(\w+)\s*\(", code)
    return m.group(1) if m else ""


def fix_function_name(code: str, expected: str) -> str:
    actual = extract_generated_name(code)
    if not actual or actual == expected:
        return code
    code = re.sub(rf"\bdef\s+{re.escape(actual)}\s*\(", f"def {expected}(", code, count=1)
    code = re.sub(rf"\b{re.escape(actual)}\s*\(", f"{expected}(", code)
    return code


def build_test_program(problem: Dict, completion: str) -> str:
    setup = problem.get("test_setup_code", "")
    tests = problem.get("test_list", [])
    pieces = []
    if setup:
        pieces.append(setup)
    pieces.append(completion)
    pieces.extend(tests)
    return "\n".join(pieces) + "\n"


# ---------------------------------------------------------------------------
# Core: three modes (all using direct LLM calls)
# ---------------------------------------------------------------------------

def run_baseline(problem: Dict, llm: LMStudioClient,
                 n_attempts: int = 3, debug: bool = False) -> Dict:
    """Mode 1: Clean attempts, NO error info on retry."""
    expected = infer_function_name(problem["code"], problem["test_list"])
    prompt = (
        f"{problem['text']}\n\n"
        f"Write a Python function{f' named {expected!r}' if expected else ''} that solves this. "
        f"Output only the function code in a markdown code block."
    )

    for attempt in range(1, n_attempts + 1):
        raw_list = llm.generate(prompt=prompt, temperature=0.0,
                              max_tokens=1024, n=1)
        raw  = raw_list[0] if raw_list else ""
        code = extract_code(raw)
        if not code:
            continue

        if expected:
            gen = extract_generated_name(code)
            if gen and gen != expected:
                code = fix_function_name(code, expected)

        result = execute_code(build_test_program(problem, code), timeout=TIMEOUT)
        if result["passed"]:
            return {"passed": True, "attempts": attempt, "code": code, "error": None}

    return {"passed": False, "attempts": n_attempts,
            "code": code, "error": result.get("error", "failed")}


def run_basic_v2(problem: Dict, llm: LMStudioClient,
                 n_attempts: int = 3, debug: bool = False) -> Dict:
    """Mode 2: BASIC V2 — raw error + strategy rotation."""
    expected = infer_function_name(problem["code"], problem["test_list"])
    base_prompt = (
        f"{problem['text']}\n\n"
        f"Write a Python function{f' named {expected!r}' if expected else ''} that solves this. "
        f"Output only the function code in a markdown code block."
    )

    tracker = AttemptTracker()
    last_error = ""
    last_code = ""
    used_error = False

    for attempt in range(1, n_attempts + 1):
        full_prompt = base_prompt
        if last_error:
            rotation = tracker.get_rotation_hint()
            full_prompt = (
                base_prompt + "\n\n"
                f"[Previous attempt FAILED with this error:]\n"
                f"```\n{last_error}\n```\n"
                f"Fix the code based on this error message.{rotation}"
            )
            used_error = True

        raw_list = llm.generate(prompt=full_prompt, temperature=0.0,
                                max_tokens=1024, n=1)
        raw  = raw_list[0] if raw_list else ""
        code = extract_code(raw)
        if not code:
            last_error = "extraction failed"
            continue

        if expected:
            gen = extract_generated_name(code)
            if gen and gen != expected:
                code = fix_function_name(code, expected)

        result = execute_code(build_test_program(problem, code), timeout=TIMEOUT)
        if result["passed"]:
            return {"passed": True, "attempts": attempt, "code": code,
                    "error": None, "used_error_info": used_error}

        last_error = result.get("error", "unknown")
        if last_code:
            tracker.record(extract_error_fingerprint(last_error)[0], last_code, code, False)
        last_code = code

    return {"passed": False, "attempts": n_attempts, "code": code,
            "error": last_error, "used_error_info": used_error}


def run_advanced_v2(problem: Dict, llm: LMStudioClient, kg: CoherentKnowledgeGraph,
                    n_attempts: int = 3, debug: bool = False) -> Dict:
    """Mode 3: ADVANCED V2 — high-confidence toolbox only (>= 0.5)."""
    expected = infer_function_name(problem["code"], problem["test_list"])
    base_prompt = (
        f"{problem['text']}\n\n"
        f"Write a Python function{f' named {expected!r}' if expected else ''} that solves this. "
        f"Output only the function code in a markdown code block."
    )

    last_error = ""
    last_code = ""
    used_toolbox = False
    tracker = AttemptTracker()

    for attempt in range(1, n_attempts + 1):
        full_prompt = base_prompt
        shown_patterns = []
        if last_error:
            if attempt == 1:
                pass
            elif attempt == 2:
                toolbox_text, shown_patterns = kg.get_coherent_toolbox(
                    last_error, top_k=3, min_confidence=0.5, max_confidence=1.0
                )
                if toolbox_text:
                    full_prompt = base_prompt + "\n\n" + toolbox_text + "\n"
                    used_toolbox = True
                else:
                    rotation = tracker.get_rotation_hint()
                    full_prompt = (
                        base_prompt + "\n\n"
                        f"[Previous attempt FAILED with this error:]\n"
                        f"```\n{last_error}\n```\n"
                        f"Fix the code based on this error message.{rotation}"
                    )
            else:  # attempt >= 3
                toolbox_text, shown_patterns = kg.get_coherent_toolbox(
                    last_error, top_k=3, min_confidence=0.5, max_confidence=1.0
                )
                if toolbox_text:
                    full_prompt = base_prompt + "\n\n" + toolbox_text + "\n"
                    used_toolbox = True
                else:
                    rotation = tracker.get_rotation_hint()
                    full_prompt = (
                        base_prompt + "\n\n"
                        f"[Previous attempt FAILED with this error:]\n"
                        f"```\n{last_error}\n```\n"
                        f"Fix the code based on this error message.{rotation}"
                    )

        raw_list = llm.generate(prompt=full_prompt, temperature=0.0,
                                max_tokens=1024, n=1)
        raw  = raw_list[0] if raw_list else ""
        code = extract_code(raw)
        if not code:
            last_error = "extraction failed"
            kg.record_error("extraction failed")
            continue

        if expected:
            gen = extract_generated_name(code)
            if gen and gen != expected:
                code = fix_function_name(code, expected)

        result = execute_code(build_test_program(problem, code), timeout=TIMEOUT)
        if result["passed"]:
            if last_error:
                kg.record_fix(last_error, failing_code=last_code, fixed_code=code)
            return {"passed": True, "attempts": attempt, "code": code,
                    "error": None, "used_toolbox": used_toolbox}

        error_text = result.get("error", "unknown")
        kg.record_error(error_text, context=base_prompt[:200], code=code)
        if used_toolbox and shown_patterns:
            kg.record_toolbox_failure(shown_patterns)
        if last_code:
            tracker.record(extract_error_fingerprint(error_text)[0], last_code, code, False)
        last_error = error_text
        last_code = code

    return {"passed": False, "attempts": n_attempts, "code": code,
            "error": last_error, "used_toolbox": used_toolbox}


# ---------------------------------------------------------------------------
# Concurrent runner
# ---------------------------------------------------------------------------

def run_problem_batch(batch: List[Dict], llm: LMStudioClient,
                      n_attempts: int, debug: bool) -> List[Dict]:
    """Run Baseline + Basic for a batch of problems concurrently.
    Returns list of dicts: [{baseline, basic, advanced_placeholder, task_id}]."""
    
    results = []
    kg_lock = threading.Lock()
    
    def run_both(problem):
        """Run baseline + basic for one problem."""
        r0 = run_baseline(problem, llm, n_attempts=n_attempts, debug=debug)
        r1 = run_basic_v2(problem, llm, n_attempts=n_attempts, debug=debug)
        return {
            "task_id": problem["task_id"],
            "baseline": r0,
            "basic": r1,
            "problem": problem,
        }
    
    # Phase 1: Run Baseline + Basic concurrently for entire batch
    with ThreadPoolExecutor(max_workers=len(batch)) as executor:
        futures = {executor.submit(run_both, p): i for i, p in enumerate(batch)}
        for future in as_completed(futures):
            i = futures[future]
            result = future.result()
            results.append((i, result))
    
    # Sort by original index
    results.sort(key=lambda x: x[0])
    return [r for _, r in results]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MBPP Three-Way Benchmark v2.5 Concurrent")
    parser.add_argument("--model",     type=str,  default=None)
    parser.add_argument("--limit",     type=int,  default=300)
    parser.add_argument("--attempts",  type=int,  default=3)
    parser.add_argument("--output",    type=str,  default=None)
    parser.add_argument("--resume",    type=str,  default=None)
    parser.add_argument("--debug",     action="store_true")
    parser.add_argument("--knowledge", type=str,  default=None)
    parser.add_argument("--workers",   type=int,  default=4,
                        help="Number of concurrent problems for Baseline+Basic (default: 4)")
    args = parser.parse_args()

    # ── Per-run knowledge graph filename ──
    if args.knowledge:
        kg_path = args.knowledge
    else:
        kg_path = f"puzzle_logic_knowledge_{time.strftime('%Y%m%d_%H%M%S')}.json"

    print(bold("=" * 70))
    print(bold("  MBPP Three-Way Benchmark — v2.5 CONCURRENT"))
    print(bold("  Baseline | Basic V2 | Advanced V2 (Omega + λ)"))
    print(bold(f"  Concurrent workers: {args.workers} (Baseline + Basic parallel)"))
    print(bold("  Advanced sequential — KG state preserved"))
    print(bold("=" * 70))

    download_mbpp()

    # ── Detect model ──
    import requests
    try:
        r = requests.get("http://localhost:1234/v1/models", timeout=5)
        detected_model = r.json()["data"][0]["id"]
        model = args.model or detected_model
        print(f"LM Studio detected: {bold(model)}")
    except Exception:
        model = args.model
        if not model:
            print(red("No model specified and LM Studio not detected."))
            sys.exit(1)
        print(f"Using model: {bold(model)}")

    # ── Initialize ──
    llm = LMStudioClient(model=model)
    kg  = CoherentKnowledgeGraph(storage_path=kg_path)
    print(f"Knowledge graph: {len(kg.patterns)} existing patterns | Omega={kg.omega}")
    print(bold("=" * 70))

    # ── Load problems ──
    if args.resume and os.path.exists(args.resume):
        print(f"Resuming from {args.resume}...")
        with open(args.resume, "r", encoding="utf-8") as f:
            saved = json.load(f)
        baseline_results = saved["baseline_results"]
        basic_results    = saved["basic_results"]
        advanced_results = saved["advanced_results"]
        start_idx        = len(baseline_results)
        problems         = load_mbpp(MBPP_PATH, limit=args.limit)
        problems         = problems[start_idx:]
        print(f"  Resuming at problem {start_idx + 1}, {len(problems)} remaining")
    else:
        baseline_results = []
        basic_results    = []
        advanced_results = []
        start_idx        = 0
        problems         = load_mbpp(MBPP_PATH, limit=args.limit)

    def save():
        out = args.output or f"mbpp_three_way_{time.strftime('%Y%m%d_%H%M%S')}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump({
                "model": model,
                "n_problems": start_idx + len(baseline_results),
                "timestamp": time.strftime("%Y%m%d_%H%M%S"),
                "omega": kg.omega,
                "knowledge_graph": kg_path,
                "baseline_results": baseline_results,
                "basic_results":    basic_results,
                "advanced_results": advanced_results,
                "baseline_passed":  sum(1 for r in baseline_results if r["passed"]),
                "basic_passed":     sum(1 for r in basic_results    if r["passed"]),
                "advanced_passed":  sum(1 for r in advanced_results if r["passed"]),
            }, f, indent=2)
        return out

    # ── Run benchmark (concurrent batch mode) ──
    t0 = time.time()
    batch_size = args.workers
    
    for batch_start in range(0, len(problems), batch_size):
        batch = problems[batch_start:batch_start + batch_size]
        global_start = start_idx + batch_start
        
        print(f"\n{cyan(f'>>> BATCH [{batch_start//batch_size + 1}]')} "
              f"problems {global_start + 1}-{global_start + len(batch)}")

        # Phase 1: Baseline + Basic concurrently
        t1 = time.time()
        batch_results = run_problem_batch(batch, llm, args.attempts, args.debug)
        t_phase1 = time.time() - t1
        
        # Phase 2: Advanced sequentially (needs KG state)
        t2 = time.time()
        for i, result in enumerate(batch_results):
            problem = result["problem"]
            pid = problem["task_id"]
            global_idx = global_start + i
            
            r0 = result["baseline"]
            r1 = result["basic"]
            
            # Append baseline + basic results
            baseline_results.append({**r0, "task_id": pid})
            basic_results.append({**r1, "task_id": pid})
            
            # Run advanced (sequential — modifies KG)
            r2 = run_advanced_v2(problem, llm, kg, n_attempts=args.attempts, debug=args.debug)
            advanced_results.append({**r2, "task_id": pid})
            
            # Print summary
            status0 = green("PASS") if r0["passed"] else red("FAIL")
            status1 = green("PASS") if r1["passed"] else red("FAIL")
            status2 = green("PASS") if r2["passed"] else red("FAIL")
            err = "+err" if r1.get("used_error_info") else "    "
            tb = "toolbox" if r2.get("used_toolbox") else "clean"
            
            b_pass  = sum(1 for r in baseline_results if r["passed"])
            ba_pass = sum(1 for r in basic_results    if r["passed"])
            a_pass  = sum(1 for r in advanced_results if r["passed"])
            n_done  = len(baseline_results)
            
            print(f"  [{global_idx + 1}] {bold(pid[:10])}: "
                  f"Base={status0}({r0['attempts']}) "
                  f"Basic={status1}({r1['attempts']}){err} "
                  f"Adv={status2}({r2['attempts']}){tb} | "
                  f"B={b_pass}/{n_done} V2={ba_pass}/{n_done} Adv={a_pass}/{n_done}")
        
        t_phase2 = time.time() - t2
        print(f"  Batch time: Phase1(Baseline+Basic concurrent)={t_phase1:.1f}s, "
              f"Phase2(Advanced sequential)={t_phase2:.1f}s")
        
        # Save periodically
        if (batch_start + len(batch)) % SAVE_EVERY < batch_size:
            out_path = save()
            elapsed = time.time() - t0
            completed = len(baseline_results)
            rate = elapsed / completed if completed else 0
            remaining = (args.limit - start_idx - completed) * rate
            print(f"  Saved ({elapsed/60:.1f}m elapsed, ~{remaining/60:.1f}m remaining)")

    # ── Final summary ──
    out_path = save()
    elapsed = time.time() - t0
    n_done = len(baseline_results)
    print(f"\n{bold('=' * 70)}")
    print(f"  Final results saved to {out_path}")
    print(f"  Elapsed: {elapsed/60:.1f} minutes ({elapsed/n_done:.1f}s per problem)")
    print(f"  Baseline:    {sum(1 for r in baseline_results if r['passed'])}/{n_done}  ({sum(1 for r in baseline_results if r['passed'])/n_done*100:.1f}%)")
    print(f"  Basic V2:    {sum(1 for r in basic_results if r['passed'])}/{n_done}  ({sum(1 for r in basic_results if r['passed'])/n_done*100:.1f}%)")
    print(f"  Advanced V2: {sum(1 for r in advanced_results if r['passed'])}/{n_done}  ({sum(1 for r in advanced_results if r['passed'])/n_done*100:.1f}%)")
    print(f"{bold('=' * 70)}")
    kg.print_summary()


if __name__ == "__main__":
    main()
