"""
Puzzle Logic v4.0 — Shared Utilities
=====================================

Functions used across puzzle_logic_agent.py, personality_engine.py, and constraint_engine.py.
Extracted to remove duplication and deepen the module boundaries.
"""

import json
import os
import re
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════
#  1.  ERROR FINGERPRINTING
# ═══════════════════════════════════════════════════════════════════════

def extract_error_fingerprint(error_text: str) -> Tuple[str, str, str]:
    """Extract (error_type, signature, failing_line) from ANY Python traceback."""
    if not error_text:
        return ("Unknown", "empty error", "")

    lines = error_text.strip().split("\n")
    err_type, err_msg = "Other", ""

    # Find the exception line (bottom of traceback)
    for line in reversed(lines):
        m = re.search(
            r"^(\w+Error|\w+Exception|RecursionError|TimeoutError|StopIteration):\s*(.*)$",
            line,
        )
        if m:
            err_type, err_msg = m.group(1), m.group(2).strip()
            break

    # Fallback: scan for known exception keywords (handles AssertionError without colon)
    if err_type == "Other":
        for pattern in [
            "AssertionError", "NameError", "TypeError", "SyntaxError", "IndexError",
            "KeyError", "ValueError", "AttributeError", "ImportError",
            "ModuleNotFoundError", "IndentationError", "RecursionError",
            "TimeoutError", "ZeroDivisionError",
        ]:
            if pattern in error_text:
                err_type = pattern
                m = re.search(rf"{pattern}:\s*(.+?)(?:\n|$)", error_text)
                if m:
                    err_msg = m.group(1).strip()
                break

    # Extract the failing code line (the line of source code in the traceback)
    failing_line = ""
    for i, line in enumerate(lines):
        if re.search(r'File "[^"]+", line \d+, in \S+', line):
            if i + 1 < len(lines):
                candidate = lines[i + 1].strip()
                if candidate and not candidate.startswith("^") and not candidate.startswith("Traceback"):
                    failing_line = candidate[:120]
                    break

    # For AssertionError with empty message, use the failing line as signature
    if err_type == "AssertionError" and not err_msg and failing_line:
        err_msg = failing_line

    # Normalize signature (strip variable names, keep structure)
    sig = err_msg
    sig = re.sub(r"'[^']+'", "'<name>'", sig)
    sig = re.sub(r'"[^"]+"', '"<name>"', sig)
    sig = re.sub(r"\b0x[0-9a-f]+\b", "<addr>", sig)
    sig = re.sub(r"\d+", "<N>", sig)
    if len(sig) > 120:
        sig = sig[:120] + "..."

    return (err_type, sig, failing_line)


def infer_fix_strategy(error_type: str, error_sig: str) -> str:
    """Map common error types to structural fix strategies."""
    strategies = {
        "NameError":      "Name not defined: check function name matches test expectation exactly.",
        "TypeError":      "Type / signature mismatch: check arg count, types, and default values.",
        "SyntaxError":    "Syntax error: check missing colons, brackets, or indentation.",
        "IndentationError": "Fix indentation: use consistent 4-space indentation.",
        "IndexError":     "Index out of range: check loop bounds and list length.",
        "KeyError":       "Missing dictionary key: use .get() or check key exists.",
        "ValueError":     "Wrong value: check input validation and type conversion.",
        "AttributeError": "Missing attribute: the object doesn't have that method/property.",
        "ImportError":    "Import failed: check spelling and that module is installed.",
        "ModuleNotFoundError": "Module not found: check module name spelling.",
        "RecursionError": "Infinite recursion: check base case and recursive calls.",
        "TimeoutError":   "Timeout / infinite loop: check loop conditions and breaks.",
        "ZeroDivisionError": "Division by zero: guard denominator with if statement.",
        "AssertionError": "Wrong output: trace through test input step by step.",
    }
    return strategies.get(error_type, f"{error_type}: analyze the error and fix root cause.")


# ═══════════════════════════════════════════════════════════════════════
#  2.  LOCALITY & CODE DELTA
# ═══════════════════════════════════════════════════════════════════════

def compute_locality(error_type: str, code_delta: str) -> float:
    """Compute error locality (lambda) from error type and fix complexity."""
    base = {
        "NameError": 1.0,
        "SyntaxError": 1.0,
        "IndentationError": 1.0,
        "TypeError": 0.8,
        "IndexError": 0.7,
        "KeyError": 0.7,
        "ValueError": 0.6,
        "AttributeError": 0.6,
        "ImportError": 0.9,
        "ModuleNotFoundError": 0.9,
        "ZeroDivisionError": 0.7,
        "RecursionError": 0.3,
        "TimeoutError": 0.3,
        "AssertionError": 0.2,
    }.get(error_type, 0.5)

    if code_delta:
        changes = code_delta.count("Changed:") + code_delta.count("Added:") + code_delta.count("Removed:")
        if changes <= 1:
            delta_factor = 1.0
        elif changes <= 3:
            delta_factor = 0.6
        else:
            delta_factor = 0.2
    else:
        delta_factor = 0.5

    return round((base + delta_factor) / 2, 2)


def compute_fix_complexity(code_delta: str) -> int:
    """Count the number of structural changes in a code delta."""
    if not code_delta:
        return 1
    changes = code_delta.count("Changed:") + code_delta.count("Added:") + code_delta.count("Removed:")
    return max(1, changes)


def code_delta(old: str, new: str) -> str:
    """Generate a human-readable delta between two code snippets."""
    if not old or not new:
        return ""
    old_lines = [l.strip() for l in old.strip().split("\n") if l.strip()]
    new_lines = [l.strip() for l in new.strip().split("\n") if l.strip()]
    changed = []
    max_len = min(len(old_lines), len(new_lines))
    for i in range(max_len):
        if old_lines[i] != new_lines[i]:
            changed.append(f"  Changed: {old_lines[i]} -> {new_lines[i]}")
    for i in range(max_len, len(new_lines)):
        changed.append(f"  Added: {new_lines[i]}")
    for i in range(max_len, len(old_lines)):
        changed.append(f"  Removed: {old_lines[i]}")
    if not changed:
        return ""
    result = "Fix: " + "; ".join(changed[:3])
    if len(result) > 200:
        result = result[:200] + "..."
    return result


def summarize_fix_principle(
    failing_code: str,
    fixed_code: str,
    error_type: str,
    error_signature: str,
    llm_client,
    max_tokens: int = 128,
) -> str:
    """
    Ask the LLM to generalize a successful fix into a reusable principle.

    Instead of storing a raw code diff (problem-specific), we store a
    general strategy that the LLM can apply to different but similar errors.

    If llm_client is None, falls back to code_delta.
    """
    if not llm_client or not failing_code or not fixed_code:
        return code_delta(failing_code, fixed_code)

    # Compute the raw code diff for context
    delta = code_delta(failing_code, fixed_code)

    prompt = (
        f"You are analyzing a successful bug fix. Your output will be shown to an LLM "
        f"that is trying to fix a SIMILAR but DIFFERENT error. The principle must be "
        f"specific enough that the LLM knows exactly what syntax to change.\n\n"
        f"Error type: {error_type}\n"
        f"Error message: {error_signature[:200]}\n\n"
        f"Failing code:\n```python\n{failing_code[:800]}\n```\n\n"
        f"Fixed code:\n```python\n{fixed_code[:800]}\n```\n\n"
        f"Raw diff: {delta[:200] if delta else 'N/A'}\n\n"
        f"RULES:\n"
        f"1. State the fix as a concrete code change, not vague advice.\n"
        f"2. Include the ACTUAL SYNTAX where possible (operators, function names, types).\n"
        f"3. Say WHERE to look: 'on the line with X', 'in the function signature', etc.\n"
        f"4. Do NOT mention the example's specific variable names.\n"
        f"5. ONE sentence only, max 30 words.\n\n"
        f"BAD (too vague):  'Ensure all variables are properly defined'\n"
        f"GOOD (specific):  'When int() fails, wrap the argument with str() first: int(str(x))'\n"
        f"BAD (too vague):  'Make sure the logic handles all cases'\n"
        f"GOOD (specific):  'When comparing list lengths, use len(a) == len(b) before zip'\n\n"
        f"Principle:"
    )

    try:
        raw_list = llm_client.generate(
            prompt=prompt,
            temperature=0.0,
            max_tokens=max_tokens,
            n=1,
        )
        raw = raw_list[0] if raw_list else ""
        principle = raw.strip().strip('"').strip("'")
        # Truncate if too long
        if len(principle) > 200:
            principle = principle[:200] + "..."
        if principle:
            return principle
    except Exception:
        pass

    # Fallback to raw diff if LLM call fails or returns empty
    return code_delta(failing_code, fixed_code)


# ═══════════════════════════════════════════════════════════════════════
#  3.  PATTERN MATCHING & SIMILARITY
# ═══════════════════════════════════════════════════════════════════════

def same_pattern(sig1: str, sig2: str) -> bool:
    """Check if two error signatures describe the same underlying pattern."""
    if sig1 == sig2:
        return True
    s1 = sig1.replace("'", "").replace('"', '').lower()
    s2 = sig2.replace("'", "").replace('"', '').lower()
    if s1 == s2:
        return True
    t1, t2 = set(s1.split()), set(s2.split())
    if not t1 or not t2:
        return False
    return len(t1 & t2) >= min(len(t1), len(t2)) * 0.5


def sig_similarity(sig1: str, sig2: str) -> float:
    """Jaccard similarity between two normalized error signatures."""
    s1 = sig1.replace("'", "").replace('"', '').lower()
    s2 = sig2.replace("'", "").replace('"', '').lower()
    if s1 == s2:
        return 1.0
    t1, t2 = set(s1.split()), set(s2.split())
    if not t1 or not t2:
        return 0.0
    return len(t1 & t2) / len(t1 | t2)


def extract_func_name(line: str) -> Optional[str]:
    """Extract the function name from a line of code."""
    if not line:
        return None
    m = re.search(r'(\w+)\s*\(', line.strip().lower())
    return m.group(1) if m else None


# ═══════════════════════════════════════════════════════════════════════
#  4.  CODE EXTRACTION & EXECUTION
# ═══════════════════════════════════════════════════════════════════════

def extract_code(text: str) -> str:
    """Extract Python code from model output (markdown blocks or raw)."""
    if not text:
        return ""
    blocks = re.findall(
        r"```(?:\n|\r\n)?(?:python(?:\n|\r\n))?(.*?)```", text, re.DOTALL
    )
    for block in blocks:
        block = block.strip()
        if block and ("def " in block or "return" in block or "for " in block or "if " in block):
            return block
    text = text.strip()
    if text and ("def " in text or "return" in text or "for " in text or "if " in text):
        return text
    return ""


def execute_code(python_code: str, timeout: int = 5) -> Dict:
    """Execute Python in a subprocess sandbox."""
    import subprocess
    import sys
    import tempfile

    if not python_code or not python_code.strip():
        return {"passed": False, "error": "No code to execute", "stdout": ""}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(python_code)
        temp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True, text=True, timeout=timeout
        )
        passed = result.returncode == 0
        error = result.stderr if not passed else None
        if error and len(error) > 500:
            error = error[:500] + "..."
        return {"passed": passed, "error": error, "stdout": result.stdout}
    except subprocess.TimeoutExpired:
        return {"passed": False, "error": "Timeout -- possible infinite loop", "stdout": ""}
    except Exception as e:
        return {"passed": False, "error": str(e), "stdout": ""}
    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass
