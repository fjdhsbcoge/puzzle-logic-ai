"""
Puzzle Logic Agent v3.5  --  Basic V2 + Advanced V3.5 (Natural Language Knowledge Browser)
===========================================================================================

Two modes:

  BASIC V2    —  Raw error + per-problem strategy tracking with rotation.

  ADVANCED V3.5 —  No fingerprint scoring, no cross-function penalty.
                   Same-error-type verified patterns are shown as natural
                   language examples. The LLM decides which ones apply.
                   Confidence: +0.1 on fix, ×0.8 on toolbox failure.

Usage:
  python puzzle_logic_agent.py my_script.py --model qwen2.5-coder-3b-instruct
  python puzzle_logic_agent.py my_script.py --test test_my_script.py
  python puzzle_logic_agent.py --generate "Write a function..."
  python puzzle_logic_agent.py --stats
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from typing import Optional, Dict, List, Tuple
from collections import defaultdict
from datetime import datetime


def cyan(s):   return f"\033[36m{s}\033[0m"
def green(s):  return f"\033[32m{s}\033[0m"
def red(s):    return f"\033[31m{s}\033[0m"
def yellow(s): return f"\033[33m{s}\033[0m"
def bold(s):   return f"\033[1m{s}\033[0m"


# ═══════════════════════════════════════════════════════════════════════
#  1.  UTILITIES
# ═══════════════════════════════════════════════════════════════════════

def extract_error_fingerprint(error_text: str) -> Tuple[str, str, str]:
    """Extract (error_type, signature, failing_line) from ANY Python traceback."""
    if not error_text:
        return ("Unknown", "empty error", "")

    lines = error_text.strip().split("\n")
    err_type, err_msg = "Other", ""

    # Find the exception line (bottom of traceback)
    for line in reversed(lines):
        m = re.search(r"^(\w+Error|\w+Exception|RecursionError|TimeoutError|StopIteration):\s*(.*)$", line)
        if m:
            err_type, err_msg = m.group(1), m.group(2).strip()
            break

    # Fallback: scan for known exception keywords (handles AssertionError without colon)
    if err_type == "Other":
        for pattern in ["AssertionError", "NameError", "TypeError", "SyntaxError", "IndexError",
                       "KeyError", "ValueError", "AttributeError", "ImportError",
                       "ModuleNotFoundError", "IndentationError", "RecursionError",
                       "TimeoutError", "ZeroDivisionError"]:
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

    # For AssertionError with empty message, use the failing line (the assertion) as signature
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


def extract_code(text: str) -> str:
    """Extract code from model output."""
    if not text:
        return ""
    blocks = re.findall(r"```(?:\n|\r\n)?(?:python(?:\n|\r\n))?(.*?)```", text, re.DOTALL)
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
    if not python_code or not python_code.strip():
        return {"passed": False, "error": "No code to execute", "stdout": ""}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(python_code)
        temp_path = f.name

    try:
        result = subprocess.run([sys.executable, temp_path],
                                capture_output=True, text=True, timeout=timeout)
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


# ═══════════════════════════════════════════════════════════════════════
#  2.  BASIC V2  —  Strategy Rotation
# ═══════════════════════════════════════════════════════════════════════

class StrategyExtractor:
    """Guess what fix strategy was tried from a code diff."""

    # Keywords that map to strategy names
    RULES = [
        ("add parameter",       lambda d: "def " in d and (")," in d or ")," in d or "def " in d and d.count(",") > 0)),
        ("remove parameter",    lambda d: "def " in d and d.count(",") < 0),  # heuristic: hard to detect
        ("change return value",   lambda d: "return " in d),
        ("add import",          lambda d: "import " in d or "from " in d),
        ("change operator",     lambda d: any(op in d for op in [" + ", " - ", " * ", " / ", " % ", " ** ", " // ", " == ", " != ", " < ", " > "])),
        ("change condition",    lambda d: "if " in d or "else:" in d or "elif " in d),
        ("add loop",            lambda d: "for " in d or "while " in d),
        ("add guard/check",     lambda d: any(g in d for g in ["if not", "if len", "if isinstance", "if type", "try:", "except"])),
        ("change variable",     lambda d: " = " in d and not "==" in d),
        ("add recursion",       lambda d: False),  # complex to detect
        ("change function name",lambda d: "def " in d),
    ]

    def extract(self, old_code: str, new_code: str) -> str:
        """Guess the strategy from the code delta."""
        if not old_code or not new_code:
            return "unknown"
        old_lines = set(l.strip() for l in old_code.strip().split("\n") if l.strip())
        new_lines = set(l.strip() for l in new_code.strip().split("\n") if l.strip())
        delta_lines = list(old_lines.symmetric_difference(new_lines))
        delta_text = "\n".join(delta_lines)

        for name, test in self.RULES:
            if test(delta_text):
                return name
        return "code change"


class AttemptTracker:
    """Tracks strategies tried within a single problem to avoid repetition."""

    def __init__(self):
        self.attempts: List[Dict] = []

    def record(self, error_type: str, old_code: str, new_code: str, passed: bool):
        strategy = StrategyExtractor().extract(old_code, new_code)
        self.attempts.append({
            "error_type": error_type,
            "strategy": strategy,
            "passed": passed,
        })

    def get_rotation_hint(self) -> str:
        """Generate a hint about what NOT to try again."""
        failed = [a["strategy"] for a in self.attempts if not a["passed"]]
        if not failed:
            return ""
        # Deduplicate while preserving order
        seen = set()
        unique_failed = []
        for s in failed:
            if s not in seen:
                seen.add(s)
                unique_failed.append(s)

        lines = [
            "",
            "[Strategy rotation — do NOT repeat what already failed]",
            f"Failed approaches for this problem: {', '.join(unique_failed)}",
            "Try a completely different strategy. Think about what the error REALLY means.",
        ]
        return "\n".join(lines)

    def get_successful_strategy(self) -> str:
        """Return the strategy that worked, if any."""
        for a in reversed(self.attempts):
            if a["passed"]:
                return a["strategy"]
        return ""


# ═══════════════════════════════════════════════════════════════════════
#  3.  ADVANCED V2  —  Coherent Knowledge Graph with Omega + Lambda
# ═══════════════════════════════════════════════════════════════════════

class ErrorPatternNode:
    """A validated error-fix pattern with locality (λ) tracking."""

    def __init__(self, error_type: str, error_signature: str, failing_line: str = "",
                 fix_strategy: str = "", context: str = "", locality: float = 0.5):
        self.error_type      = error_type
        self.error_signature = error_signature
        self.failing_line    = failing_line
        self.fix_strategy    = fix_strategy
        self.confidence      = 1.0
        self.context         = context[:300]
        self.times_seen      = 1
        self.times_fixed     = 0
        self.locality        = locality   # λ: 1.0=local, 0.0=unlocal
        self.timestamp       = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: Dict) -> "ErrorPatternNode":
        n = cls(d["error_type"], d["error_signature"], d.get("failing_line", ""),
                d["fix_strategy"], d.get("context", ""), d.get("locality", 0.5))
        n.confidence  = d.get("confidence", 1.0)
        n.times_seen  = d.get("times_seen", 1)
        n.times_fixed = d.get("times_fixed", 0)
        n.locality    = d.get("locality", 0.5)
        n.timestamp   = d.get("timestamp", datetime.now().isoformat())
        return n


class CoherentKnowledgeGraph:
    """
    v2.5 Advanced — Coherent picture with Omega belief revision and Local/Unlocal.

    Omega (Ω) ∈ [0,1]: openness to revising confidence of related patterns.
      Ω = 1.0 → very open: new fix strongly boosts similar patterns
      Ω = 0.0 → conservative: new fix only boosts the exact pattern

    Lambda (λ) ∈ [0,1]: locality of a problem.
      λ = 1.0 → perfectly local (NameError, single-line SyntaxError)
      λ = 0.0 → perfectly unlocal (AssertionError about algorithm logic)

    Decay: multiplicative (x0.8) with no floor. Patterns fade toward 0 but are
    never truly forgotten. Reassembly (new same-type fix) resets all to 0.5.
    """

    def __init__(self, storage_path: str = "puzzle_logic_knowledge.json"):
        self.storage_path = storage_path
        self.patterns: List[ErrorPatternNode] = []
        self.by_type: Dict[str, List[ErrorPatternNode]] = defaultdict(list)
        self._dirty = False
        self._toolbox_failures = defaultdict(int)  # track consecutive toolbox failures per error type
        self._load()

    @property
    def omega(self) -> float:
        """Ω = average confidence of all verified patterns.

        Characterises the system's expertise in the current domain.
        High Ω → system is confident in its knowledge (expert mode).
        Low Ω → system is still learning (novice mode).
        """
        if not self.patterns:
            return 0.5
        return sum(p.confidence for p in self.patterns) / len(self.patterns)

    # ── Locality (λ) computation ───────────────────────────────────────

    def _compute_locality(self, error_type: str, code_delta: str) -> float:
        """Compute λ (locality): 1.0 = perfectly local, 0.0 = unlocal."""
        # Base score from error type
        base = {
            "NameError": 1.0, "SyntaxError": 1.0, "IndentationError": 1.0,
            "TypeError": 0.8, "IndexError": 0.7, "KeyError": 0.7,
            "ValueError": 0.6, "AttributeError": 0.6, "ImportError": 0.9,
            "ModuleNotFoundError": 0.9, "ZeroDivisionError": 0.7,
            "RecursionError": 0.3, "TimeoutError": 0.3,
            "AssertionError": 0.2,
        }.get(error_type, 0.5)

        # Adjust by code delta size
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

    # ── Core recording ──────────────────────────────────────────────────

    def record_error(self, error_text: str, context: str = "", code: str = "") -> Dict:
        """Record an error observation.

        Only updates EXISTING verified patterns (times_fixed > 0).
        Does NOT create new patterns — unverified errors are not stored.
        A pattern only enters the graph when it earns a verified fix.
        """
        err_type, err_sig, failing_line = extract_error_fingerprint(error_text)

        for p in self.by_type.get(err_type, []):
            if self._same_pattern(p.error_signature, err_sig):
                p.times_seen += 1
                # NOTE: We do NOT decay confidence here. The only penalty is
                # targeted decay in record_toolbox_failure — only patterns that
                # were actually shown in the toolbox and still failed get penalized.
                # This is the most precise feedback loop possible.
                self._dirty = True
                return {"type": err_type, "sig": err_sig, "line": failing_line,
                        "locality": p.locality, "existing": True}

        # No matching verified pattern exists — do not create one.
        # The graph only stores fixes that have been proven.
        return {"type": err_type, "sig": err_sig, "line": failing_line,
                "locality": self._compute_locality(err_type, None), "existing": False}

    def record_fix(self, error_text: str, failing_code: str = "", fixed_code: str = ""):
        err_type, err_sig, failing_line = extract_error_fingerprint(error_text)
        delta = self._code_delta(failing_code, fixed_code)
        locality = self._compute_locality(err_type, delta)

        # Extract a concise context snippet from failing_code (the problematic function)
        context_snippet = ""
        if failing_code:
            lines = failing_code.strip().split("\n")
            context_snippet = "; ".join(l.strip() for l in lines if l.strip())[:200]

        matched = None
        is_new_pattern = False
        for p in self.by_type.get(err_type, []):
            if self._same_pattern(p.error_signature, err_sig):
                p.times_fixed += 1
                p.confidence = min(1.0, p.confidence + 0.1)  # +0.1 absolute for verified fix
                # v3.0: Dynamic locality — learn from actual fix complexity
                actual_complexity = self._fix_complexity(delta)
                # Adjust locality toward evidence: 1-line fix → more local; multi-line → less local
                if actual_complexity == 1:
                    p.locality = min(1.0, p.locality + 0.15)  # strong local evidence
                elif actual_complexity <= 3:
                    p.locality = (p.locality + locality) / 2  # average with theoretical
                else:
                    p.locality = max(0.0, p.locality - 0.2)   # structural fix evidence
                # Backfill failing_line if it was previously empty
                if not p.failing_line and failing_line:
                    p.failing_line = failing_line
                if not p.context and context_snippet:
                    p.context = context_snippet
                # NOTE: fix_strategy is NOT overwritten. A pattern's fix strategy
                # is immutable — it earned verification with that strategy. Overwriting
                # it with a different fix would pollute the proven pattern.
                matched = p
                break

        if not matched:
            # New pattern discovered by the LLM
            is_new_pattern = True
            fix = delta if delta else infer_fix_strategy(err_type, err_sig)
            matched = ErrorPatternNode(err_type, err_sig, failing_line, fix, context_snippet, locality)
            matched.confidence = 0.5  # starts equal
            matched.times_fixed = 1
            self.patterns.append(matched)
            self.by_type[err_type].append(matched)

        self._omega_revision(matched, locality)
        self._dirty = True
        
        # Reset toolbox failure counter — the conscious has succeeded, crisis is over
        if err_type in self._toolbox_failures:
            del self._toolbox_failures[err_type]

    def _fix_complexity(self, code_delta: str) -> int:
        """Count number of structural changes in a fix. Used for dynamic λ adjustment."""
        if not code_delta:
            return 1
        changes = code_delta.count("Changed:") + code_delta.count("Added:") + code_delta.count("Removed:")
        return max(1, changes)  # at minimum 1 change

    def _reassembly(self, error_type: str):
        """
        Reassembly: the unconscious surfacing in layers.

        Not all repressed material returns with equal force. Patterns surface
        proportionally to their prior standing — near-conscious patterns get
        a gentle nudge, deep unconscious patterns get a tiny lifeline, shadows
        are remembered but surface weakest of all.

        Nothing is ever truly forgotten. Even pure trauma stays in the graph,
        but it must earn its way back through actual success. The shadow gets
        the faintest whisper of a second chance.

        Tier 1 (established): confidence >= 0.7, fixed >= 3
            → gentle reset toward 0.5: loses 0.15-0.20, stays above 0.55

        Tier 2 (middling): confidence >= 0.5
            → standard reset to 0.5

        Tier 3 (buried): confidence < 0.5, has at least 1 fix
            → small boost toward 0.3-0.4

        Tier 4 (shadow): confidence < 0.3, no fixes yet
            → faintest whisper: 0.2
            Rationale: remembered, not erased. Must prove itself from near-zero.
        """
        tier_1 = tier_2 = tier_3 = tier_4 = 0
        for p in self.by_type.get(error_type, []):
            old_conf = p.confidence
            if p.confidence >= 0.7 and p.times_fixed >= 3:
                p.confidence = max(0.55, p.confidence - 0.15)
                tier_1 += 1
            elif p.confidence >= 0.5:
                p.confidence = 0.5
                tier_2 += 1
            elif p.times_fixed > 0:
                p.confidence = max(0.3, min(0.4, p.confidence + 0.1))
                tier_3 += 1
            else:
                # Shadow: pure trauma, but remembered. Faintest whisper.
                p.confidence = 0.2
                tier_4 += 1

        total = tier_1 + tier_2 + tier_3 + tier_4
        if total > 0:
            tiers = []
            if tier_1: tiers.append(f"established={tier_1}")
            if tier_2: tiers.append(f"middling={tier_2}")
            if tier_3: tiers.append(f"buried={tier_3}")
            if tier_4: tiers.append(f"shadow={tier_4}")
            print(f"    [REASSEMBLY] {error_type}: {total} patterns — {', '.join(tiers)}")

    def _omega_revision(self, confirmed_pattern: ErrorPatternNode, locality: float):
        """Omega-based belief revision: boost confidence of related patterns."""
        for etype, plist in self.by_type.items():
            for p in plist:
                if p is confirmed_pattern:
                    continue
                # Similarity across signature
                sig_sim = self._sig_similarity(p.error_signature, confirmed_pattern.error_signature)
                # Similarity across locality
                loc_sim = 1.0 - abs(p.locality - locality)
                # Structural similarity: same error type
                type_bonus = 0.3 if p.error_type == confirmed_pattern.error_type else 0.0

                relatedness = (sig_sim * 0.5 + loc_sim * 0.3 + type_bonus * 0.2)
                if relatedness > 0.4:
                    boost = self.omega * relatedness * 0.15
                    p.confidence = min(1.0, p.confidence + boost)

    def _code_delta(self, old: str, new: str) -> str:
        """Extract a simple, readable transformation from old code to new code."""
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

    # ── Toolbox: Local vs Unlocal ──────────────────────────────────────

    def get_coherent_toolbox(self, error_text: str, failing_code: str = "",
                              top_k: int = 3,
                              min_confidence: float = 0.5,
                              max_confidence: float = 1.0,
                              llm_client = None) -> Tuple[str, List[ErrorPatternNode]]:
        """
        v3.5: Natural-language knowledge browser.

        No fingerprint scoring. No cross-function penalty. No template-based
        "coherent picture" injection. Just verified examples the LLM can read
        and decide for itself what applies.

        Returns: (toolbox_text, shown_patterns)
        """
        err_type, err_sig, failing_line = extract_error_fingerprint(error_text)

        # ── Gather ALL verified same-error-type patterns meeting confidence threshold ──
        candidates = []
        for p in self.by_type.get(err_type, []):
            if p.times_fixed > 0 and min_confidence <= p.confidence < max_confidence:
                candidates.append(p)

        if not candidates:
            return "", []

        # Sort by confidence (highest first) and take top_k
        candidates.sort(key=lambda p: -p.confidence)
        shown = candidates[:top_k]

        # ── Build natural-language prompt ──
        lines = [
            f"[Knowledge Base — Past verified fixes for {err_type}]",
            f"Your current error: {err_sig[:120]}",
            "",
        ]

        for i, p in enumerate(shown, 1):
            # Extract a readable problem description from the pattern
            func_name = self._extract_func_name(p.failing_line) or "function"
            fix_desc = p.fix_strategy[:150] if p.fix_strategy else "(no description)"
            context_hint = f"Context: {p.context[:80]}..." if p.context else ""

            lines.append(
                f"  Pattern {i}:\n"
                f"    Problem: {func_name} — {p.error_signature[:100]}\n"
                f"    Fix applied: {fix_desc}\n"
                f"{f'    {context_hint}' if context_hint else ''}"
            )

        lines.append("")
        lines.append(
            "Use the relevant patterns above to fix your code. "
            "Apply what worked before for similar errors."
        )

        toolbox_text = "\n".join(lines)
        return toolbox_text, shown

    # ── Similarity helpers ─────────────────────────────────────────────

    def _same_pattern(self, sig1: str, sig2: str) -> bool:
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

    def _sig_similarity(self, sig1: str, sig2: str) -> float:
        """Compute token overlap between two error signatures."""
        s1 = sig1.replace("'", "").replace('"', '').lower()
        s2 = sig2.replace("'", "").replace('"', '').lower()
        if s1 == s2:
            return 1.0
        t1, t2 = set(s1.split()), set(s2.split())
        if not t1 or not t2:
            return 0.0
        inter = len(t1 & t2)
        return inter / len(t1 | t2)

    def _extract_func_name(self, line: str) -> Optional[str]:
        """Extract function name from an assert/test line."""
        if not line:
            return None
        m = re.search(r'(\w+)\s*\(', line.strip().lower())
        return m.group(1) if m else None

    # ── Stats / persistence ────────────────────────────────────────────

    def stats(self) -> Dict:
        if not self.patterns:
            return {"n_patterns": 0, "total_seen": 0, "total_fixed": 0, "patterns": []}
        by_type = defaultdict(int)
        by_locality = {"local": 0, "unlocal": 0, "mixed": 0}
        for p in self.patterns:
            by_type[p.error_type] += 1
            if p.locality >= 0.6:
                by_locality["local"] += 1
            elif p.locality <= 0.4:
                by_locality["unlocal"] += 1
            else:
                by_locality["mixed"] += 1
        return {
            "n_patterns":     len(self.patterns),
            "by_type":        dict(by_type),
            "by_locality":    by_locality,
            "omega":          self.omega,
            "total_seen":     sum(p.times_seen for p in self.patterns),
            "total_fixed":    sum(p.times_fixed for p in self.patterns),
            "avg_confidence": sum(p.confidence for p in self.patterns) / len(self.patterns),
            "avg_locality":   sum(p.locality for p in self.patterns) / len(self.patterns),
            "patterns":       [p.to_dict() for p in self.patterns]
        }

    def print_summary(self):
        print(f"\n{bold('Coherent Knowledge Graph')} ({len(self.patterns)} patterns, Ω={self.omega}):")
        if not self.patterns:
            print("  (empty)")
            return
        for p in sorted(self.patterns, key=lambda x: -x.confidence):
            status = green("VERIFIED") if p.times_fixed > 0 else yellow("unverified")
            loc_label = green("local") if p.locality >= 0.6 else (red("unlocal") if p.locality <= 0.4 else yellow("mixed"))
            print(f"  [{p.error_type}] λ={p.locality:.1f} [{loc_label}] {p.error_signature[:50]}")
            if p.failing_line:
                print(f"    Line: {p.failing_line[:60]}")
            print(f"    Fix: {p.fix_strategy[:70]}...")
            print(f"    Confidence: {p.confidence:.2f} | {status} | seen {p.times_seen}x, fixed {p.times_fixed}x")

    def _save(self):
        """Write to disk only if data has changed."""
        if not self._dirty:
            return
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump({"patterns": [p.to_dict() for p in self.patterns]}, f, indent=2)
            self._dirty = False
        except Exception:
            pass

    def flush(self):
        """Force immediate save to disk."""
        self._save()

    def _load(self):
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for pd in data.get("patterns", []):
                    node = ErrorPatternNode.from_dict(pd)
                    self.patterns.append(node)
                    self.by_type[node.error_type].append(node)
        except Exception:
            pass

    def record_toolbox_failure(self, shown_patterns: List[ErrorPatternNode], decay: float = 0.8):
        """
        Penalize ONLY the specific patterns that were shown in the toolbox
        but whose fix attempt still failed. Multiplicative decay (× 0.8).
        
        Tracks consecutive toolbox failures per error type. After 3 failures,
        reassembly fires — the unconscious surfaces with alternative patterns.
        """
        if not shown_patterns:
            return
        for p in shown_patterns:
            p.confidence *= decay  # no floor — fades toward 0 but never reaches it
        types = set(p.error_type for p in shown_patterns)
        print(f"    [PENALTY] {', '.join(types)}: {len(shown_patterns)} specific patterns decayed × {decay}")
        
        # Track consecutive toolbox failures — Jungian unconscious surfacing
        for err_type in types:
            self._toolbox_failures[err_type] += 1
            if self._toolbox_failures[err_type] >= 3:
                print(f"    [CRISIS] {err_type}: {self._toolbox_failures[err_type]} toolbox failures. Unconscious surfacing...")
                self._reassembly(err_type)
                self._toolbox_failures[err_type] = 0  # reset after reassembly
        
        self._dirty = True


# ═══════════════════════════════════════════════════════════════════════
#  4.  LLM CLIENT
# ═══════════════════════════════════════════════════════════════════════

class LMStudioClient:
    EMPIRICAL_SYSTEM_PROMPT = "You are a helpful coding assistant. Write clean, correct Python code."

    def __init__(self, base_url="http://localhost:1234/v1", model=None, timeout=300):
        self.base_url      = base_url.rstrip("/")
        self.model         = model
        self.timeout       = timeout
        self.chat_endpoint = f"{self.base_url}/chat/completions"

    def generate(self, prompt, system_message=None, temperature=0.0, max_tokens=1024, n=1):
        import requests
        messages = [
            {"role": "system", "content": system_message or self.EMPIRICAL_SYSTEM_PROMPT},
            {"role": "user",   "content": prompt}
        ]
        candidates = []
        for _ in range(n):
            payload = {
                "model": self.model or "local-model",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False
            }
            data = None
            for attempt in range(3):
                try:
                    response = requests.post(self.chat_endpoint, json=payload,
                                              timeout=self.timeout)
                    response.raise_for_status()
                    data = response.json()
                    break
                except requests.exceptions.ReadTimeout:
                    print(yellow(f"  [Timeout] Retry {attempt+1}/3..."))
                    time.sleep(2 ** attempt)
                    if attempt == 2:
                        candidates.append("")
                        break
                except Exception as e:
                    print(red(f"  [Error] {e}"))
                    candidates.append("")
                    break
            else:
                if data is None:
                    candidates.append("")
                    continue
            if data is None:
                continue
            msg = data["choices"][0]["message"]
            content = msg.get("content", "")
            if not content.strip() and "reasoning_content" in msg:
                content = msg["reasoning_content"]
            if not content.strip() and "reasoning" in msg:
                content = msg["reasoning"]
            content = self._strip_think_tags(content)
            candidates.append(content)
        return candidates

    def _strip_think_tags(self, text):
        if not text:
            return ""
        text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)
        text = re.sub(r" thinking.*?end thinking ", "", text, flags=re.DOTALL)
        return text.strip()

    def check_health(self):
        try:
            import requests
            return requests.get(f"{self.base_url}/models", timeout=5).status_code == 200
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════════
#  5.  CORE AGENT
# ═══════════════════════════════════════════════════════════════════════

class PuzzleLogicAgent:
    def __init__(self, model: str, knowledge_path: str = "puzzle_logic_knowledge.json"):
        self.synapse   = LMStudioClient(model=model)
        self.knowledge = CoherentKnowledgeGraph(storage_path=knowledge_path)
        self.logger    = None

    # ── Unified solve method (all three modes) ──────────────────────────

    def solve(self, prompt: str, test_code: str = None, n_attempts: int = 3,
              max_tokens: int = 1024, task_id: str = "task",
              mode: str = "advanced") -> Dict:
        """
        mode = "baseline"  → clean attempts, no error info
        mode = "basic"     → raw error + strategy rotation (Basic V2)
        mode = "advanced"  → coherent knowledge graph (Advanced V2)
        """
        print(f"\n{bold('[Puzzle Logic]')} {cyan(task_id)}  [mode={mode}]")
        print(f"  Knowledge: {len(self.knowledge.patterns)} patterns | Ω={self.knowledge.omega}")

        failure_history   = []
        last_error        = ""
        last_failing_code = ""
        used_toolbox      = False
        shown_patterns    = []  # patterns shown in toolbox for current attempt
        tracker = AttemptTracker() if mode == "basic" else None

        for attempt in range(1, n_attempts + 1):
            full_prompt = prompt
            shown_patterns = []  # reset each attempt

            # ── Build the retry prompt based on mode ─────────────────────
            if failure_history and last_error:
                if mode == "baseline":
                    pass  # no error info, just retry clean

                elif mode == "basic":
                    # Basic V2: raw error + strategy rotation hint
                    rotation = tracker.get_rotation_hint() if tracker else ""
                    full_prompt = (
                        prompt + "\n\n"
                        f"[Previous attempt FAILED with this error:]\n"
                        f"```\n{last_error}\n```\n"
                        f"Fix the code based on this error message.{rotation}"
                    )

                elif mode == "advanced":
                    # Advanced V2: coherent knowledge graph toolbox
                    toolbox_text, shown_patterns = self.knowledge.get_coherent_toolbox(last_error, top_k=3)
                    full_prompt = prompt + "\n\n" + toolbox_text + "\n"
                    used_toolbox = True

            print(f"\n  {yellow('[Attempt ' + str(attempt) + ']')} ", end="")
            if mode == "advanced" and used_toolbox:
                print(f"{yellow('[toolbox]')}")
            elif mode == "basic" and failure_history:
                print(f"{yellow('[raw error + rotation]')}")
            else:
                print(f"{cyan('[clean]')}")

            print(f"    -> LLM...", end=" ", flush=True)
            raw_list = self.synapse.generate(prompt=full_prompt, temperature=0.0,
                                              max_tokens=max_tokens, n=1)
            raw_text = raw_list[0] if raw_list else ""
            print("done")

            code = extract_code(raw_text)
            if not code:
                print(f"    {red('No code extracted')}")
                last_error = "extraction failed"
                self.knowledge.record_error("extraction failed")
                failure_history.append(last_error)
                if tracker:
                    tracker.record("extraction", "", "", False)
                continue

            print(f"    Code: {code.split(chr(10))[0][:60]}...")

            if test_code is None:
                return {"code": code, "passed": True, "attempts": attempt,
                        "error": None, "used_toolbox": used_toolbox, "patterns_learned": 0}

            test_program = prompt + "\n" + code + "\n" + test_code + "\n"
            print(f"    -> Exec...", end=" ", flush=True)
            result = execute_code(test_program)

            if result["passed"]:
                print(f"{green('PASS')}")
                if last_error:
                    self.knowledge.record_fix(last_error, failing_code=last_failing_code,
                                               fixed_code=code)
                if tracker:
                    tracker.record(extract_error_fingerprint(last_error)[0],
                                     last_failing_code, code, True)
                return {"code": code, "passed": True, "attempts": attempt,
                        "error": None, "used_toolbox": used_toolbox,
                        "patterns_learned": len(self.knowledge.patterns)}
            else:
                error_text = result.get("error", "unknown")
                print(f"{red('FAIL')} -- {yellow(error_text[:80])}")
                self.knowledge.record_error(error_text, context=prompt[:200], code=code)
                # Penalize ONLY the specific patterns shown in toolbox that didn't work
                if mode == "advanced" and used_toolbox and shown_patterns:
                    self.knowledge.record_toolbox_failure(shown_patterns)
                failure_history.append(error_text)
                if tracker:
                    tracker.record(extract_error_fingerprint(error_text)[0],
                                     last_failing_code, code, False)
                last_error = error_text
                last_failing_code = code

        print(f"\n  {red('All ' + str(n_attempts) + ' attempts failed.')}")
        return {"code": code if 'code' in dir() else "", "passed": False,
                "attempts": n_attempts, "error": last_error,
                "used_toolbox": used_toolbox,
                "patterns_learned": len(self.knowledge.patterns)}

    def show_stats(self):
        self.knowledge.print_summary()


# ═══════════════════════════════════════════════════════════════════════
#  6.  CLI
# ═══════════════════════════════════════════════════════════════════════

def print_banner():
    print(cyan(r"""
    ____       _       _         _            _   _
   |  _ \_   _| | __ _| | ____ _| | ___  __ _| |_(_) ___  _ __
   | |_) | | | | |/ _` | |/ / _` | |/ _ \/ _` | __| |/ _ \| '_ \
   |  __/| |_| | | (_| |   < (_| | |  __/ (_| | |_| | (_) | | | |
   |_|    \__, |_\__, |_|\_\__, |_|\___|\__,_|\__|_|\___/|_| |_|
          |___/    |___/    |___/
    ____                            _       _
   |  _ \  ___  _ __ ___   ___   __| |_   _| | ___  ___
   | | | |/ _ \| '_ ` _ \ / _ \ / _` | | | | |/ _ \/ __|
   | |_| | (_) | | | | | | (_) | (_| | |_| | |  __/\__ \
   |____/ \___/|_| |_| |_|\___/ \__,_|\__,_|_|\___||___/
    """))
    print(bold("    v2.4 -- Basic V2 (Strategy Rotation) + Advanced V2 (Omega + Coherence)\n"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", nargs="?")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--test", type=str, default=None)
    parser.add_argument("--generate", type=str, default=None)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--knowledge", type=str, default="puzzle_logic_knowledge.json")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--mode", type=str, default="advanced", choices=["baseline", "basic", "advanced"],
                        help="Mode: baseline | basic | advanced")
    args = parser.parse_args()

    print_banner()

    if args.stats:
        agent = PuzzleLogicAgent(model="", knowledge_path=args.knowledge)
        agent.show_stats()
        return

    model = args.model
    if not model:
        try:
            import requests
            r = requests.get("http://localhost:1234/v1/models", timeout=5)
            model = r.json()["data"][0]["id"]
            print(f"Auto-detected: {bold(model)}")
        except Exception:
            print(red("[Error] Model not detected. Start LM Studio server."))
            sys.exit(1)

    agent = PuzzleLogicAgent(model=model, knowledge_path=args.knowledge)
    if not agent.synapse.check_health():
        print(red("[Error] LM Studio not running on localhost:1234"))
        sys.exit(1)
    print(green("LM Studio connected OK"))

    if args.generate:
        # Generate mode: just use baseline
        result = agent.solve(args.generate, n_attempts=1, max_tokens=args.max_tokens, mode="baseline")
        print(result.get("code", "(no code)"))
        return

    if args.file:
        if not os.path.exists(args.file):
            print(red(f"[Error] File not found: {args.file}"))
            sys.exit(1)
        # For file fixing, read the file content as prompt
        with open(args.file, "r", encoding="utf-8") as f:
            code = f.read()
        test_code = None
        if args.test and os.path.exists(args.test):
            with open(args.test, "r", encoding="utf-8") as f:
                test_code = f.read()
        result = agent.solve(code, test_code=test_code, n_attempts=args.attempts,
                             max_tokens=args.max_tokens, mode=args.mode)
        print(f"\n{bold('=' * 60)}")
        if result["passed"]:
            print(f"{green('SUCCESS')} in {result['attempts']} attempt(s)")
        else:
            print(f"{red('FAILED')} after {result['attempts']} attempt(s)")
        if result.get("code"):
            print(result["code"])
        age