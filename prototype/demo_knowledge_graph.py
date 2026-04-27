"""
Demo: Knowledge Graph Learning
================================

This demo shows the Validated Knowledge Graph in action.

The agent solves a sequence of related problems. After each success,
the solution is stored in the Knowledge Graph. For subsequent problems,
the KG retrieves similar past solutions as few-shot examples.

This demonstrates: the agent genuinely gets better because it accumulates
only empirically validated knowledge.
"""

import os
import sys

# Import our components
from validated_knowledge_graph import ValidatedKnowledgeGraph
from lmstudio_client import LMStudioClient
import re
import tempfile
import subprocess


# A small set of RELATED problems so similarity matching works
# All are string/list operations with similar structure
DEMO_PROBLEMS = [
    {
        "task_id": "learn_1",
        "name": "Count vowels in a string",
        "prompt": '''def count_vowels(text: str) -> int:
    """Return the number of vowels (a, e, i, o, u) in the string, case-insensitive.
    >>> count_vowels("hello")
    2
    >>> count_vowels("HELLO")
    2
    >>> count_vowels("")
    0
    """
''',
        "test": '''
def check(count_vowels):
    assert count_vowels("hello") == 2
    assert count_vowels("HELLO") == 2
    assert count_vowels("") == 0
    assert count_vowels("xyz") == 0
    assert count_vowels("aeiou") == 5

check(count_vowels)
''',
        "entry_point": "count_vowels",
    },
    {
        "task_id": "learn_2",
        "name": "Count consonants in a string",
        "prompt": '''def count_consonants(text: str) -> int:
    """Return the number of consonants in the string. Consonants are all letters that are not vowels (a, e, i, o, u). Case-insensitive.
    >>> count_consonants("hello")
    3
    >>> count_consonants("HELLO")
    3
    >>> count_consonants("")
    0
    """
''',
        "test": '''
def check(count_consonants):
    assert count_consonants("hello") == 3
    assert count_consonants("HELLO") == 3
    assert count_consonants("") == 0
    assert count_consonants("aeiou") == 0
    assert count_consonants("xyz") == 3

check(count_consonants)
''',
        "entry_point": "count_consonants",
    },
    {
        "task_id": "learn_3",
        "name": "Reverse a string if it contains a digit",
        "prompt": '''def maybe_reverse(s: str) -> str:
    """Return the reversed string if it contains any digit (0-9), otherwise return the original string.
    >>> maybe_reverse("abc")
    "abc"
    >>> maybe_reverse("a1c")
    "c1a"
    >>> maybe_reverse("")
    ""
    """
''',
        "test": '''
def check(maybe_reverse):
    assert maybe_reverse("abc") == "abc"
    assert maybe_reverse("a1c") == "c1a"
    assert maybe_reverse("") == ""
    assert maybe_reverse("123") == "321"
    assert maybe_reverse("hello2") == "2olleh"

check(maybe_reverse)
''',
        "entry_point": "maybe_reverse",
    },
    {
        "task_id": "learn_4",
        "name": "Keep only letters from a string",
        "prompt": '''def keep_letters(text: str) -> str:
    """Return a new string containing only alphabetic characters from the input, in the same order.
    >>> keep_letters("a1b2c3")
    "abc"
    >>> keep_letters("!!!")
    ""
    >>> keep_letters("Hello World")
    "HelloWorld"
    """
''',
        "test": '''
def check(keep_letters):
    assert keep_letters("a1b2c3") == "abc"
    assert keep_letters("!!!") == ""
    assert keep_letters("Hello World") == "HelloWorld"
    assert keep_letters("") == ""
    assert keep_letters("123") == ""

check(keep_letters)
''',
        "entry_point": "keep_letters",
    },
]


def extract_code(text: str) -> str:
    """Extract code from model output."""
    if not text:
        return ""
    match = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Check if raw code
    if "def " in text or "return" in text:
        return text.strip()
    return ""


def run_test(problem: Dict, completion: str) -> Dict:
    """Test a completion."""
    test_program = problem["prompt"] + "\n" + completion + "\n" + problem["test"] + "\n"
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(test_program)
        temp_path = f.name
    
    try:
        result = subprocess.run([sys.executable, temp_path], capture_output=True, text=True, timeout=5)
        passed = result.returncode == 0
        error = result.stderr if not passed else None
        if error and len(error) > 200:
            error = error[:200] + "..."
        return {"passed": passed, "error": error}
    except subprocess.TimeoutExpired:
        return {"passed": False, "error": "Timeout"}
    except Exception as e:
        return {"passed": False, "error": str(e)}
    finally:
        os.unlink(temp_path)


def solve_with_kg(problem: Dict, synapse: LMStudioClient, kg: ValidatedKnowledgeGraph,
                   n_candidates: int = 3, use_kg: bool = True) -> Dict:
    """
    Solve a problem, optionally using the Knowledge Graph for few-shot examples.
    Returns result dict and stores successful solutions in KG.
    """
    task_id = problem["task_id"]
    problem_desc = problem["name"]
    
    print(f"\n{'='*60}")
    print(f"TASK: {problem_desc}")
    print(f"{'='*60}")
    
    # Try to get few-shot example from KG
    few_shot = ""
    if use_kg:
        few_shot = kg.build_few_shot_prompt(problem["prompt"], problem["entry_point"])
        if few_shot:
            print("  [KG] Retrieved similar past solution as example")
    
    # Build prompt
    base_prompt = problem["prompt"]
    instruction = (
        "\n\nComplete the function above. Output the code inside a markdown code block."
    )
    
    if few_shot:
        prompt = few_shot + base_prompt + instruction
    else:
        prompt = base_prompt + instruction
    
    # Try multiple candidates
    previous_errors = []
    for attempt in range(1, n_candidates + 1):
        if previous_errors:
            feedback = "\n\nNOTE: Previous attempt did not pass tests. Please try again."
            attempt_prompt = prompt + feedback
        else:
            attempt_prompt = prompt
        
        raw = synapse.generate(prompt=attempt_prompt, temperature=0.3, max_tokens=512, n=1)
        
        if not raw or not raw[0].strip():
            previous_errors.append("Empty generation")
            continue
        
        completion = extract_code(raw[0])
        if not completion:
            previous_errors.append("No code extracted")
            continue
        
        test_result = run_test(problem, completion)
        
        if test_result["passed"]:
            print(f"  -> SOLVED on attempt {attempt}")
            # Store in Knowledge Graph!
            kg.add_solution(
                task_id=task_id,
                problem_description=problem_desc,
                solution_code=completion,
                reasoning_trace="",  # Could extract from model if available
                test_summary="All tests passed",
                attempts=attempt
            )
            return {"passed": True, "attempts": attempt, "used_kg": bool(few_shot)}
        else:
            previous_errors.append(test_result["error"])
            print(f"  Attempt {attempt}: FAIL")
    
    print(f"  -> FAILED after {n_candidates} attempts")
    return {"passed": False, "attempts": n_candidates, "used_kg": bool(few_shot)}


def main():
    print("=" * 70)
    print("PUZZLE LOGIC AI - KNOWLEDGE GRAPH DEMO")
    print("=" * 70)
    print()
    print("This demo shows the agent accumulating expertise.")
    print()
    print("Phase 1: Problem 1 solved WITHOUT knowledge graph help (empty graph)")
    print("Phase 2: Problem 2 solved WITH Problem 1 as few-shot example")
    print("Phase 3: Problem 3 solved WITH Problems 1-2 as examples")
    print("Phase 4: Problem 4 solved WITH accumulated knowledge")
    print()
    print("The hypothesis: The agent gets faster/better because it")
    print("ONLY remembers solutions that empirically passed the tests.")
    print()
    print("-" * 70)
    
    # Setup
    synapse = LMStudioClient()
    print("\n[CHECK] LM Studio...")
    if not synapse.check_health():
        print("  NOT RUNNING")
        return
    print("  OK")
    
    # Remove old knowledge graph for clean demo
    kg_path = "demo_knowledge_graph.json"
    if os.path.exists(kg_path):
        os.remove(kg_path)
    
    kg = ValidatedKnowledgeGraph(storage_path=kg_path)
    
    results = []
    
    # Solve each problem
    for problem in DEMO_PROBLEMS:
        result = solve_with_kg(problem, synapse, kg, n_candidates=3, use_kg=True)
        result["task_id"] = problem["task_id"]
        result["name"] = problem["name"]
        results.append(result)
    
    # Summary
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        kg_help = " (KG helped)" if r.get("used_kg") else " (no KG yet)"
        print(f"  {r['name']}: {status} in {r['attempts']} attempt(s){kg_help}")
    
    total_passed = sum(1 for r in results if r["passed"])
    total_with_kg_help = sum(1 for r in results if r.get("used_kg") and r["passed"])
    
    print(f"\n  Solved: {total_passed}/{len(results)}")
    print(f"  With KG assistance: {total_with_kg_help}/{len(results)}")
    
    # KG stats
    stats = kg.get_stats()
    print(f"\n  Knowledge Graph now contains {stats['n_solutions']} validated solution(s)")
    print(f"  Average confidence: {stats['avg_confidence']:.2f}")
    print(f"  Total retrievals: {stats['total_accesses']}")
    print(f"  Learned tasks: {', '.join(stats['task_ids'])}")
    
    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print()
    print("The agent 'learned' by storing only solutions that passed tests.")
    print("For later problems, it retrieved similar past successes as examples.")
    print("This is the Puzzle Logic approach to memory: only validated pieces fit.")
    
    # Cleanup
    if os.path.exists(kg_path):
        os.remove(kg_path)
        print(f"\n  (Cleaned up: removed {kg_path})")


if __name__ == "__main__":
    main()
