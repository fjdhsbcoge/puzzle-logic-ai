"""
MBPP Three-Way Benchmark Runner v2.6 — PIPELINED CONCURRENT
=============================================================

Maximizes GPU utilization by processing each problem COMPLETELY
(Baseline + Basic + Advanced) in a single worker thread.

  1. BASELINE    — 3 clean attempts, no error information
  2. BASIC V2    — 3 attempts; raw error + strategy rotation on retry
  3. ADVANCED V2 — 3 attempts; high-confidence toolbox (>= 0.5) on attempts 2 AND 3

Architecture:
  - 8 worker threads (default), each processes ONE problem end-to-end
  - As a worker finishes, it picks up the next problem
  - Knowledge Graph is protected by a thread lock
  - GPU sees 8 concurrent LLM requests continuously

Output (2 files, updated in-place during the run):
  1. puzzle_logic_knowledge.json  — Living knowledge graph (confidence, patterns, omega)
  2. puzzle_logic_log.json        — Full results log (baseline/basic/advanced results + metadata)

Usage:
    python mbpp_three_way_runner_v26.py --model qwen2.5-coder-7b-instruct --limit 20 --workers 8
    python mbpp_three_way_runner_v26.py --model qwen2.5-coder-3b-instruct --limit 974 --workers 8
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

# ── Import v2.6 engine ──────────────────────────────────────────────────
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
                    kg_lock: threading.Lock,
                    n_attempts: int = 3, debug: bool = False) -> Dict:
    """Mode 3: ADVANCED V2 — high-confidence toolbox only (>= 0.5).
    kg_lock protects Knowledge Graph operations across threads."""

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
            elif attempt >= 2:
                with kg_lock:
                    toolbox_text, shown_patterns = kg.get_coherent_toolbox(
                        last_error, failing_code=last_code, top_k=3,
                        min_confidence=0.5, max_confidence=1.0,
                        llm_client=llm
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
            with kg_lock:
                kg.record_error("extraction failed")
            continue

        if expected:
            gen = extract_generated_name(code)
            if gen and gen != expected:
                code = fix_function_name(code, expected)

        result = execute_code(build_test_program(problem, code), timeout=TIMEOUT)
        if result["passed"]:
            if last_error:
                with kg_lock:
                    kg.record_fix(last_error, failing_code=last_code, fixed_code=code)
            return {"passed": True, "attempts": attempt, "code": code,
                    "error": None, "used_toolbox": used_toolbox}

        error_text = result.get("error", "unknown")
        with kg_lock:
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
# Worker: one problem end-to-end (Baseline + Basic + Advanced)
# ---------------------------------------------------------------------------

def process_problem(problem: Dict, llm: LMStudioClient,
                    kg: CoherentKnowledgeGraph, kg_lock: threading.Lock,
                    n_attempts: int, debug: bool) -> Dict:
    """Process one problem through all three modes. Runs in a worker thread."""
    r0 = run_baseline(problem, llm, n_attempts=n_attempts, debug=debug)
    r1 = run_basic_v2(problem, llm, n_attempts=n_attempts, debug=debug)
    r2 = run_advanced_v2(problem, llm, kg, kg_lock,
                         n_attempts=n_attempts, debug=debug)
    return {
        "task_id": problem["task_id"],
        "baseline": r0,
        "basic": r1,
        "advanced": r2,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MBPP Three-Way Benchmark v2.6 Pipelined Concurrent")
    parser.add_argument("--model",     type=str,  default=None)
    parser.add_argument("--limit",     type=int,  default=300)
    parser.add_argument("--attempts",  type=int,  default=3)
    parser.add_argument("--resume",    type=str,  default=None)
    parser.add_argument("--debug",     action="store_true")
    parser.add_argument("--workers",   type=int,  default=8,
                        help="Number of concurrent worker threads (default: 8)")
    args = parser.parse_args()

    # ── Fixed output paths (2 files only) ──
    kg_path = "puzzle_logic_knowledge.json"
    log_path = "puzzle_logic_log.json"

    print(bold("=" * 70))
    print(bold("  MBPP Three-Way Benchmark — v2.6 PIPELINED CONCURRENT"))
    print(bold("  Baseline | Basic V2 | Advanced V2 (Omega + λ)"))
    print(bold(f"  Worker threads: {args.workers} (each problem = all 3 modes)"))
    print(bold("  Output: puzzle_logic_knowledge.json + puzzle_logic_log.json"))
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
    kg_lock = threading.Lock()
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
        """Save both files in-place: knowledge graph + results log."""
        # 1. Knowledge graph (fast, small)
        kg.flush()
        # 2. Results log (overwrites in place)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump({
                "model": model,
                "n_problems": start_idx + len(baseline_results),
                "timestamp": time.strftime("%Y%m%d_%H%M%S"),
                "omega": kg.omega,
                "baseline_results": baseline_results,
                "basic_results":    basic_results,
                "advanced_results": advanced_results,
                "baseline_passed":  sum(1 for r in baseline_results if r["passed"]),
                "basic_passed":     sum(1 for r in basic_results    if r["passed"]),
                "advanced_passed":  sum(1 for r in advanced_results if r["passed"]),
            }, f, indent=2)
        return log_path

    # ── Run benchmark (pipelined concurrent) ──
    t0 = time.time()
    n_done = len(baseline_results)
    completed_lock = threading.Lock()

    def on_complete(future):
        """Callback: called when a worker finishes a problem."""
        nonlocal n_done
        try:
            result = future.result()
            pid = result["task_id"]

            # Thread-safe append to result lists
            with completed_lock:
                global_idx = n_done
                n_done += 1

                r0 = result["baseline"]
                r1 = result["basic"]
                r2 = result["advanced"]

                baseline_results.append({**r0, "task_id": pid})
                basic_results.append({**r1, "task_id": pid})
                advanced_results.append({**r2, "task_id": pid})

                status0 = green("PASS") if r0["passed"] else red("FAIL")
                status1 = green("PASS") if r1["passed"] else red("FAIL")
                status2 = green("PASS") if r2["passed"] else red("FAIL")
                err = "+err" if r1.get("used_error_info") else "    "
                tb = "toolbox" if r2.get("used_toolbox") else "clean"

                b_pass  = sum(1 for r in baseline_results if r["passed"])
                ba_pass = sum(1 for r in basic_results    if r["passed"])
                a_pass  = sum(1 for r in advanced_results if r["passed"])

                print(f"  [{global_idx + 1}] {bold(pid[:10])}: "
                      f"Base={status0}({r0['attempts']}) "
                      f"Basic={status1}({r1['attempts']}){err} "
                      f"Adv={status2}({r2['attempts']}){tb} | "
                      f"B={b_pass}/{n_done} V2={ba_pass}/{n_done} Adv={a_pass}/{n_done}")

                if n_done % SAVE_EVERY == 0:
                    out_path = save()
                    elapsed = time.time() - t0
                    rate = elapsed / n_done if n_done else 0
                    remaining = (args.limit - start_idx - n_done) * rate
                    print(f"  {cyan('>>> Saved')} ({elapsed/60:.1f}m elapsed, ~{remaining/60:.1f}m remaining)")

        except Exception as e:
            print(f"  {red('WORKER ERROR')}: {e}")

    print(f"\nStarting {args.workers} workers for {len(problems)} problems...")
    print(f"Each worker processes one problem through all 3 modes (9 LLM calls).\n")

    # ── Continuous feed: submit in small batches to keep pool saturated ──
    batch_size = args.workers * 2  # always 2× workers worth of pending work
    pending_futures = []
    problem_idx = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Initial batch
        for _ in range(min(batch_size, len(problems))):
            future = executor.submit(
                process_problem, problems[problem_idx], llm, kg, kg_lock,
                args.attempts, args.debug
            )
            future.add_done_callback(on_complete)
            pending_futures.append(future)
            problem_idx += 1

        # As futures complete, submit new ones to keep pool full
        while problem_idx < len(problems):
            done_futures = [f for f in pending_futures if f.done()]
            for f in done_futures:
                pending_futures.remove(f)
            
            # Fill back up to batch_size
            while len(pending_futures) < batch_size and problem_idx < len(problems):
                future = executor.submit(
                    process_problem, problems[problem_idx], llm, kg, kg_lock,
                    args.attempts, args.debug
                )
                future.add_done_callback(on_complete)
                pending_futures.append(future)
                problem_idx += 1
            
            # Brief sleep to avoid busy-waiting
            time.sleep(0.01)

        # Wait for remaining futures
        for f in as_completed(pending_futures):
            pass  # on_complete already handled results

    # ── Final summary ──
    out_path = save()
    elapsed = time.time() - t0
    n_done = len(baseline_results)
    print(f"\n{bold('=' * 70)}")
    print(f"  Final results saved to:")
    print(f"    Knowledge: {kg_path}")
    print(f"    Log:       {out_path}")
    print(f"  Elapsed: {elapsed/60:.1f} minutes ({elapsed/n_done:.1f}s per problem)")
    print(f"  Baseline:    {sum(1 for r in baseline_results if r['passed'])}/{n_done}  ({sum(1 for r in baseline_results if r['passed'])/n_done*100:.1f}%)")
    print(f"  Basic V2:    {sum(1 for r in basic_results if r['passed'])}/{n_done}  ({sum(1 for r in basic_results if r['passed'])/n_done*100:.1f}%)")
    print(f"  Advanced V2: {sum(1 for r in advanced_results if r['passed'])}/{n_done}  ({sum(1 for r in advanced_results if r['passed'])/n_done*100:.1f}%)")
    print(f"{bold('=' * 70)}")
    kg.print_summary()


if __name__ == "__main__":
    main()
