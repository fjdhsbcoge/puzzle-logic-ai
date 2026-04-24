"""
Validated Knowledge Graph (Compact Pattern Edition)
====================================================

A knowledge store that ONLY accumulates empirically validated solutions.
Every entry passed the test suite. Nothing enters by assumption.

KEY DESIGN: Few-shot prompts use COMPACT PATTERNS, not full code.
Full solutions are stored for inspection but never injected into prompts.

Why: An 8B model gets confused when given full code from a different
problem. It anchors to wrong variable names and structure. A 1-2 line
pattern description gives the idea without the baggage.
"""

import json
import os
import re
import difflib
from typing import List, Dict, Any, Optional
from datetime import datetime


# Pattern templates derived from common programming approaches
PATTERN_TEMPLATES = {
    "iteration": "Iterate over a sequence, process each element.",
    "filter": "Filter elements from a sequence matching a condition.",
    "count": "Count elements in a sequence satisfying a condition.",
    "accumulate": "Accumulate a value while iterating (sum, product, etc.).",
    "transform": "Transform each element in a sequence (map operation).",
    "search": "Search for a specific element or condition in a sequence.",
    "set_membership": "Use a set for O(1) membership lookup.",
    "string_process": "Process characters in a string with conditionals.",
    "nested_loop": "Use nested iteration to check all pairs/triples.",
    "sort": "Sort a sequence based on a key function.",
    "group": "Group elements by a criterion.",
    "stack": "Use a stack (LIFO) to process nested or sequential data.",
    "state_machine": "Track state while iterating, update based on conditions.",
    "math_formula": "Apply a mathematical formula or calculation.",
    "recursive": "Break problem into smaller subproblems (recursion).",
    "two_pointer": "Use two indices from start/end converging inward.",
    "default_dict": "Use a default dict/counter to track frequencies.",
    "zip": "Combine multiple sequences element-wise (zip).",
    "slice": "Extract or manipulate subsequences (slicing).",
    "replace": "Replace elements matching a condition.",
}


class ValidatedSolution:
    """A single piece of empirically validated knowledge."""

    def __init__(self, task_id: str, problem_description: str, solution_code: str,
                 compact_pattern: str = "", reasoning_trace: str = "",
                 test_summary: str = "", attempts: int = 1):
        self.task_id = task_id
        self.problem_description = problem_description
        self.solution_code = solution_code
        self.compact_pattern = compact_pattern  # 1-2 line pattern (injected into prompts)
        self.reasoning_trace = reasoning_trace
        self.test_summary = test_summary
        self.attempts = attempts
        self.timestamp = datetime.now().isoformat()
        self.confidence = 1.0 / attempts
        self.access_count = 0

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "problem_description": self.problem_description,
            "solution_code": self.solution_code,
            "compact_pattern": self.compact_pattern,
            "reasoning_trace": self.reasoning_trace,
            "test_summary": self.test_summary,
            "attempts": self.attempts,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ValidatedSolution":
        s = cls(
            task_id=d["task_id"],
            problem_description=d["problem_description"],
            solution_code=d["solution_code"],
            compact_pattern=d.get("compact_pattern", ""),
            reasoning_trace=d.get("reasoning_trace", ""),
            test_summary=d.get("test_summary", ""),
            attempts=d.get("attempts", 1),
        )
        s.timestamp = d.get("timestamp", datetime.now().isoformat())
        s.confidence = d.get("confidence", 1.0)
        s.access_count = d.get("access_count", 0)
        return s


class ValidatedKnowledgeGraph:
    """
    Memory of the Puzzle Logic OS.

    Principle: ONLY validated knowledge enters. No assumptions.
    Full solutions stored for inspection, but prompts get compact patterns only.
    """

    def __init__(self, storage_path: str = "validated_knowledge.json"):
        self.solutions: List[ValidatedSolution] = []
        self.storage_path = storage_path
        self._load()

    def add_solution(self, task_id: str, problem_description: str, solution_code: str,
                     compact_pattern: str = "", reasoning_trace: str = "",
                     test_summary: str = "", attempts: int = 1):
        """
        Add a validated solution. Only call this AFTER the solution passed tests.
        If no compact_pattern is provided, one is auto-generated.
        """
        if not compact_pattern:
            compact_pattern = self._generate_pattern(problem_description, solution_code)

        solution = ValidatedSolution(
            task_id=task_id,
            problem_description=problem_description,
            solution_code=solution_code,
            compact_pattern=compact_pattern,
            reasoning_trace=reasoning_trace,
            test_summary=test_summary,
            attempts=attempts
        )

        for i, existing in enumerate(self.solutions):
            if existing.task_id == task_id:
                if solution.confidence > existing.confidence:
                    self.solutions[i] = solution
                self._save()
                return

        self.solutions.append(solution)
        self._save()

    def _generate_pattern(self, problem_description: str, solution_code: str) -> str:
        """Auto-generate a compact pattern from problem + code."""
        problem_lower = problem_description.lower()
        code_lower = solution_code.lower()

        # Check code for key constructs
        has_set = "set(" in code_lower or " in {" in code_lower
        has_dict = "dict" in code_lower or "{}" in code_lower
        has_nested = code_lower.count("for ") >= 2
        has_while = "while " in code_lower
        has_zip = "zip(" in code_lower
        has_sort = ".sort" in code_lower or "sorted(" in code_lower
        has_sum = "sum(" in code_lower
        has_count_method = ".count(" in code_lower
        has_replace = ".replace(" in code_lower
        has_recur = solution_code.strip().startswith("def ") and solution_code.count("def ") == 1 and solution_code.count(solution_code.split("def ")[1].split("(")[0] + "(") > 1

        # Determine pattern from code constructs
        if has_recur:
            return PATTERN_TEMPLATES["recursive"]
        if has_nested and ("all pair" in problem_lower or "triple" in problem_lower):
            return PATTERN_TEMPLATES["nested_loop"]
        if has_while and ("stack" in problem_lower or "nested" in problem_lower or "bracket" in problem_lower):
            return PATTERN_TEMPLATES["stack"]
        if has_dict or has_set:
            if "count" in problem_lower or "frequency" in problem_lower or "unique" in problem_lower:
                return PATTERN_TEMPLATES["default_dict"]
            if "filter" in problem_lower or "only" in problem_lower or "remove" in problem_lower:
                return PATTERN_TEMPLATES["filter"] + " Use a set/dict for O(1) lookup."
            return PATTERN_TEMPLATES["set_membership"]
        if has_sort:
            return PATTERN_TEMPLATES["sort"]
        if has_zip:
            return PATTERN_TEMPLATES["zip"]
        if has_count_method or "count" in problem_lower:
            return PATTERN_TEMPLATES["count"]
        if has_sum or ("sum" in problem_lower and "product" not in problem_lower):
            return PATTERN_TEMPLATES["accumulate"]
        if "filter" in problem_lower or "only" in problem_lower or "positive" in problem_lower or "negative" in problem_lower:
            return PATTERN_TEMPLATES["filter"]
        if "search" in problem_lower or "find" in problem_lower or "index" in problem_lower:
            return PATTERN_TEMPLATES["search"]
        if "replace" in problem_lower or "swap" in problem_lower or "exchange" in problem_lower:
            return PATTERN_TEMPLATES["replace"]
        if "reverse" in problem_lower or "invert" in problem_lower or "flip" in problem_lower:
            return "Reverse or invert the input sequence/structure."
        if "max" in problem_lower or "min" in problem_lower or "largest" in problem_lower or "smallest" in problem_lower:
            return "Find the maximum/minimum element satisfying a condition."
        if "palindrome" in problem_lower or "symmetric" in problem_lower:
            return "Compare the sequence forward and backward."
        if "string" in problem_lower or "character" in problem_lower or "char" in problem_lower:
            return PATTERN_TEMPLATES["string_process"]
        if "every" in problem_lower or "each" in problem_lower or "all" in problem_lower:
            return PATTERN_TEMPLATES["iteration"]
        if "transform" in problem_lower or "convert" in problem_lower or "change" in problem_lower:
            return PATTERN_TEMPLATES["transform"]
        if "factorial" in problem_lower or "fibonacci" in problem_lower:
            return PATTERN_TEMPLATES["recursive"] + " Or use iteration with memoization."

        return PATTERN_TEMPLATES["iteration"]

    def find_similar(self, problem_description: str, top_k: int = 2) -> List[ValidatedSolution]:
        """Find the most similar past validated problems."""
        if not self.solutions:
            return []

        scored = []
        problem_lower = problem_description.lower()

        for sol in self.solutions:
            # Primary: similarity between problem descriptions
            desc_sim = difflib.SequenceMatcher(
                None, problem_lower, sol.problem_description.lower()).ratio()

            # Secondary: pattern overlap (are they the same TYPE of problem?)
            pattern_sim = 0.0
            if sol.compact_pattern:
                # Extract key terms from both patterns
                prob_words = set(re.findall(r'\b[a-z]+\b', problem_lower))
                pat_words = set(re.findall(r'\b[a-z]+\b', sol.compact_pattern.lower()))
                if prob_words and pat_words:
                    pattern_sim = len(prob_words & pat_words) / len(prob_words | pat_words)

            combined_score = (desc_sim * 0.6 + pattern_sim * 0.4) * sol.confidence * (1 + 0.1 * sol.access_count)
            scored.append((combined_score, sol))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, sol in scored:
            if score > 0.15:  # Lower threshold for pattern-based matching
                sol.access_count += 1
                results.append(sol)
                if len(results) >= top_k:
                    break

        return results

    def build_compact_prompt(self, current_problem: str, entry_point: str) -> str:
        """
        Build a prompt enriched with COMPACT patterns from similar past successes.
        Injects only the pattern idea, NEVER the full code.
        """
        similar = self.find_similar(current_problem, top_k=1)

        if not similar:
            return ""

        sol = similar[0]
        compact = (
            f"Hint from a similar solved problem: {sol.compact_pattern}\n"
            f"Write your own solution for this new problem.\n\n"
        )

        return compact

    def print_contents(self):
        """Print a human-readable summary of everything in the knowledge graph."""
        print(f"\n{'='*60}")
        print(f"KNOWLEDGE GRAPH CONTENTS ({len(self.solutions)} entries)")
        print(f"{'='*60}")

        if not self.solutions:
            print("  (empty)")
            return

        for i, sol in enumerate(self.solutions, 1):
            print(f"\n--- Entry {i}: {sol.task_id} ---")
            print(f"  Problem: {sol.problem_description[:80]}")
            print(f"  Compact Pattern: {sol.compact_pattern}")
            print(f"  Confidence: {sol.confidence:.2f} | Accessed: {sol.access_count} times")
            # Print first 3 lines of code
            code_lines = sol.solution_code.split('\n')[:3]
            for line in code_lines:
                print(f"    {line}")
            if len(sol.solution_code.split('\n')) > 3:
                print(f"    ... ({len(sol.solution_code.split(chr(10))) - 3} more lines)")

        print(f"\n{'='*60}")

    def save_readable(self, filepath: str = "knowledge_graph_readable.txt"):
        """Save a human-readable dump."""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"KNOWLEDGE GRAPH DUMP\n")
            f.write(f"{'='*60}\n")
            f.write(f"Total entries: {len(self.solutions)}\n\n")

            for i, sol in enumerate(self.solutions, 1):
                f.write(f"\n{'='*60}\n")
                f.write(f"ENTRY {i}: {sol.task_id}\n")
                f.write(f"{'='*60}\n")
                f.write(f"Problem: {sol.problem_description}\n")
                f.write(f"Compact Pattern: {sol.compact_pattern}\n")
                f.write(f"Confidence: {sol.confidence:.2f}\n")
                f.write(f"Attempts: {sol.attempts}\n")
                f.write(f"Retrieved: {sol.access_count} times\n")
                f.write(f"Learned: {sol.timestamp}\n")
                f.write(f"\nFULL SOLUTION (for inspection only):\n")
                f.write(f"```python\n{sol.solution_code}\n```\n")

        print(f"  [KG] Readable dump saved to: {filepath}")

    def get_stats(self) -> Dict:
        if not self.solutions:
            return {"n_solutions": 0, "avg_confidence": 0, "total_accesses": 0}
        return {
            "n_solutions": len(self.solutions),
            "avg_confidence": sum(s.confidence for s in self.solutions) / len(self.solutions),
            "total_accesses": sum(s.access_count for s in self.solutions),
            "task_ids": [s.task_id for s in self.solutions],
        }

    def _save(self):
        data = [sol.to_dict() for sol in self.solutions]
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load(self):
        if os.path.exists(self.storage_path):
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.solutions = [ValidatedSolution.from_dict(d) for d in data]
