"""
Puzzle Logic AI — Benchmark Suite
====================================

A set of coding tasks designed to test both raw model performance
and Puzzle Logic OS-augmented performance.

Some tasks are straightforward. Others contain hidden edge cases
that models commonly miss. The OS should catch these through
constraint validation and candidate selection.
"""

import os


class BenchmarkTask:
    """A single benchmark task with tests."""
    
    def __init__(self, name, description, module_name, module_stub, test_code, difficulty, hint=""):
        self.name = name
        self.description = description
        self.module_name = module_name
        self.module_stub = module_stub  # Starting content of the module file
        self.test_code = test_code
        self.difficulty = difficulty  # "easy", "medium", "hard"
        self.hint = hint  # Additional instruction to help the model
    
    def setup(self, base_dir="benchmark_project"):
        """Create the module and test files for this task."""
        os.makedirs(base_dir, exist_ok=True)
        
        module_path = f"{base_dir}/{self.module_name}.py"
        with open(module_path, "w", encoding="utf-8") as f:
            f.write(self.module_stub)
        
        test_path = f"{base_dir}/test_{self.module_name}.py"
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(self.test_code)
        
        return module_path, test_path
    
    def get_prompt(self):
        """Build the prompt for the model."""
        prompt = f"Add a '{self.name}' function. {self.description}"
        if self.hint:
            prompt += f" {self.hint}"
        return prompt


# ==================== TASK DEFINITIONS ====================

TASKS = []

# TASK 1: Easy — should pass for both
TASKS.append(BenchmarkTask(
    name="multiply",
    description="Return the product of two numbers.",
    module_name="calculator",
    module_stub='"""Calculator module."""\n\ndef add(a, b):\n    return a + b\n',
    test_code='"""Tests."""\nimport sys\nsys.path.insert(0, "benchmark_project")\nfrom calculator import multiply\n\ndef test_multiply():\n    assert multiply(3, 4) == 12\n    assert multiply(0, 5) == 0\n    assert multiply(-2, 3) == -6\n',
    difficulty="easy",
))

# TASK 2: Medium — zero division trap
TASKS.append(BenchmarkTask(
    name="safe_divide",
    description="Return a / b. If b is zero, return None instead of crashing.",
    module_name="math_utils",
    module_stub='"""Math utilities."""\n\n',
    test_code='"""Tests."""\nimport sys\nsys.path.insert(0, "benchmark_project")\nfrom math_utils import safe_divide\n\ndef test_safe_divide_normal():\n    assert safe_divide(10, 2) == 5.0\n\ndef test_safe_divide_zero():\n    assert safe_divide(5, 0) is None\n    assert safe_divide(-3, 0) is None\n',
    difficulty="medium",
))

# TASK 3: Medium — palindrome with edge cases
# Trap: models often forget to handle mixed case, spaces, or non-alphanumeric
TASKS.append(BenchmarkTask(
    name="is_palindrome",
    description="Return True if the string is a palindrome (reads same forwards and backwards). Ignore case, spaces, and non-alphanumeric characters.",
    module_name="strings",
    module_stub='"""String utilities."""\n\n',
    test_code='"""Tests."""\nimport sys\nsys.path.insert(0, "benchmark_project")\nfrom strings import is_palindrome\n\ndef test_is_palindrome_simple():\n    assert is_palindrome("radar") == True\n    assert is_palindrome("hello") == False\n\ndef test_is_palindrome_case_insensitive():\n    assert is_palindrome("Radar") == True\n\ndef test_is_palindrome_with_spaces():\n    assert is_palindrome("A man a plan a canal Panama") == True\n\ndef test_is_palindrome_with_punctuation():\n    assert is_palindrome("Was it a car or a cat I saw?") == True\n',
    difficulty="medium",
))

# TASK 4: Medium — list average with empty list trap
TASKS.append(BenchmarkTask(
    name="list_average",
    description="Return the average of a list of numbers. If the list is empty, return 0.0.",
    module_name="stats",
    module_stub='"""Statistics utilities."""\n\n',
    test_code='"""Tests."""\nimport sys\nsys.path.insert(0, "benchmark_project")\nfrom stats import list_average\n\ndef test_average_normal():\n    assert list_average([1, 2, 3, 4]) == 2.5\n\ndef test_average_empty():\n    assert list_average([]) == 0.0\n\ndef test_average_single():\n    assert list_average([7]) == 7.0\n',
    difficulty="medium",
))

# TASK 5: Hard — LRU cache with eviction
# Trap: models often get the eviction order wrong or don't handle capacity
TASKS.append(BenchmarkTask(
    name="LRUCache",
    description="Implement a simple LRU (Least Recently Used) cache class with get(key) and put(key, value) methods. When the cache exceeds a given capacity, evict the least recently used item.",
    module_name="cache",
    module_stub='"""Cache implementation."""\n\n',
    test_code='"""Tests."""\nimport sys\nsys.path.insert(0, "benchmark_project")\nfrom cache import LRUCache\n\ndef test_lru_basic():\n    c = LRUCache(2)\n    c.put(1, "a")\n    c.put(2, "b")\n    assert c.get(1) == "a"\n\ndef test_lru_eviction():\n    c = LRUCache(2)\n    c.put(1, "a")\n    c.put(2, "b")\n    c.put(3, "c")  # evicts key 1\n    assert c.get(1) is None\n    assert c.get(2) == "b"\n    assert c.get(3) == "c"\n\ndef test_lru_updates_order():\n    c = LRUCache(2)\n    c.put(1, "a")\n    c.put(2, "b")\n    c.get(1)  # now 1 is most recently used\n    c.put(3, "c")  # should evict 2, not 1\n    assert c.get(1) == "a"\n    assert c.get(2) is None\n    assert c.get(3) == "c"\n',
    difficulty="hard",
))

# TASK 6: Hard — recursive Fibonacci with memoization
# Trap: naive recursive Fibonacci is O(2^n) and will hang on n=30+
TASKS.append(BenchmarkTask(
    name="fibonacci",
    description="Return the nth Fibonacci number. Use memoization or an iterative approach so it runs efficiently for large n.",
    module_name="sequences",
    module_stub='"""Sequence utilities."""\n\n',
    test_code='"""Tests."""\nimport sys\nsys.path.insert(0, "benchmark_project")\nfrom sequences import fibonacci\n\ndef test_fibonacci_small():\n    assert fibonacci(0) == 0\n    assert fibonacci(1) == 1\n    assert fibonacci(10) == 55\n\ndef test_fibonacci_large():\n    assert fibonacci(30) == 832040\n    assert fibonacci(50) == 12586269025\n',
    difficulty="hard",
))


def get_all_tasks():
    return TASKS
