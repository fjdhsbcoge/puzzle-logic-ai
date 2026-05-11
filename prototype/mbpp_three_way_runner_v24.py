"""
MBPP Three-Way Benchmark Runner v2.5
=====================================

Uses direct LLM calls + proper test programs, manually invoking v2.5 knowledge graph.

  1. BASELINE    — 3 clean attempts, no error information
  2. BASIC V2    — 3 attempts; raw error + strategy rotation on retry
  3. ADVANCED V2 — 3 attempts; high-confidence toolbox (>= 0.5) on attempts 2 AND 3
                   Decayed patterns (< 0.5) never shown. Multiplicative decay x0.8,
                   no floor. Reassembly resets all same-type patterns to 0.5.

Usage:
    python mbpp_three_way_runner_v24.py --model qwen2.5-coder-3b-instruct --limit 20 --debug
    python mbpp_three_way_runner_v24.py --model qwen2.5-coder-3b-instruct --limit 300
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from typing import Dict, List

# ── Import v2.4 engine ──────────────────────────────────────────────────
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
# Core: three modes (all using direct LLM calls, NOT agent.solve())
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
    """
    Mode 2: BASIC V2 — raw error + strategy rotation.
    Uses AttemptTracker to avoid repeating failed strategies.
    """
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
    """
    Mode 3: ADVANCED V2 — three-tier toolbox with fallback.
    Direct LLM calls. Proper test programs. Manual toolbox + record_fix.
    """
    expected = infer_function_name(problem["code"], problem["test_list"])
    base_prompt = (
        f"{problem['text']}\n\n"
        f"Write a Python function{f' named {expected!r}' if expected else ''} that solves this. "
        f"Output only the function code in a markdown code block."
    )

    last_error = ""
    last_code = ""
    used_toolbox = False
    tracker = AttemptTracker()  # strategy rotation when toolbox is empty

    for attempt in range(1, n_attempts + 1):
        full_prompt = base_prompt
        shown_patterns = []
        # ── Three-tier retry ──
        # Attempt 1: clean (no error info)
        # Attempt 2: high-confidence verified (conf >= 0.5)
        # Attempt 3: low-confidence verified (conf < 0.5) OR high-confidence fallback
        if last_error:
            if attempt == 1:
                pass  # clean — should never reach here
            elif attempt == 2:
                toolbox_text, shown_patterns = kg.get_coherent_toolbox(
                    last_error, top_k=3, min_confidence=0.5, max_confidence=1.0
                )
                if toolbox_text:
                    full_prompt = base_prompt + "\n\n" + toolbox_text + "\n"
                    used_toolbox = True
                else:
                    # No high-confidence verified patterns — raw error + rotation
                    rotation = tracker.get_rotation_hint()
                    full_prompt = (
                        base_prompt + "\n\n"
                        f"[Previous attempt FAILED with this error:]\n"
                        f"```\n{last_error}\n```\n"
                        f"Fix the code based on this error message.{rotation}"
                    )
            else:  # attempt >= 3
                # ── HIGH-CONFIDENCE TOOLBOX on attempt 3 too ──
                # Low-confidence patterns (<0.5) are NOT shown — they decayed for a reason.
                # Show the same proven high-confidence patterns again.
                toolbox_text, shown_patterns = kg.get_coherent_toolbox(
                    last_error, top_k=3, min_confidence=0.5, max_confidence=1.0
                )
                if toolbox_text:
                    full_prompt = base_prompt + "\n\n" + toolbox_text + "\n"
                    used_toolbox = True
                else:
                    # No high-confidence verified patterns — raw error + rotation
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
        # Penalize ONLY the specific patterns shown in toolbox that didn't work
        if used_toolbox and shown_patterns:
            kg.record_toolbox_failure(shown_patterns)
        # Track strategy rotation (even when toolbox wasn't shown)
        if last_code:
            tracker.record(extract_error_fingerprint(error_text)[0], last_code, code, False)
        last_error = error_text
        last_code = code

    return {"passed": False, "attempts": n_attempts, "code": code,
            "error": last_error, "used_toolbox": used_toolbox}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MBPP Three-Way Benchmark v2.4")
    parser.add_argument("--model",     type=str,  default=None)
    parser.add_argument("--limit",     type=int,  default=300)
    parser.add_argument("--attempts",  type=int,  default=3)
    parser.add_argument("--output",    type=str,  default=None)
    parser.add_argument("--resume",    type=str,  default=None)
    parser.add_argument("--debug",     action="store_true")
    parser.add_argument("--knowledge", type=str, default=None,
                        help="Knowledge graph file. Default: auto-generated per-run timestamp.")
    args = parser.parse_args()

    # ── Per-run knowledge graph filename ──
    if args.knowledge:
        kg_path = args.knowledge
    else:
        # Auto-generate: puzzle_logic_knowledge_YYYYMMDD_HHMMSS.json
        kg_path = f"puzzle_logic_knowledge_{time.strftime('%Y%m%d_%H%M%S')}.json"

    print(bold("=" * 70))
    print(bold("  MBPP Three-Way Benchmark — v2.5"))
    print(bold("  Baseline | Basic V2 (Strategy Rotation) | Advanced V2 (Omega + λ)"))
    print(bold("  High-confidence toolbox only (>= 0.5). No low-confidence tier."))
    print(bold("=" * 70))
    print(f"  Model: {args.model or 'auto-detect'}")
    print(f"  Problems: {args.limit}")
    print(f"  Attempts: {args.attempts}")
    # Omega is dynamically calculated from the knowledge graph
    print(f"  Knowledge graph: {kg_path}")
    print(bold("=" * 70))
    print()

    download_mbpp()

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
        print(f"  Resuming at problem {start_idx + 1}, {len(problems)} remaining.")
    else:
        baseline_results = []
        basic_results    = []
        advanced_results = []
        problems         = load_mbpp(MBPP_PATH, limit=args.limit)
        start_idx        = 0

    if not problems:
        print("No problems to run.")
        return

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

    # ── Initialize LLM + Knowledge Graph ──
    llm = LMStudioClient(model=model)
    kg  = CoherentKnowledgeGraph(storage_path=kg_path)
    print(f"Knowledge graph: {len(kg.patterns)} existing patterns | Ω={kg.omega}")

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
        # The knowledge graph auto-saves to kg_path via kg._save()
        # No separate snapshot needed — the living graph is the source of truth.
        return out

    # ── Run benchmark ──
    t0 = time.time()
    for idx, problem in enumerate(problems):
        global_idx = start_idx + idx
        pid = problem["task_id"]
        print(f"\n{cyan(f'[{global_idx + 1}/{args.limit}]')} {bold(pid)}: {problem['text'][:60]}...")

        # 1. BASELINE
        r0 = run_baseline(problem, llm, n_attempts=args.attempts, debug=args.debug)
        baseline_results.append({**r0, "task_id": pid})
        status0 = green("PASS") if r0["passed"] else red("FAIL")
        print(f"  Baseline:    {status0} (attempts={r0['attempts']})")

        # 2. BASIC V2
        r1 = run_basic_v2(problem, llm, n_attempts=args.attempts, debug=args.debug)
        basic_results.append({**r1, "task_id": pid})
        status1 = green("PASS") if r1["passed"] else red("FAIL")
        err = "+err" if r1.get("used_error_info") else "    "
        print(f"  Basic V2:    {status1} (attempts={r1['attempts']}) {err}")

        # 3. ADVANCED V2
        r2 = run_advanced_v2(problem, llm, kg, n_attempts=args.attempts, debug=args.debug)
        advanced_results.append({**r2, "task_id": pid})
        status2 = green("PASS") if r2["passed"] else red("FAIL")
        tb = "toolbox" if r2.get("used_toolbox") else "clean"
        print(f"  Advanced V2: {status2} (attempts={r2['attempts']}) {tb}")

        # Running totals
        b_pass  = sum(1 for r in baseline_results if r["passed"])
        ba_pass = sum(1 for r in basic_results    if r["passed"])
        a_pass  = sum(1 for r in advanced_results if r["passed"])
        n_done  = len(baseline_results)
        print(f"  Running: Baseline={b_pass}/{n_done}  BasicV2={ba_pass}/{n_done}  AdvancedV2={a_pass}/{n_done}")

        if (idx + 1) % SAVE_EVERY == 0:
            out_path = save()
            elapsed = time.time() - t0
            rate = elapsed / (idx + 1)
            remaining = (len(problems) - idx - 1) * rate
            print(f"  Saved to {out_path} ({elapsed/60:.1f}m elapsed, {remaining/60:.1f}m remaining)")

    # ── Final summary ──
    out_path = save()
    elapsed = time.time() - t0
    print(f"\n{bold('=' * 70)}")
    print(f"  Final results saved to {out_path}")
    print(f"  Elapsed: {elapsed/60:.1f} minutes")
    print(f"  Baseline:    {b_pass}/{n_done}  ({b_pass/n_done*100:.1f}%)")
    print(f"  Basic V2:    {ba_pass}/{n_done}  ({ba_pass/n_done*100:.1f}%)")
    print(f"  Advanced V2: {a_pass}/{n_done}  ({a_pass/n_done*100:.1f}%)")
    print(f"{bold('=' * 70)}")

    kg.print_summary()


if __name__ == "__main__":
    main()
