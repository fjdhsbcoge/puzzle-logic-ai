#!/usr/bin/env python3
"""
Aider-Puzzle Logic Bridge v1.0
================================

Integrates Puzzle Logic Agent into Aider's retry loop.

Place this file in your project root (e.g., my_data_app/aider_bridge.py).
It will find the puzzle-logic modules in the parent directory
(puzzle-logic-V2/) automatically.

Usage with Aider:
    aider --test-cmd "python aider_bridge.py --test"

What it does:
1. Runs pytest in your project
2. If tests FAIL:
   - Extracts error type and signature from pytest output
   - Queries the knowledge graph for relevant patterns
   - Outputs enriched test report with Creative Toolbox to stdout
   - Aider captures this output and feeds it to the LLM on retry
3. If tests PASS after a previous failure:
   - Records the successful fix to the knowledge graph
   - Pattern's Confidence and Agreeableness grow

Files created in your project (gitignore these):
  .puzzle_logic_knowledge.json   — the knowledge graph
  .puzzle_logic_failure_log.json — pending fix to record
  .puzzle_logic_toolbox.md       — latest toolbox output
"""

import argparse
import json
import os
import subprocess
import sys
import re
from pathlib import Path
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Path setup: find puzzle-logic modules in parent directory
# ---------------------------------------------------------------------------
# aider_bridge.py lives in:    my_data_app/aider_bridge.py
# puzzle-logic modules live in: puzzle-logic-V2/*.py
# We look 1 level up, then find the puzzle-logic folder

BRIDGE_DIR = Path(__file__).resolve().parent
PARENT_DIR = BRIDGE_DIR.parent  # e.g., puzzle-logic-V2

# Try parent first (if bridge is in my_data_app inside puzzle-logic-V2)
sys.path.insert(0, str(PARENT_DIR))

# Fallback: try bridge's own directory (if copied alongside modules)
sys.path.insert(0, str(BRIDGE_DIR))

_PUZZLE_MODULES_LOADED = False


def _load_puzzle_modules():
    global _PUZZLE_MODULES_LOADED
    if _PUZZLE_MODULES_LOADED:
        return
    try:
        from personality_engine import PersonalityKnowledgeGraph
        from utils import extract_error_fingerprint, code_delta
        _load_puzzle_modules.PersonalityKnowledgeGraph = PersonalityKnowledgeGraph
        _load_puzzle_modules.extract_error_fingerprint = extract_error_fingerprint
        _load_puzzle_modules.code_delta = code_delta
        _PUZZLE_MODULES_LOADED = True
    except ImportError as e:
        print(f"[Puzzle Logic Bridge] ERROR: Cannot import puzzle modules: {e}")
        print(f"  Tried paths: {PARENT_DIR}, {BRIDGE_DIR}")
        print("  Make sure personality_engine.py, utils.py, model_personality.py, ocean_config.py")
        print("  and legacy.py are in the same directory as aider_bridge.py or in the parent.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Pytest output parsing
# ---------------------------------------------------------------------------

PYTEST_ERROR_RE = re.compile(
    r"([A-Za-z]+Error|AssertionError|SyntaxError|TypeError|ValueError|NameError|"
    r"KeyError|IndexError|AttributeError|ImportError|ModuleNotFoundError|"
    r"RecursionError|TimeoutError|ZeroDivisionError|IndentationError)"
    r"[:,]?\s*(.*)"
)


def extract_pytest_error(output: str) -> Tuple[str, str, str]:
    """Parse pytest stderr/stdout to find the first error."""
    lines = output.split("\n")
    for i, line in enumerate(lines):
        m = PYTEST_ERROR_RE.search(line)
        if m:
            err_type = m.group(1)
            err_sig = m.group(2).strip()[:200]
            start = max(0, i - 3)
            end = min(len(lines), i + 4)
            context = "\n".join(lines[start:end])
            return err_type, err_sig, context

    # Fallback: look for FAILED lines
    for line in lines:
        if "FAILED" in line:
            return "Unknown", line.strip()[:200], output[:500]

    return "Unknown", output[:200], output[:500]


# ---------------------------------------------------------------------------
# Knowledge graph I/O
# ---------------------------------------------------------------------------

_KG_CACHE = None


def get_knowledge_path() -> Path:
    """Knowledge graph lives in the project root (hidden file)."""
    return Path.cwd() / ".puzzle_logic_knowledge.json"


def load_knowledge_graph():
    """Load or create the knowledge graph for this project."""
    global _KG_CACHE
    _load_puzzle_modules()

    kg_path = get_knowledge_path()
    KGraph = _load_puzzle_modules.PersonalityKnowledgeGraph

    if kg_path.exists():
        try:
            with open(kg_path, "r") as f:
                data = json.load(f)
            kg = KGraph.__new__(KGraph)
            kg.patterns = []
            kg.by_type = {}
            kg.storage_path = str(kg_path)
            kg._dirty = False
            kg._toolbox_failures = {}
            for p in data.get("patterns", []):
                from personality_engine import PersonalityPatternNode
                node = PersonalityPatternNode.from_dict(p)
                kg.patterns.append(node)
                kg.by_type.setdefault(node.error_type, []).append(node)
            _KG_CACHE = kg
            return kg
        except Exception as e:
            print(f"[Puzzle Logic] Could not load knowledge graph: {e}")

    kg = KGraph(storage_path=str(kg_path))
    _KG_CACHE = kg
    return kg


def save_knowledge_graph():
    """Persist the knowledge graph to disk."""
    global _KG_CACHE
    if _KG_CACHE and _KG_CACHE._dirty:
        try:
            _KG_CACHE.save()
            _KG_CACHE._dirty = False
        except Exception as e:
            print(f"[Puzzle Logic] Could not save knowledge graph: {e}")


# ---------------------------------------------------------------------------
# Phase 2: Record fix when tests pass after a failure
# ---------------------------------------------------------------------------

_FAILURE_LOG = Path.cwd() / ".puzzle_logic_failure_log.json"


def log_failure(error_type: str, error_sig: str, failing_code: str):
    """Remember that we failed, so we can record the fix when we pass."""
    entry = {
        "error_type": error_type,
        "error_signature": error_sig,
        "failing_code": failing_code,
        "timestamp": __import__('datetime').datetime.now().isoformat(),
    }
    try:
        if _FAILURE_LOG.exists():
            with open(_FAILURE_LOG, "r") as f:
                history = json.load(f)
        else:
            history = []
        history.append(entry)
        with open(_FAILURE_LOG, "w") as f:
            json.dump(history, f, indent=2)
    except Exception:
        pass


def consume_failure_and_record_fix(fixed_code: str):
    """If there was a previous failure, record the successful fix."""
    if not _FAILURE_LOG.exists():
        return

    try:
        with open(_FAILURE_LOG, "r") as f:
            history = json.load(f)
        if not history:
            return
        last = history[-1]
    except Exception:
        return

    kg = load_knowledge_graph()
    err_type = last.get("error_type", "Unknown")
    err_sig = last.get("error_signature", "")
    failing_code = last.get("failing_code", "")

    kg.record_fix(
        error_text=f"{err_type}: {err_sig}",
        failing_code=failing_code,
        fixed_code=fixed_code,
    )
    save_knowledge_graph()

    # Clear the failure log
    try:
        with open(_FAILURE_LOG, "w") as f:
            json.dump([], f)
    except Exception:
        pass

    print(f"[Puzzle Logic] Fix recorded to knowledge graph: {err_type}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_tests() -> Tuple[int, str, str]:
    """Run pytest and capture output."""
    result = subprocess.run(
        ["pytest", "-x", "-v"],
        capture_output=True,
        text=True,
        cwd=str(Path.cwd()),
    )
    return result.returncode, result.stdout, result.stderr


def main():
    parser = argparse.ArgumentParser(
        description="Aider-Puzzle Logic Bridge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage with Aider:
  aider --test-cmd "python aider_bridge.py --test"

The bridge runs pytest. On failure, it enriches the output with Puzzle Logic's
Creative Toolbox so Aider's retry prompt includes verified patterns.
        """,
    )
    parser.add_argument("--test", action="store_true", help="Run pytest with Puzzle Logic enrichment")
    parser.add_argument(
        "--knowledge-path",
        default=".puzzle_logic_knowledge.json",
        help="Path to knowledge graph (default: .puzzle_logic_knowledge.json in project root)",
    )
    args = parser.parse_args()

    if args.test:
        returncode, stdout, stderr = run_tests()
        full_output = stdout + "\n" + stderr

        print(full_output)

        if returncode != 0:
            # ── Phase 1: FAILURE → enrich with toolbox ───────────────────
            err_type, err_sig, trace = extract_pytest_error(full_output)
            print(f"\n{'='*60}")
            print(f"[Puzzle Logic Bridge] Detected: {err_type}")
            print(f"{'='*60}")

            kg = load_knowledge_graph()

            # Get toolbox
            toolbox_text, shown = kg.get_toolbox(
                error_text=f"{err_type}: {err_sig}",
                failing_code="",
            )

            if toolbox_text:
                print(f"\n{toolbox_text}")
            else:
                print(f"\n[Puzzle Logic] No verified patterns for {err_type} yet.")
                print("           This error type will build knowledge on the next success.")

            # Remember this failure for Phase 2
            log_failure(err_type, err_sig, "")

            sys.exit(returncode)

        else:
            # ── Phase 2: PASS → record fix if we recovered from failure ──
            project_root = Path.cwd()
            module_candidates = [
                p for p in project_root.glob("*.py")
                if p.name not in ("aider_bridge.py", "conftest.py", "setup.py")
                and not p.name.startswith("test_")
            ]
            fixed_code = ""
            if module_candidates:
                try:
                    fixed_code = module_candidates[0].read_text()
                except Exception:
                    pass

            consume_failure_and_record_fix(fixed_code)

            # Clean up toolbox file on success
            md_path = project_root / ".puzzle_logic_toolbox.md"
            if md_path.exists():
                try:
                    md_path.unlink()
                except Exception:
                    pass

            sys.exit(0)

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
