"""
Puzzle Logic AI — Rejection Demonstration
==========================================

This demo deliberately triggers the rejection mechanism.
The task has a subtle requirement that the model will likely miss,
causing candidates to fail tests and be structurally rejected.

Watch for:
  - Candidate generates code that looks correct
  - Tests fail because of a hidden edge case
  - Tension exceeds the Ω threshold
  - REJECTION → Ω is raised automatically
  - The agent tries the next candidate
"""

import os
import sys

from puzzle_logic_agent import PuzzleLogicAgent


def create_sample_project():
    """Create a module with no functions — we will add one."""
    os.makedirs("sample_project_rejection", exist_ok=True)
    
    module_path = "sample_project_rejection/currency.py"
    with open(module_path, "w", encoding="utf-8") as f:
        f.write('"""Currency formatting utilities."""\n\n')
    
    # The test file — this is the ground truth, and it has a SUBTLE expectation
    test_code = '''"""Tests for currency formatting."""

import sys
sys.path.insert(0, "sample_project_rejection")

from currency import format_currency


def test_format_currency_positive():
    """A positive amount formats with the € symbol."""
    assert format_currency(123.4) == "€123.40"


def test_format_currency_zero():
    """Zero formats correctly."""
    assert format_currency(0) == "€0.00"


def test_format_currency_negative():
    """
    THIS IS THE TRAP.
    Most models will produce:  f"€{amount:.2f}"  →  "€-5.00"
    But the test expects:     "-€5.00"  (negative sign BEFORE the symbol)
    """
    assert format_currency(-5) == "-€5.00"
'''
    
    test_path = "sample_project_rejection/test_currency.py"
    with open(test_path, "w", encoding="utf-8") as f:
        f.write(test_code)
    
    return module_path, test_path


def main():
    print("=" * 70)
    print("PUZZLE LOGIC AI — REJECTION DEMONSTRATION")
    print("=" * 70)
    print()
    print("This demo is designed to trigger REJECTION.")
    print()
    print("The task looks simple: format currency with € symbol.")
    print("But the test has a HIDDEN requirement:")
    print('  Negative amounts must be formatted as "-€5.00"')
    print('  NOT as "€-5.00"')
    print()
    print("Most LLMs will miss this edge case.")
    print("The constraint engine will catch the failure.")
    print("The candidate will be structurally rejected.")
    print()
    print("-" * 70)
    
    # Setup
    print("\n[SETUP] Creating adversarial test project...")
    module_path, test_path = create_sample_project()
    
    # Show the trap
    with open(test_path, "r") as f:
        test_content = f.read()
    print(f"\n[TEST FILE — THE TRAP]\n{test_content}")
    
    # Initialize agent with Ω = 0.5 (balanced)
    print("-" * 70)
    agent = PuzzleLogicAgent(omega=0.5)
    
    # Check LM Studio
    print("\n[CHECK] Testing LM Studio connection...")
    if not agent.synapse.check_health():
        print("  ✗ LM Studio is not running!")
        print("  Please start LM Studio and load a model.")
        return
    print("  ✓ LM Studio is running!")
    
    # THE ADVERSARIAL TASK
    print("\n" + "=" * 70)
    task = (
        "Add a 'format_currency(amount)' function that formats a number "
        "as a currency string with the € symbol and two decimal places. "
        "Example: format_currency(123.4) should return '€123.40'. "
        "Handle all numeric inputs including zero and negative numbers."
    )
    print(f"TASK: {task}")
    print(f"Ω (openness) = {agent.omega:.2f}")
    print(f"Threshold (1-Ω) = {1-agent.omega:.2f}")
    print(f"If tension > {1-agent.omega:.2f}: candidate is REJECTED")
    print("=" * 70 + "\n")
    
    accepted = agent.generate_code(
        task_description=task,
        target_module=module_path,
        test_file=test_path,
        n_candidates=3
    )
    
    if accepted:
        print("\n[RESULT] A candidate was eventually accepted.")
        print("If it was the 2nd or 3rd candidate, you saw rejection + Ω-raising in action.")
        with open(module_path, "r") as f:
            print(f"\n[FINAL CODE]\n{f.read()}")
    else:
        print("\n[RESULT] ALL candidates were rejected. Ω was raised significantly.")
        print("The agent could not solve the task with the current model.")
        print("This demonstrates structural falsification in action.")
    
    # Show session log
    agent.print_log()
    
    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    
    # Summary
    rejections = len([e for e in agent.log if e["action"] == "REJECT"])
    accepts = len([e for e in agent.log if e["action"] == "ACCEPT"])
    
    print(f"\nSUMMARY:")
    print(f"  Candidates generated: 3")
    print(f"  Accepted: {accepts}")
    print(f"  Rejected: {rejections}")
    print(f"  Initial Ω: 0.50")
    print(f"  Final Ω: {agent.omega:.2f}")
    
    if rejections > 0:
        print(f"\n  ✓ Rejection mechanism activated {rejections} time(s)")
        print(f"  ✓ Ω was raised from 0.50 to {agent.omega:.2f}")
        print(f"  ✓ The agent became MORE OPEN after failures")
    else:
        print(f"\n  The model was too good — every candidate passed.")
        print(f"  Try a different model or a harder task to see rejection.")


if __name__ == "__main__":
    main()
