"""
Constraint Engine
Validates candidate code against empirical constraints:
- Syntax: does it compile?
- Types: does mypy pass? (optional)
- Tests: does pytest pass?
- Regression: do existing tests still pass?
"""

import subprocess
import tempfile
import os


class ConstraintResult:
    """Result of a single constraint check."""
    def __init__(self, name, passed, tension_contribution, details=""):
        self.name = name
        self.passed = passed
        self.tension_contribution = tension_contribution  # 0.0 to 1.0
        self.details = details
    
    def __repr__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"{self.name}: {status} (tension +{self.tension_contribution})"


class ConstraintEngine:
    """
    The measurement apparatus.
    The compiler and test suite are the ground truth.
    """
    
    # Constraint weights — hard constraints have high tension when violated
    WEIGHTS = {
        "syntax": 1.0,        # Must compile. Non-negotiable.
        "tests": 0.9,           # Must pass. Strong constraint.
        "regression": 0.9,      # Existing tests must still pass.
        "types": 0.8,           # Type safety. Strong but not fatal.
        "style": 0.2,           # Naming/formatting. Soft constraint.
    }
    
    def __init__(self, test_file=None, existing_module=None):
        self.test_file = test_file
        self.existing_module = existing_module
    
    def evaluate(self, code_string, module_path=None):
        """
        Run all constraints on a candidate code string.
        Returns (total_tension, list of ConstraintResults)
        """
        results = []
        
        # 1. Syntax check: write to temp file and compile
        syntax_result = self._check_syntax(code_string, module_path)
        results.append(syntax_result)
        
        # If syntax fails, stop early — maximum tension
        if not syntax_result.passed:
            return 1.0, results
        
        # 2. Write the candidate to the actual module file for testing
        if module_path:
            self._write_candidate_to_module(code_string, module_path)
        
        # 3. Run existing tests (regression check)
        if self.test_file and module_path:
            regression_result = self._check_regression()
            results.append(regression_result)
            
            # 4. Run full test suite
            test_result = self._check_tests()
            results.append(test_result)
        
        total_tension = sum(r.tension_contribution for r in results)
        return min(total_tension, 1.5), results
    
    def _check_syntax(self, code_string, module_path=None):
        """Check if the code is valid Python syntax."""
        try:
            compile(code_string, "<candidate>", "exec")
            return ConstraintResult("syntax", True, 0.0, "Valid Python syntax")
        except SyntaxError as e:
            return ConstraintResult(
                "syntax", False, self.WEIGHTS["syntax"],
                f"SyntaxError: {e}"
            )
    
    def _write_candidate_to_module(self, code_string, module_path):
        """Write the candidate code to the module file for testing."""
        # For the prototype, we assume the code_string is the full module content
        with open(module_path, "w") as f:
            f.write(code_string)
    
    def _check_regression(self):
        """Check if existing tests still pass."""
        if not self.test_file:
            return ConstraintResult("regression", True, 0.0, "No test file configured")
        
        return self._run_pytest(self.test_file, "regression")
    
    def _check_tests(self):
        """Check if tests pass."""
        if not self.test_file:
            return ConstraintResult("tests", True, 0.0, "No test file configured")
        
        return self._run_pytest(self.test_file, "tests")
    
    def _run_pytest(self, test_file, label):
        """Run pytest and return result."""
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", test_file, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=30
            )
            passed = result.returncode == 0
            tension = 0.0 if passed else self.WEIGHTS.get(label, 0.5)
            
            # Extract failure summary
            details = "All tests passed" if passed else result.stdout[-500:]
            return ConstraintResult(label, passed, tension, details)
            
        except subprocess.TimeoutExpired:
            return ConstraintResult(label, False, self.WEIGHTS.get(label, 0.5), "Test timeout")
        except FileNotFoundError:
            return ConstraintResult(label, False, 0.0, "pytest not installed")
