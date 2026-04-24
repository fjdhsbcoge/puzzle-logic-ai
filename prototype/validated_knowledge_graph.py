"""
Validated Knowledge Graph
==========================

A knowledge store that ONLY accumulates empirically validated solutions.
Every entry passed the test suite. Nothing enters by assumption.

Features:
- Stores: task_id, problem, solution, reasoning_trace, test_passed, confidence
- Retrieves similar past problems to provide few-shot examples
- Serializes to disk for persistence across sessions
- Confidence decays if similar problems later fail (self-correcting)
"""

import json
import os
import difflib
from typing import List, Dict, Any, Optional
from datetime import datetime


class ValidatedSolution:
    """A single piece of knowledge that has been empirically validated."""
    
    def __init__(self, task_id: str, problem_description: str, solution_code: str,
                 reasoning_trace: str = "", test_summary: str = "", attempts: int = 1):
        self.task_id = task_id
        self.problem_description = problem_description
        self.solution_code = solution_code
        self.reasoning_trace = reasoning_trace  # Model's thinking, if available
        self.test_summary = test_summary          # What tests passed
        self.attempts = attempts                # How many tries to succeed
        self.timestamp = datetime.now().isoformat()
        self.confidence = 1.0 / attempts         # Fewer attempts = higher confidence
        self.access_count = 0                   # How often retrieved
    
    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "problem_description": self.problem_description,
            "solution_code": self.solution_code,
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
    The memory of the Puzzle Logic OS.
    
    Principle: ONLY validated knowledge enters. No assumptions.
    This is the empirical foundation that the agent builds over time.
    """
    
    def __init__(self, storage_path: str = "validated_knowledge.json"):
        self.solutions: List[ValidatedSolution] = []
        self.storage_path = storage_path
        self._load()
    
    def add_solution(self, task_id: str, problem_description: str, solution_code: str,
                     reasoning_trace: str = "", test_summary: str = "", attempts: int = 1):
        """
        Add a validated solution to the knowledge graph.
        
        CRITICAL: Only call this AFTER the solution has passed tests.
        Unvalidated code must NEVER enter the graph.
        """
        solution = ValidatedSolution(
            task_id=task_id,
            problem_description=problem_description,
            solution_code=solution_code,
            reasoning_trace=reasoning_trace,
            test_summary=test_summary,
            attempts=attempts
        )
        
        # Check if we already have this task -- update if new attempt is better
        for i, existing in enumerate(self.solutions):
            if existing.task_id == task_id:
                if solution.confidence > existing.confidence:
                    print(f"  [KG] Updating {task_id} with better solution (confidence: {solution.confidence:.2f})")
                    self.solutions[i] = solution
                else:
                    print(f"  [KG] Keeping existing {task_id} (better confidence: {existing.confidence:.2f})")
                self._save()
                return
        
        # New task
        self.solutions.append(solution)
        print(f"  [KG] Learned new solution: {task_id} (confidence: {solution.confidence:.2f})")
        self._save()
    
    def find_similar(self, problem_description: str, top_k: int = 2) -> List[ValidatedSolution]:
        """
        Find the most similar past validated problems.
        Uses simple string similarity (difflib) -- can be upgraded to embeddings.
        """
        if not self.solutions:
            return []
        
        scored = []
        for sol in self.solutions:
            # Similarity score between problem descriptions
            similarity = difflib.SequenceMatcher(None, problem_description.lower(),
                                                  sol.problem_description.lower()).ratio()
            # Weight by confidence and access history
            score = similarity * sol.confidence * (1 + 0.1 * sol.access_count)
            scored.append((score, sol))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # Return top_k, excluding exact same problem
        results = []
        for score, sol in scored:
            if score > 0.3:  # Minimum similarity threshold
                sol.access_count += 1
                results.append(sol)
                if len(results) >= top_k:
                    break
        
        return results
    
    def build_few_shot_prompt(self, current_problem: str, entry_point: str) -> str:
        """
        Build a prompt enriched with similar past successful solutions.
        This is how the system 'learns' -- by retrieving relevant experience.
        """
        similar = self.find_similar(current_problem, top_k=1)
        
        if not similar:
            return ""  # No relevant experience yet
        
        sol = similar[0]
        few_shot = (
            f"Here is a similar problem I successfully solved before:\n\n"
            f"Task: {sol.problem_description}\n"
            f"Solution:\n```python\n{sol.solution_code}\n```\n\n"
            f"Now, using the same approach, solve this new task.\n\n"
        )
        
        return few_shot
    
    def get_stats(self) -> Dict:
        """Statistics about what the system has learned."""
        if not self.solutions:
            return {"n_solutions": 0, "avg_confidence": 0, "total_accesses": 0}
        
        return {
            "n_solutions": len(self.solutions),
            "avg_confidence": sum(s.confidence for s in self.solutions) / len(self.solutions),
            "total_accesses": sum(s.access_count for s in self.solutions),
            "task_ids": [s.task_id for s in self.solutions],
        }
    
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
            print(f"  Confidence: {sol.confidence:.2f} | Accessed: {sol.access_count} times")
            print(f"  Code ({len(sol.solution_code)} chars):")
            # Print code with indentation
            for line in sol.solution_code.split('\n')[:10]:  # First 10 lines
                print(f"    {line}")
            if len(sol.solution_code.split('\n')) > 10:
                print(f"    ... ({len(sol.solution_code.split(chr(10))) - 10} more lines)")
        
        print(f"\n{'='*60}")
    
    def save_readable(self, filepath: str = "knowledge_graph_readable.txt"):
        """Save a human-readable dump of the knowledge graph."""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"KNOWLEDGE GRAPH DUMP\n")
            f.write(f"{'='*60}\n")
            f.write(f"Total entries: {len(self.solutions)}\n")
            f.write(f"Storage: {self.storage_path}\n\n")
            
            for i, sol in enumerate(self.solutions, 1):
                f.write(f"\n{'='*60}\n")
                f.write(f"ENTRY {i}: {sol.task_id}\n")
                f.write(f"{'='*60}\n")
                f.write(f"Problem: {sol.problem_description}\n")
                f.write(f"Confidence: {sol.confidence:.2f}\n")
                f.write(f"Attempts to solve: {sol.attempts}\n")
                f.write(f"Times retrieved: {sol.access_count}\n")
                f.write(f"Learned: {sol.timestamp}\n")
                f.write(f"Test result: {sol.test_summary}\n")
                f.write(f"\nSOLUTION CODE:\n")
                f.write(f"```python\n{sol.solution_code}\n```\n")
                if sol.reasoning_trace:
                    f.write(f"\nREASONING TRACE:\n{sol.reasoning_trace}\n")
        
        print(f"  [KG] Readable dump saved to: {filepath}")
    
    def _save(self):
        """Persist to disk."""
        data = [sol.to_dict() for sol in self.solutions]
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    def _load(self):
        """Load from disk if exists."""
        if os.path.exists(self.storage_path):
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.solutions = [ValidatedSolution.from_dict(d) for d in data]
            print(f"  [KG] Loaded {len(self.solutions)} validated solutions from disk")
