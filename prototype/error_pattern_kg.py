"""
Error-Pattern Knowledge Graph
=============================

Learns from compilation/execution failures, not just successes.
When a solution fails, this graph extracts the error signature and
stores how it was eventually resolved.

Key insight: The compiler IS the constraint engine. Its output tells us
exactly what's wrong. We use that output to find relevant fix patterns.

Flow:
  1. Problem fails with error E
  2. Extract error fingerprint (type, missing symbol, context)
  3. Search graph: "Have we seen error E before?"
  4. If yes → inject the fix pattern as hint
  5. If no → record error E, try generic fix strategies
  6. When eventually resolved → store (error E → fix pattern) as validated edge

This is domain-independent. NameError, TypeError, IndexError — the graph
learns the structural fix for each error class.
"""

import re
import json
import os
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
from datetime import datetime


class ErrorPatternNode:
    """
    A validated error-fix pattern.
    
    Not full code — just the STRUCTURAL LESSON:
    - What error occurred?
    - What was the root cause category?
    - What fix strategy resolved it?
    """

    def __init__(self, error_type: str, error_signature: str,
                 fix_strategy: str, confidence: float = 1.0,
                 context: str = ""):
        self.error_type = error_type          # "NameError", "TypeError", "SyntaxError"
        self.error_signature = error_signature  # "name 'X' is not defined"
        self.fix_strategy = fix_strategy      # "Ensure function name matches test"
        self.confidence = confidence          # 1.0 = first-try fix worked
        self.context = context                # Problem domain hint
        self.times_seen = 1
        self.times_fixed = 0
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return {
            "error_type": self.error_type,
            "error_signature": self.error_signature,
            "fix_strategy": self.fix_strategy,
            "confidence": self.confidence,
            "context": self.context,
            "times_seen": self.times_seen,
            "times_fixed": self.times_fixed,
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> "ErrorPatternNode":
        n = cls(
            error_type=d["error_type"],
            error_signature=d["error_signature"],
            fix_strategy=d["fix_strategy"],
            confidence=d.get("confidence", 1.0),
            context=d.get("context", ""),
        )
        n.times_seen = d.get("times_seen", 1)
        n.times_fixed = d.get("times_fixed", 0)
        n.timestamp = d.get("timestamp", datetime.now().isoformat())
        return n


def extract_error_fingerprint(error_text: str) -> Tuple[str, str]:
    """
    Extract the structural fingerprint from a Python error.
    Returns: (error_type, normalized_signature)
    """
    if not error_text:
        return ("Unknown", "empty error")
    
    error_lower = error_text.lower()
    
    # NameError: name 'X' is not defined
    match = re.search(r"NameError:\s*name\s*['\"](\w+)['\"]\s*is not defined", error_text)
    if match:
        return ("NameError", f"name '{match.group(1)}' not defined")
    
    # NameError (generic)
    if "NameError" in error_text:
        return ("NameError", "undefined name")
    
    # TypeError
    match = re.search(r"TypeError:\s*(.+?)(?:\n|$)", error_text)
    if match:
        return ("TypeError", match.group(1).strip())
    
    # SyntaxError
    match = re.search(r"SyntaxError:\s*(.+?)(?:\n|$)", error_text)
    if match:
        return ("SyntaxError", match.group(1).strip())
    
    # AssertionError (wrong answer)
    if "AssertionError" in error_text or "assert" in error_lower:
        return ("AssertionError", "wrong output")
    
    # IndexError
    if "IndexError" in error_text:
        return ("IndexError", "index out of range")
    
    # KeyError
    if "KeyError" in error_text:
        match = re.search(r"KeyError:\s*['\"]?(\w+)['\"]?", error_text)
        if match:
            return ("KeyError", f"key '{match.group(1)}' not found")
        return ("KeyError", "missing key")
    
    # ImportError
    if "ImportError" in error_text or "ModuleNotFoundError" in error_text:
        return ("ImportError", "module not found")
    
    # IndentationError
    if "IndentationError" in error_text:
        return ("IndentationError", "bad indentation")
    
    # Timeout
    if "timeout" in error_lower:
        return ("Timeout", "execution timed out")
    
    # Generic
    first_line = error_text.split("\n")[0][:80]
    return ("Other", first_line)


def infer_fix_strategy(error_type: str, error_sig: str, 
                       problem_text: str, code: str) -> str:
    """
    Infer the fix strategy from the error and context.
    This is the 'lesson learned' — not code, but the structural fix.
    """
    strategies = []
    
    # Handle TypeError with wrong argument count (highest impact pattern)
    if error_type == "TypeError" and "takes" in error_sig and "argument" in error_sig:
        # Extract the numbers: "takes 2 positional arguments but 3 were given"
        match = re.search(r"takes\s+(\d+).*?but\s+(\d+)\s+were", error_sig)
        if match:
            defined = match.group(1)
            called = match.group(2)
            strategies.append(
                f"FUNCTION SIGNATURE MISMATCH: Your function takes {defined} arguments "
                f"but the test calls it with {called}. "
                f"Look at the assert statement in the test to see exactly how many "
                f"arguments the test expects, then update your function's def line to match."
            )
        else:
            strategies.append("FUNCTION SIGNATURE MISMATCH: The test calls your function with a different number of arguments than you defined. Check the assert statement and update your function signature.")
    
    elif error_type == "TypeError":
        if "'NoneType'" in error_sig:
            strategies.append("Function returns None instead of correct value. Ensure all code paths have a return statement.")
        elif "not subscriptable" in error_sig:
            strategies.append("Trying to index something that isn't a list/tuple. Check the data type before indexing.")
        elif "not iterable" in error_sig:
            strategies.append("Trying to loop over a non-iterable value. Check that the input is a list/string before iterating.")
        else:
            strategies.append("Type mismatch: check that the function handles the expected input types correctly.")
    
    elif error_type == "NameError":
        # Common cause: function name doesn't match what test expects
        strategies.append("Ensure the function name exactly matches what the test expects. Check the assert statement for the correct function name.")
    
    elif error_type == "TypeError":
        if "takes" in error_sig and "positional argument" in error_sig:
            strategies.append("Check function signature: wrong number of arguments. Count the parameters in the test calls.")
        elif "'NoneType'" in error_sig:
            strategies.append("Function returns None instead of correct value. Ensure all code paths have a return statement.")
        elif "not subscriptable" in error_sig:
            strategies.append("Trying to index something that isn't a list/tuple. Check the data type before indexing.")
        elif "not iterable" in error_sig:
            strategies.append("Trying to loop over a non-iterable value. Check that the input is a list/string before iterating.")
        else:
            strategies.append("Type mismatch: check that the function handles the expected input types correctly.")
    
    elif error_type == "SyntaxError":
        strategies.append("Syntax error in the code. Check for missing colons, mismatched parentheses, or incorrect indentation.")
    
    elif error_type == "AssertionError":
        strategies.append("Logic error: function runs but returns wrong value. Trace through the algorithm step by step with the test input.")
    
    elif error_type == "IndexError":
        strategies.append("Index out of range. Check for empty lists or loop bounds that exceed the list length.")
    
    elif error_type == "IndentationError":
        strategies.append("Fix indentation: Python requires consistent indentation (usually 4 spaces).")
    
    else:
        strategies.append(f"Error type {error_type}: review the error message carefully and compare your code with the expected behavior.")
    
    return " ".join(strategies)


class ErrorPatternGraph:
    """
    Graph of error patterns and their validated fixes.
    Learns empirically: every error teaches a lesson.
    """

    def __init__(self, storage_path: str = "error_patterns.json"):
        self.storage_path = storage_path
        self.patterns: List[ErrorPatternNode] = []
        # Index by error type for fast lookup
        self.by_type: Dict[str, List[ErrorPatternNode]] = defaultdict(list)
        self._load()
    
    def record_error(self, error_text: str, problem_text: str = "", 
                     code: str = "") -> str:
        """
        Record an error occurrence. Returns the error fingerprint for matching.
        """
        err_type, err_sig = extract_error_fingerprint(error_text)
        
        # Check if we've seen this exact pattern
        for p in self.by_type.get(err_type, []):
            if self._similar_error(p.error_signature, err_sig):
                p.times_seen += 1
                p.confidence *= 0.95  # Decay slightly on repeated failure
                self._save()
                return f"{err_type}: {err_sig}"
        
        # New error pattern
        fix = infer_fix_strategy(err_type, err_sig, problem_text, code)
        node = ErrorPatternNode(
            error_type=err_type,
            error_signature=err_sig,
            fix_strategy=fix,
            context=problem_text[:100] if problem_text else ""
        )
        self.patterns.append(node)
        self.by_type[err_type].append(node)
        self._save()
        return f"{err_type}: {err_sig}"
    
    def record_fix(self, error_text: str, problem_text: str = ""):
        """
        Call this when an error was eventually fixed (problem passed).
        Increases confidence of the fix strategy.
        """
        err_type, err_sig = extract_error_fingerprint(error_text)
        for p in self.by_type.get(err_type, []):
            if self._similar_error(p.error_signature, err_sig):
                p.times_fixed += 1
                p.confidence = min(1.0, p.confidence + 0.1)
                self._save()
                return
    
    def get_fix_toolbox(self, error_text: str, top_k: int = 3) -> str:
        """
        Retrieve a toolbox of relevant error-fix patterns.
        
        NOT a directive — the model must evaluate each piece and decide
        whether it structurally fits the current problem.
        
        Format: "Here are past errors similar to yours. Review each,
        decide if it applies, then write your solution."
        """
        err_type, err_sig = extract_error_fingerprint(error_text)
        
        candidates = []
        for p in self.by_type.get(err_type, []):
            sim = self._error_similarity(p.error_signature, err_sig)
            if sim > 0.3:  # Lower threshold — show more options, let model decide
                candidates.append((sim * p.confidence, p))
        
        # Cross-type check
        for etype, plist in self.by_type.items():
            if etype == err_type:
                continue
            for p in plist:
                sim = self._error_similarity(p.error_signature, err_sig)
                if sim > 0.7:
                    candidates.append((sim * p.confidence * 0.6, p))
        
        candidates.sort(key=lambda x: -x[0])
        
        if not candidates:
            return (
                f"[Error knowledge base: no prior patterns for {err_type}]\n"
                f"This appears to be a new error type. Analyze the error message "
                f"carefully and determine the root cause yourself."
            )
        
        lines = [
            f"[Error knowledge base: {err_type} — {len(candidates)} related patterns found]",
            "Below are past errors and their validated fixes. REVIEW EACH and decide",
            "whether it structurally fits YOUR current problem. Use none, one, or combine.",
            "Do NOT blindly apply — evaluate fit like a puzzle piece.",
            ""
        ]
        
        for i, (score, pattern) in enumerate(candidates[:top_k], 1):
            relevance = "high" if score > 0.7 else ("medium" if score > 0.4 else "low")
            lines.append(
                f"  Pattern {i} [relevance: {relevance}, validated {pattern.times_fixed}x]:\n"
                f"    Past error: [{pattern.error_type}] {pattern.error_signature}\n"
                f"    Validated fix: {pattern.fix_strategy}\n"
            )
        
        lines.append(
            "\nNow analyze YOUR error and decide which pattern (if any) applies. "
            "Then write the corrected function."
        )
        
        return "\n".join(lines)
    
    def _similar_error(self, sig1: str, sig2: str) -> bool:
        """Check if two error signatures describe the same root cause."""
        # Exact match
        if sig1 == sig2:
            return True
        # Same error name
        s1 = sig1.replace("'", "").replace('"', '').lower()
        s2 = sig2.replace("'", "").replace('"', '').lower()
        if s1 == s2:
            return True
        # Shared word tokens (e.g., "name X not defined" vs "name Y not defined")
        tokens1 = set(s1.split())
        tokens2 = set(s2.split())
        shared = tokens1 & tokens2
        if len(shared) >= min(len(tokens1), len(tokens2)) * 0.6:
            return True
        return False
    
    def _error_similarity(self, sig1: str, sig2: str) -> float:
        """Compute similarity score between error signatures."""
        s1 = sig1.replace("'", "").replace('"', '').lower()
        s2 = sig2.replace("'", "").replace('"', '').lower()
        if s1 == s2:
            return 1.0
        tokens1 = set(s1.split())
        tokens2 = set(s2.split())
        if not tokens1 or not tokens2:
            return 0.0
        jaccard = len(tokens1 & tokens2) / len(tokens1 | tokens2)
        return jaccard
    
    def get_stats(self) -> Dict:
        if not self.patterns:
            return {"n_patterns": 0}
        
        by_type_count = defaultdict(int)
        for p in self.patterns:
            by_type_count[p.error_type] += 1
        
        return {
            "n_patterns": len(self.patterns),
            "by_type": dict(by_type_count),
            "avg_confidence": sum(p.confidence for p in self.patterns) / len(self.patterns),
            "top_patterns": [
                {"error": p.error_signature, "fix": p.fix_strategy[:60], 
                 "confidence": round(p.confidence, 2), "seen": p.times_seen}
                for p in sorted(self.patterns, key=lambda x: -x.confidence)[:5]
            ]
        }
    
    def print_graph(self):
        print(f"\nError Pattern Graph ({len(self.patterns)} patterns):")
        if not self.patterns:
            print("  (empty)")
            return
        for p in sorted(self.patterns, key=lambda x: -x.confidence):
            print(f"  [{p.error_type}] {p.error_signature[:40]}")
            print(f"    Fix: {p.fix_strategy[:60]}...")
            print(f"    Confidence: {p.confidence:.2f} | Seen: {p.times_seen}")
    
    def _save(self):
        data = {"patterns": [p.to_dict() for p in self.patterns]}
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass  # Don't crash on save failure
    
    def _load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for pd in data.get("patterns", []):
                        node = ErrorPatternNode.from_dict(pd)
                        self.patterns.append(node)
                        self.by_type[node.error_type].append(node)
            except Exception:
                pass
