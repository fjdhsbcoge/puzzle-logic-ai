"""
Mistake-Pattern Knowledge Graph
=================================

Watches the model fail, categorizes failures, extracts prevention rules.
RULE: Only injects a prevention hint after the SECOND failure of the same type
on the same problem. This avoids prompt bloat while helping when the model
is genuinely stuck.

Design:
  1. First failure: try again with generic feedback (no KG injection)
  2. Second failure of same type: retrieve prevention rule from KG, inject it
  3. Prevention rules accumulate across all problems (domain-independent)
"""

import json
import os
import re
from typing import Dict, List, Optional, Any
from datetime import datetime


# Failure categories and their prevention rules
FAILURE_CATEGORIES = {
    "empty_input": {
        "patterns": ["empty list", "empty string", "empty tuple", "index out of range", "sequence has no elements"],
        "prevention_rule": "Always check if input is empty or None at the start of the function and return a sensible default.",
        "examples": ["if not items: return []", "if not s: return 0", "if text is None: return ''"],
    },
    "type_mismatch": {
        "patterns": ["unsupported operand type", "can only concatenate", "not supported between instances", "type error", "expected str"],
        "prevention_rule": "Verify the types of inputs before operations. Convert or guard if mixed types are possible.",
        "examples": ["ensure all elements are int", "convert to str before concatenation"],
    },
    "off_by_one": {
        "patterns": ["index out of range", "list index out of range", "string index out of range"],
        "prevention_rule": "Double-check all indices and loop bounds. Use len()-1 for last element, and guard empty sequences.",
        "examples": ["range(len(arr)-1)", "check index < len(arr)"],
    },
    "none_return": {
        "patterns": ["typeerror: 'nonetype'", "cannot unpack non-iterable", "none has no"],
        "prevention_rule": "Ensure all code paths return a value. If returning early, return the expected type.",
        "examples": ["if not found: return -1", "initialize result before conditions"],
    },
    "zero_division": {
        "patterns": ["division by zero", "zero divisor", "float division by zero"],
        "prevention_rule": "Check if denominator is zero before division. Return a default or raise an appropriate error.",
        "examples": ["if b == 0: return None", "handle zero case explicitly"],
    },
    "name_error": {
        "patterns": ["nameerror", "is not defined", "undefined variable"],
        "prevention_rule": "Verify all variables are initialized before use. Check for typos and scoping issues.",
        "examples": ["initialize accumulator before loop", "check variable names for typos"],
    },
    "syntax_error_string": {
        "patterns": ["unterminated string literal", "eol while scanning string", "invalid character"],
        "prevention_rule": "Do not include explanatory text or thinking traces inside the code block. Output only clean Python code.",
        "examples": ["remove all comments and markdown", "no quotes around explanations"],
    },
    "syntax_error_indent": {
        "patterns": ["indentationerror", "unexpected indent", "unindent does not match"],
        "prevention_rule": "Ensure consistent indentation (4 spaces per level). Do not mix tabs and spaces.",
        "examples": ["use 4 spaces", "check for mixed tabs/spaces"],
    },
    "assertion_error": {
        "patterns": ["assertionerror", "assertion failed", "check() failed"],
        "prevention_rule": "The output does not match expected behavior. Re-read the problem requirements and all edge cases carefully.",
        "examples": ["check all edge cases", "verify return values match exactly"],
    },
    "timeout": {
        "patterns": ["timeout"],
        "prevention_rule": "The solution may have an infinite loop or be too slow. Check loop termination conditions and consider a more efficient algorithm.",
        "examples": ["ensure loop increments/decrements", "use memoization or iteration instead of deep recursion"],
    },
}


def categorize_error(error_text: str) -> Optional[str]:
    """
    Categorize an error message into a failure type.
    Returns category key or None if uncategorized.
    """
    if not error_text:
        return None
    
    error_lower = error_text.lower()
    
    # Score each category by number of matching patterns
    scores = {}
    for category, data in FAILURE_CATEGORIES.items():
        score = 0
        for pattern in data["patterns"]:
            if pattern.lower() in error_lower:
                score += 1
        if score > 0:
            scores[category] = score
    
    if not scores:
        return None
    
    # Return the category with the highest match score
    return max(scores.items(), key=lambda x: x[1])[0]


class MistakePattern:
    """A single validated mistake pattern learned from failures."""
    
    def __init__(self, category: str, prevention_rule: str, first_seen: str = ""):
        self.category = category
        self.prevention_rule = prevention_rule
        self.first_seen = first_seen
        self.times_seen = 1
        self.times_helped = 0
        self.last_seen = datetime.now().isoformat()
        self.problems_affected: List[str] = [first_seen] if first_seen else []
    
    def to_dict(self) -> Dict:
        return {
            "category": self.category,
            "prevention_rule": self.prevention_rule,
            "first_seen": self.first_seen,
            "times_seen": self.times_seen,
            "times_helped": self.times_helped,
            "last_seen": self.last_seen,
            "problems_affected": self.problems_affected,
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> "MistakePattern":
        mp = cls(
            category=d["category"],
            prevention_rule=d["prevention_rule"],
            first_seen=d.get("first_seen", ""),
        )
        mp.times_seen = d.get("times_seen", 1)
        mp.times_helped = d.get("times_helped", 0)
        mp.last_seen = d.get("last_seen", datetime.now().isoformat())
        mp.problems_affected = d.get("problems_affected", [])
        return mp


class MistakePatternKnowledgeGraph:
    """
    Stores mistake-prevention patterns learned empirically.
    
    RULE: A prevention rule is ONLY injected into the prompt after
    the SECOND failure of the same category on the same problem.
    This prevents prompt bloat while providing targeted help.
    """
    
    def __init__(self, storage_path: str = "mistake_patterns.json"):
        self.patterns: Dict[str, MistakePattern] = {}  # category -> MistakePattern
        self.storage_path = storage_path
        self._load()
    
    def record_failure(self, task_id: str, error_text: str) -> Optional[str]:
        """
        Record a failure. Return the category if recognized.
        """
        category = categorize_error(error_text)
        if not category:
            return None
        
        if category in self.patterns:
            # Existing pattern
            mp = self.patterns[category]
            mp.times_seen += 1
            mp.last_seen = datetime.now().isoformat()
            if task_id not in mp.problems_affected:
                mp.problems_affected.append(task_id)
        else:
            # New pattern
            prevention = FAILURE_CATEGORIES[category]["prevention_rule"]
            mp = MistakePattern(
                category=category,
                prevention_rule=prevention,
                first_seen=task_id,
            )
            self.patterns[category] = mp
            print(f"    [MP-KG] Learned NEW pattern: {category}")
        
        self._save()
        return category
    
    def get_prevention_hint(self, category: str) -> Optional[str]:
        """Get the prevention rule for a category if it exists."""
        if category in self.patterns:
            return self.patterns[category].prevention_rule
        return None
    
    def should_inject(self, failure_history: List[str]) -> Optional[str]:
        """
        Determine if a prevention hint should be injected.
        
        failure_history: list of error categories from previous attempts
        
        Returns: the prevention hint if:
          - Same category failed TWICE (or more)
          - AND we have a learned prevention rule for it
        
        Otherwise: None (do not inject, keep prompt clean)
        """
        if not failure_history:
            return None
        
        # Count occurrences of each category in failure history
        from collections import Counter
        counts = Counter(failure_history)
        
        # Find categories that have failed at least twice
        for category, count in counts.items():
            if count >= 2 and category in self.patterns:
                return self.patterns[category].prevention_rule
        
        return None
    
    def record_success_after_hint(self, category: str):
        """Mark that a prevention rule helped."""
        if category in self.patterns:
            self.patterns[category].times_helped += 1
            self._save()
    
    def get_stats(self) -> Dict:
        return {
            "n_patterns": len(self.patterns),
            "patterns": [p.to_dict() for p in self.patterns.values()],
        }
    
    def print_contents(self):
        """Print all learned mistake patterns."""
        print(f"\n{'='*60}")
        print(f"MISTAKE PATTERN KNOWLEDGE GRAPH ({len(self.patterns)} patterns)")
        print(f"{'='*60}")
        
        if not self.patterns:
            print("  (empty)")
            return
        
        for i, (cat, mp) in enumerate(self.patterns.items(), 1):
            print(f"\n--- Pattern {i}: {cat} ---")
            print(f"  Prevention: {mp.prevention_rule}")
            print(f"  Seen {mp.times_seen} times, helped {mp.times_helped} times")
            print(f"  Problems: {', '.join(mp.problems_affected)}")
        
        print(f"\n{'='*60}")
    
    def _save(self):
        data = {cat: mp.to_dict() for cat, mp in self.patterns.items()}
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    def _load(self):
        if os.path.exists(self.storage_path):
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.patterns = {cat: MistakePattern.from_dict(d) for cat, d in data.items()}
            print(f"  [MP-KG] Loaded {len(self.patterns)} mistake patterns from disk")
