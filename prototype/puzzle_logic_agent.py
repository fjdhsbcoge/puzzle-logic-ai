"""
Puzzle Logic Agent
The core system: Synapse proposes, OS validates, Ω decides.
"""

import os
import re

from lmstudio_client import LMStudioClient
from belief_graph import BeliefGraph, BeliefNode
from constraint_engine import ConstraintEngine


class PuzzleLogicAgent:
    """
    A coding agent that assembles knowledge as a jigsaw puzzle,
    with a single parameter Ω controlling openness to contradiction.
    """
    
    def __init__(self, omega=0.7, base_url="http://localhost:1234/v1"):
        # THE parameter
        self.omega = omega
        
        # THE OS
        self.belief_graph = BeliefGraph()
        self.constraint_engine = ConstraintEngine()
        
        # THE Synapse
        self.synapse = LMStudioClient(base_url=base_url)
        
        # Experience counter (drives Ω decay later)
        self.experience = 0
        
        # Logging
        self.log = []
    
    def generate_code(self, task_description, target_module, test_file=None, n_candidates=3):
        """
        Main entry point.
        
        Given a task, generate code that FITS the constraints.
        Returns the accepted candidate or None.
        """
        print(f"\n{'='*60}")
        print(f"TASK: {task_description}")
        print(f"Ω (openness) = {self.omega:.2f}")
        print(f"Threshold (1-Ω) = {1-self.omega:.2f}")
        print(f"{'='*60}\n")
        
        # Configure constraint engine for this task
        self.constraint_engine.test_file = test_file
        self.constraint_engine.existing_module = target_module
        
        # Step 1: Read existing module to provide context
        existing_code = ""
        if os.path.exists(target_module):
            with open(target_module, "r") as f:
                existing_code = f.read()
        
        # Step 2: Synapse proposes candidates
        prompt = self._build_prompt(task_description, existing_code)
        print(f"[SYNAPSE] Generating {n_candidates} candidates...")
        
        raw_candidates = self.synapse.generate(prompt, temperature=0.7, n=n_candidates)
        candidates = [self._extract_code_block(r) for r in raw_candidates]
        
        print(f"[SYNAPSE] Generated {len(candidates)} candidates\n")
        
        # Step 3: OS validates each candidate
        for i, candidate in enumerate(candidates, 1):
            if not candidate.strip():
                print(f"  Candidate {i}: EMPTY — rejected\n")
                continue
            
            print(f"  Candidate {i}: Evaluating...")
            tension, results = self.constraint_engine.evaluate(candidate, target_module)
            threshold = 1.0 - self.omega
            
            # Show constraint results
            for r in results:
                status = "✓" if r.passed else "✗"
                print(f"    {status} {r.name}: {r.details[:60]}")
            print(f"    Total tension: {tension:.3f} | Threshold: {threshold:.3f}")
            
            # Ω-GATED DECISION
            if tension <= threshold:
                print(f"  → ACCEPTED (tension ≤ threshold)\n")
                self._integrate(candidate, task_description, tension)
                return candidate
            else:
                print(f"  → REJECTED (tension > threshold)\n")
                self._log_rejection(candidate, tension, results)
        
        # No candidate worked — temporarily raise Ω ("I'm confused, be more open")
        print(f"[OS] No candidate fit. Raising Ω temporarily.")
        self.omega = min(0.95, self.omega + 0.15)
        print(f"[OS] Ω adjusted to {self.omega:.2f}")
        
        return None
    
    def _build_prompt(self, task, existing_code):
        """Build the prompt for the Synapse."""
        prompt = f"""You are working on a Python project. Here is the current module:

```python
{existing_code}
```

TASK: {task}

Please write ONLY the updated module content. Do not include explanations.
Output the complete Python module inside a markdown code block.
"""
        return prompt
    
    def _extract_code_block(self, text):
        """Extract the first Python code block from the model's response."""
        # Look for ```python ... ``` or ``` ... ```
        pattern = r"```(?:python)?\n(.*?)```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Fallback: if no code block, return the whole text
        return text.strip()
    
    def _integrate(self, code, task, tension):
        """Integrate accepted code into the belief graph."""
        self.experience += 1
        
        # Extract function names from the code (simple regex)
        functions = re.findall(r"def\s+(\w+)\s*\(", code)
        for fname in functions:
            node = BeliefNode(
                identity=fname,
                signature={"source": "inferred from code"},
                source="synapse",
                confidence=1.0 - tension  # Higher tension = lower confidence
            )
            self.belief_graph.add_node(node)
        
        self.log.append({
            "action": "ACCEPT",
            "task": task,
            "tension": tension,
            "omega": self.omega,
            "functions": functions
        })
        
        print(f"[OS] Integrated {len(functions)} function(s) into Belief Graph")
        print(self.belief_graph.describe())
    
    def _log_rejection(self, code, tension, results):
        """Log a rejected candidate."""
        self.log.append({
            "action": "REJECT",
            "tension": tension,
            "omega": self.omega,
            "reasons": [r.name for r in results if not r.passed]
        })
    
    def print_log(self):
        """Print session history."""
        print(f"\n{'='*60}")
        print("SESSION LOG")
        print(f"{'='*60}")
        for entry in self.log:
            action = entry["action"]
            omega = entry["omega"]
            tension = entry.get("tension", "N/A")
            print(f"  [{action}] Ω={omega:.2f} tension={tension}")
            if "reasons" in entry:
                print(f"         Failed: {', '.join(entry['reasons'])}")
        print(f"\nFinal Ω: {self.omega:.2f}")
        print(f"Experience: {self.experience} accepted pieces")
