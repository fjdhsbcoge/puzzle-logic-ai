"""
Puzzle Logic AI — Prototype Demo
================================

Run this script to see the Puzzle Logic Coding Agent in action.

Before running:
1. Install LM Studio (https://lmstudio.ai)
2. Download the DeepSeek R1-0528-Qwen3-8B model
3. Start the local server (usually on http://localhost:1234)
4. Install pytest: pip install pytest

Then run: python demo.py

The agent will:
1. Read a simple Python module
2. Generate candidates to add a function
3. Test each candidate against constraints (syntax + tests)
4. Accept or reject based on Ω-gated tension
"""

import os
import sys

from puzzle_logic_agent import PuzzleLogicAgent


def create_sample_project():
    """Create a minimal Python project for testing."""
    os.makedirs("sample_project", exist_ok=True)
    
    # The existing module
    module_code = '''"""A simple calculator module."""


def add(a, b):
    """Return the sum of a and b."""
    return a + b


def subtract(a, b):
    """Return the difference of a and b."""
    return a - b
'''
    
    module_path = "sample_project/calculator.py"
    with open(module_path, "w") as f:
        f.write(module_code)
    
    # The test file
    test_code = '''"""Tests for calculator module."""

import sys
sys.path.insert(0, "sample_project")

from calculator import add, subtract


def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0


def test_subtract():
    assert subtract(5, 3) == 2
    assert subtract(0, 5) == -5
'''
    
    test_path = "sample_project/test_calculator.py"
    with open(test_path, "w") as f:
        f.write(test_code)
    
    return module_path, test_path


def main():
    print("=" * 70)
    print("PUZZLE LOGIC AI — PROTOTYPE DEMO")
    print("=" * 70)
    print()
    print("This demo shows a coding agent that:")
    print("  1. Uses a local LLM (via LM Studio) to propose code")
    print("  2. Validates each proposal against constraints")
    print("  3. Accepts or rejects based on the Omega (Ω) parameter")
    print()
    print("-" * 70)
    
    # Setup sample project
    print("\n[SETUP] Creating sample project...")
    module_path, test_path = create_sample_project()
    print(f"  Module: {module_path}")
    print(f"  Tests:  {test_path}")
    
    # Show existing code
    with open(module_path, "r") as f:
        existing = f.read()
    print(f"\n[EXISTING CODE]\n{existing}")
    
    # Initialize agent with Ω = 0.5 (balanced)
    print("-" * 70)
    agent = PuzzleLogicAgent(omega=0.5)
    
    # Check LM Studio connectivity
    print("\n[CHECK] Testing LM Studio connection...")
    if not agent.synapse.check_health():
        print("  ✗ LM Studio is not running!")
        print()
        print("  Please:")
        print("  1. Open LM Studio")
        print("  2. Load a model (DeepSeek R1-0528-Qwen3-8B recommended)")
        print("  3. Start the local server (Developer tab → Start Server)")
        print("  4. Default URL: http://localhost:1234")
        print()
        print("  Running in DRY-RUN mode (no actual generation)...")
        dry_run = True
    else:
        print("  ✓ LM Studio is running!")
        dry_run = False
    
    # Task 1: Add a multiply function
    print("\n" + "=" * 70)
    task1 = "Add a 'multiply(a, b)' function that returns the product of two numbers."
    
    if dry_run:
        print("[DRY RUN] Skipping LM Studio call.")
        print("  The agent would:")
        print(f"  - Send task to model: {task1}")
        print("  - Receive candidate code")
        print("  - Check syntax + tests")
        print("  - Accept if tension < 0.5 (1-Ω)")
        return
    
    accepted = agent.generate_code(
        task_description=task1,
        target_module=module_path,
        test_file=test_path,
        n_candidates=3
    )
    
    if accepted:
        print("\n[RESULT] Accepted code written to module.")
        with open(module_path, "r") as f:
            print(f.read())
    else:
        print("\n[RESULT] No candidate was accepted.")
    
    # Show session log
    agent.print_log()
    
    # Task 2: Intentionally tricky — ask for something that might break
    print("\n" + "=" * 70)
    print("TASK 2: Add a function with a deliberate test for robustness")
    print("=" * 70)
    
    # Add a new test that expects a divide function
    test_code_2 = '''"""Tests for calculator module."""

import sys
sys.path.insert(0, "sample_project")

from calculator import add, subtract, multiply, divide


def test_add():
    assert add(2, 3) == 5


def test_subtract():
    assert subtract(5, 3) == 2


def test_multiply():
    assert multiply(3, 4) == 12


def test_divide():
    assert divide(10, 2) == 5
    assert divide(5, 0) is None  # Should handle division by zero
'''
    with open(test_path, "w") as f:
        f.write(test_code_2)
    
    task2 = "Add a 'divide(a, b)' function that returns a/b. If b is 0, return None."
    accepted2 = agent.generate_code(
        task_description=task2,
        target_module=module_path,
        test_file=test_path,
        n_candidates=3
    )
    
    if accepted2:
        print("\n[RESULT] Accepted code written to module.")
        with open(module_path, "r") as f:
            print(f.read())
    else:
        print("\n[RESULT] No candidate was accepted. Ω was raised.")
    
    agent.print_log()
    
    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print("\nThe agent:")
    print(f"  - Started with Ω = 0.50")
    print(f"  - Ended with Ω = {agent.omega:.2f}")
    print(f"  - Accepted {agent.experience} pieces")
    print(f"  - Rejected {len([e for e in agent.log if e['action'] == 'REJECT'])} pieces")
    print("\nBelief Graph:")
    print(agent.belief_graph.describe())


if __name__ == "__main__":
    main()
