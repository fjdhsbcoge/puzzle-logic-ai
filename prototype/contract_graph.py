"""
Contract Graph — Empirical Ontology Builder
============================================

Learns programming contracts from empirically validated solutions.
Starts empty. Every successful solution adds a new contract node.
Nodes connect via type compatibility and shared preconditions.

Key principle: The graph discovers Python's structure through experience,
not through human specification. A contract only enters the graph if
it was part of a solution that passed all tests.

Usage:
    graph = ContractGraph()
    # After solving a problem:
    graph.learn_from_solution(problem_text, solution_code)
    # For a new problem:
    hints = graph.get_contract_hints(problem_text)
"""

import json
import os
import re
import difflib
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
from datetime import datetime


class ContractNode:
    """
    A learned function contract — the empirical puzzle piece.
    
    This is NOT full code. It is the INTERFACE that the code satisfied:
    - What inputs does it accept?
    - What output does it produce?
    - What guards does it check before operating?
    - What type transformations does it perform?
    """

    def __init__(self, task_id: str, problem_text: str,
                 input_types: List[str], output_type: str,
                 preconditions: List[str], postconditions: List[str],
                 abstract_pattern: str, confidence: float = 1.0):
        self.task_id = task_id
        self.problem_text = problem_text
        self.input_types = input_types          # e.g., ["List[int]", "str"]
        self.output_type = output_type          # e.g., "Optional[int]"
        self.preconditions = preconditions      # e.g., ["guard: empty input"]
        self.postconditions = postconditions    # e.g., ["returns int or None"]
        self.abstract_pattern = abstract_pattern  # e.g., "Filter with predicate"
        self.confidence = confidence            # 1.0 = first-try success
        self.times_used = 0
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "input_types": self.input_types,
            "output_type": self.output_type,
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "abstract_pattern": self.abstract_pattern,
            "confidence": self.confidence,
            "times_used": self.times_used,
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, d: Dict, problem_text: str = "") -> "ContractNode":
        n = cls(
            task_id=d["task_id"],
            problem_text=problem_text,
            input_types=d.get("input_types", []),
            output_type=d.get("output_type", "unknown"),
            preconditions=d.get("preconditions", []),
            postconditions=d.get("postconditions", []),
            abstract_pattern=d.get("abstract_pattern", ""),
            confidence=d.get("confidence", 1.0),
        )
        n.times_used = d.get("times_used", 0)
        n.timestamp = d.get("timestamp", datetime.now().isoformat())
        return n


class ContractGraph:
    """
    The empirical knowledge of how Python functions connect.
    
    Nodes = validated function contracts (what the code did, not what it was).
    Edges = type compatibility and shared abstract patterns.
    """
    
    def __init__(self, storage_path: str = "contract_graph.json"):
        self.nodes: List[ContractNode] = []
        self.compatibility_edges: Dict[Tuple[str, str], int] = defaultdict(int)
        # Maps type names to how often they appear together
        self.storage_path = storage_path
        self._load()
    
    # ==================== LEARNING ====================
    
    def learn_from_solution(self, task_id: str, problem_text: str,
                           solution_code: str, attempts: int = 1):
        """
        Extract a contract from a validated solution and add it to the graph.
        This is how the graph learns — only from code that passed tests.
        """
        # Extract function signature
        sig = self._extract_signature(solution_code)
        
        # Extract preconditions (guard clauses at start of function)
        preconds = self._extract_preconditions(solution_code)
        
        # Extract abstract pattern from problem + code
        pattern = self._infer_pattern(problem_text, solution_code, preconds)
        
        # Infer types from type hints or problem description
        in_types, out_type = self._infer_types(sig, problem_text)
        
        # Create contract node
        node = ContractNode(
            task_id=task_id,
            problem_text=problem_text,
            input_types=in_types,
            output_type=out_type,
            preconditions=preconds,
            postconditions=[],  # Would need static analysis
            abstract_pattern=pattern,
            confidence=1.0 / attempts,
        )
        
        # Add to graph, update compatibility edges
        self._add_node(node)
        
        print(f"  [CG] Learned contract: {task_id}")
        print(f"       Pattern: {pattern}")
        print(f"       Signature: ({', '.join(in_types)}) -> {out_type}")
        print(f"       Guards: {', '.join(preconds) if preconds else 'none'}")
    
    def _extract_signature(self, code: str) -> Dict:
        """Extract function name and parameter names from code."""
        match = re.search(r"def\s+(\w+)\s*\((.*?)\)", code)
        if not match:
            return {"name": "unknown", "params": []}
        
        func_name = match.group(1)
        params_raw = match.group(2)
        
        # Parse parameters (handle type hints)
        params = []
        for p in params_raw.split(","):
            p = p.strip()
            if p and p != "self":
                # Remove type hints and default values
                p = re.sub(r":\s*[^=]+", "", p)  # Remove type hint
                p = re.sub(r"=.*", "", p)         # Remove default
                p = p.strip()
                if p:
                    params.append(p)
        
        return {"name": func_name, "params": params}
    
    def _extract_preconditions(self, code: str) -> List[str]:
        """
        Extract guard clauses from the first lines of the function body.
        These are the empirical preconditions the code checks.
        """
        preconds = []
        
        # Find the function body (lines after the def, indented)
        lines = code.split("\n")
        in_body = False
        body_lines = []
        
        for line in lines:
            if in_body:
                if line.strip() and not line.startswith(" ") and not line.startswith("\t"):
                    break
                body_lines.append(line)
            elif line.strip().startswith("def "):
                in_body = True
        
        # Look for early return/guard patterns in first 5 body lines
        for line in body_lines[:8]:
            stripped = line.strip()
            
            # Empty input guard
            if re.search(r"if\s+not\s+\w+\s*:\s*return", stripped):
                preconds.append("guard: empty input")
            elif re.search(r"if\s+\w+\s+is\s+None\s*:\s*return", stripped):
                preconds.append("guard: None input")
            elif re.search(r"if\s+len\([^)]+\)\s*==?\s*0\s*:\s*return", stripped):
                preconds.append("guard: empty input")
            
            # Zero division guard
            elif re.search(r"if\s+[^=]+==\s*0\s*:\s*return", stripped):
                preconds.append("guard: zero value")
            
            # Type check
            elif re.search(r"if\s+not\s+isinstance", stripped):
                preconds.append("guard: type check")
            
            # Range check
            elif re.search(r"if\s+[^<]+<\s*0\s*:", stripped):
                preconds.append("guard: negative input")
        
        return preconds
    
    def _infer_pattern(self, problem_text: str, code: str, preconds: List[str]) -> str:
        """
        Infer the abstract algorithmic pattern from problem + code.
        """
        text_lower = problem_text.lower()
        code_lower = code.lower()
        
        # Detect core operations from problem text
        has_filter = any(w in text_lower for w in ["filter", "only", "positive", "negative", "even", "odd", "greater", "less"])
        has_count = any(w in text_lower for w in ["count", "how many", "number of", "frequency"])
        has_search = any(w in text_lower for w in ["find", "search", "locate", "index", "position"])
        has_max = any(w in text_lower for w in ["largest", "maximum", "longest", "biggest", "max", "highest"])
        has_min = any(w in text_lower for w in ["smallest", "minimum", "shortest", "min", "lowest"])
        has_sum = any(w in text_lower for w in ["sum", "total", "add", "product", "multiply"])
        has_sort = any(w in text_lower for w in ["sort", "order", "arrange", "ascending", "descending"])
        has_transform = any(w in text_lower for w in ["convert", "transform", "change", "replace", "map"])
        has_reverse = any(w in text_lower for w in ["reverse", "invert", "flip", "backward"])
        has_group = any(w in text_lower for w in ["group", "partition", "split", "chunk"])
        has_unique = any(w in text_lower for w in ["distinct", "unique", "different", "no duplicate"])
        has_palindrome = "palindrome" in text_lower
        
        # Detect from code
        has_listcomp = "for " in code_lower and " in " in code_lower and "[" in code
        has_loop = "for " in code_lower or "while " in code_lower
        has_conditional = "if " in code_lower
        has_set = "set(" in code_lower or "{}" in code
        has_dict = "dict" in code_lower or "{}" in code
        has_sorted = "sorted(" in code_lower or ".sort" in code_lower
        has_max_builtin = "max(" in code_lower
        has_min_builtin = "min(" in code_lower
        has_sum_builtin = "sum(" in code_lower
        has_reduce = "reduce" in code_lower
        has_zip = "zip(" in code_lower
        has_enumerate = "enumerate(" in code_lower
        has_recur = "def " in code and code.count("def ") == 1 and code.count(code.split("def ")[1].split("(")[0] + "(") > 1
        
        # Build pattern from highest-confidence indicators
        patterns = []
        
        if has_filter and has_listcomp:
            patterns.append("Filter sequence by predicate")
        elif has_filter:
            patterns.append("Filter elements matching condition")
        
        if has_count:
            patterns.append("Count matching elements")
        
        if has_search and not has_max and not has_min:
            patterns.append("Search for element by condition")
        
        if has_max and has_max_builtin:
            patterns.append("Find maximum by criterion")
        if has_min and has_min_builtin:
            patterns.append("Find minimum by criterion")
        
        if has_sum and has_sum_builtin:
            patterns.append("Accumulate (sum) elements")
        
        if has_sort or has_sorted:
            patterns.append("Sort sequence by key")
        
        if has_transform and has_listcomp:
            patterns.append("Transform each element (map)")
        
        if has_reverse:
            patterns.append("Reverse sequence")
        
        if has_group:
            patterns.append("Group elements by criterion")
        
        if has_unique:
            patterns.append("Extract unique/distinct elements")
        
        if has_palindrome:
            patterns.append("Compare sequence forward and backward")
        
        if has_recur:
            patterns.append("Recursive divide-and-conquer")
        
        # If no specific pattern detected, infer from code structure
        if not patterns:
            if has_reduce or ("result =" in code_lower and has_loop):
                patterns.append("Accumulate value through iteration")
            elif has_zip and has_loop:
                patterns.append("Combine multiple sequences")
            elif has_dict and has_loop:
                patterns.append("Build mapping from sequence")
            elif has_set and has_loop:
                patterns.append("Set-based membership filtering")
            elif has_loop and has_conditional:
                patterns.append("Iterate with conditional logic")
            elif has_loop:
                patterns.append("Simple iteration over sequence")
            else:
                patterns.append("Direct computation/transform")
        
        # Add precondition hints
        if preconds:
            patterns.append(f"Guards: {', '.join(preconds)}")
        
        return " | ".join(patterns) if patterns else "General computation"
    
    def _infer_types(self, sig: Dict, problem_text: str) -> Tuple[List[str], str]:
        """
        Infer input/output types from problem description.
        """
        text_lower = problem_text.lower()
        params = sig.get("params", [])
        
        in_types = []
        for p in params:
            p_lower = p.lower()
            
            # Try to infer from parameter name
            if any(w in p_lower for w in ["list", "arr", "nums", "numbers", "items", "strings"]):
                in_types.append("List")
            elif any(w in p_lower for w in ["string", "text", "s", "word", "name"]):
                in_types.append("str")
            elif any(w in p_lower for w in ["num", "n", "count", "index", "x", "y", "a", "b"]):
                in_types.append("int/float")
            elif any(w in p_lower for w in ["dict", "map", "table"]):
                in_types.append("Dict")
            elif any(w in p_lower for w in ["set", "collection"]):
                in_types.append("Set")
            elif any(w in p_lower for w in ["func", "fn", "callback", "predicate"]):
                in_types.append("Callable")
            elif any(w in p_lower for w in ["prefix", "suffix", "delimiter", "sep"]):
                in_types.append("str")
            else:
                in_types.append("Any")
        
        # Infer output from problem text
        out_type = "Any"
        if any(w in text_lower for w in ["return true", "return false", "whether", "is it", "check if"]):
            out_type = "bool"
        elif any(w in text_lower for w in ["return a list", "list of", "array of", "sequence of"]):
            out_type = "List"
        elif any(w in text_lower for w in ["return a string", "string", "text", "sentence"]):
            out_type = "str"
        elif any(w in text_lower for w in ["return a number", "sum", "count", "total", "maximum", "minimum"]):
            out_type = "int"
        elif any(w in text_lower for w in ["return the first", "return the element", "return the item"]):
            out_type = "Element/Optional"
        elif any(w in text_lower for w in ["return none", "if not found", "return -1", "return 0"]):
            out_type = "Optional"
        elif "return" in text_lower and "dictionary" in text_lower:
            out_type = "Dict"
        
        return in_types, out_type
    
    def _add_node(self, node: ContractNode):
        """Add node and update type compatibility edges."""
        # Check if we already have a similar contract for this task
        for i, existing in enumerate(self.nodes):
            if existing.task_id == node.task_id:
                if node.confidence > existing.confidence:
                    self.nodes[i] = node
                self._save()
                return
        
        self.nodes.append(node)
        
        # Update compatibility: all input types are compatible with this function
        for in_t in node.input_types:
            self.compatibility_edges[(in_t, node.output_type)] += 1
        
        self._save()
    
    # ==================== RETRIEVAL ====================
    
    def get_contract_hints(self, problem_text: str, top_k: int = 2) -> str:
        """
        Retrieve relevant contracts for a new problem.
        Returns a formatted hint string (NOT full code).
        """
        if not self.nodes:
            return ""
        
        problem_lower = problem_text.lower()
        
        # Score each node by relevance
        scored = []
        for node in self.nodes:
            score = 0.0
            
            # Text similarity between problem descriptions
            desc_sim = difflib.SequenceMatcher(
                None, problem_lower, node.problem_text.lower()).ratio()
            score += desc_sim * 0.4
            
            # Pattern overlap
            prob_words = set(re.findall(r'\b[a-z]+\b', problem_lower))
            pat_words = set(re.findall(r'\b[a-z]+\b', node.abstract_pattern.lower()))
            if prob_words and pat_words:
                pat_sim = len(prob_words & pat_words) / len(prob_words | pat_words)
                score += pat_sim * 0.4
            
            # Type compatibility heuristic
            # If problem mentions "list" and contract takes List, boost score
            if "list" in problem_lower and any("list" in t.lower() for t in node.input_types):
                score += 0.1
            if "string" in problem_lower and any("str" in t.lower() for t in node.input_types):
                score += 0.1
            
            # Confidence weighting
            score *= node.confidence
            
            scored.append((score, node))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # Build compact hint from top matches
        hints = []
        for score, node in scored[:top_k]:
            if score < 0.1:
                continue
            
            node.times_used += 1
            
            hint_parts = [f"Pattern: {node.abstract_pattern}"]
            if node.preconditions:
                hint_parts.append(f"Validated guards: {', '.join(node.preconditions)}")
            hint_parts.append(f"Interface: ({', '.join(node.input_types)}) -> {node.output_type}")
            
            hints.append(" | ".join(hint_parts))
        
        if not hints:
            return ""
        
        return (
            "Validated patterns from similar problems:\n" +
            "\n".join(f"  - {h}" for h in hints) +
            "\n\nApply these patterns to solve the new problem.\n\n"
        )
    
    def get_stats(self) -> Dict:
        if not self.nodes:
            return {"n_contracts": 0}
        
        patterns = defaultdict(int)
        preconds = defaultdict(int)
        type_pairs = defaultdict(int)
        
        for node in self.nodes:
            patterns[node.abstract_pattern.split(" | ")[0] if " | " in node.abstract_pattern else node.abstract_pattern] += 1
            for p in node.preconditions:
                preconds[p] += 1
            for it in node.input_types:
                type_pairs[f"{it} -> {node.output_type}"] += 1
        
        return {
            "n_contracts": len(self.nodes),
            "n_unique_patterns": len(patterns),
            "top_patterns": dict(sorted(patterns.items(), key=lambda x: -x[1])[:5]),
            "top_preconditions": dict(sorted(preconds.items(), key=lambda x: -x[1])[:5]),
            "top_type_transforms": dict(sorted(type_pairs.items(), key=lambda x: -x[1])[:5]),
        }
    
    def print_graph(self):
        """Print human-readable summary of the learned graph."""
        print(f"\n{'='*60}")
        print(f"CONTRACT GRAPH ({len(self.nodes)} learned contracts)")
        print(f"{'='*60}")
        
        if not self.nodes:
            print("  (empty — no validated solutions yet)")
            return
        
        for i, node in enumerate(self.nodes, 1):
            print(f"\n--- Contract {i}: {node.task_id} ---")
            print(f"  Interface: ({', '.join(node.input_types)}) -> {node.output_type}")
            print(f"  Pattern: {node.abstract_pattern}")
            if node.preconditions:
                print(f"  Guards: {', '.join(node.preconditions)}")
            print(f"  Confidence: {node.confidence:.2f} | Used: {node.times_used} times")
        
        print(f"\n{'='*60}")
    
    def _save(self):
        data = {
            "nodes": [n.to_dict() for n in self.nodes],
            "compatibility": {f"{k[0]}->{k[1]}": v for k, v in self.compatibility_edges.items()},
        }
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    def _load(self):
        if os.path.exists(self.storage_path):
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.nodes = []
                for n_data in data.get("nodes", []):
                    self.nodes.append(ContractNode.from_dict(n_data))
                self.compatibility_edges = defaultdict(int)
                for k, v in data.get("compatibility", {}).items():
                    parts = k.split("->")
                    if len(parts) == 2:
                        self.compatibility_edges[(parts[0], parts[1])] = v
