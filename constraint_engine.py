"""
Constraint Engine v3.0 — Structural Error Auto-Fixer
========================================================

Uses Python AST to analyze structural errors and compute concrete fixes.
For LOCAL errors (λ >= 0.6): NameError, TypeError, SyntaxError, IndexError, etc.

NOT for semantic/algorithmic errors (AssertionError, logic bugs) — those go
to the LLM Prompt Composer.

Key insight: The knowledge graph stores patterns like:
    "Changed: def find_missing(arr): -> def find_missing(arr, n):"
The constraint engine parses the CURRENT code, identifies the structural
violation, and computes the EXACT replacement for THIS code.
"""

import ast
import re
from typing import Optional, Tuple, Dict, List


class ConstraintViolation:
    """Represents a single structural violation with a concrete fix."""
    def __init__(self, violation_type: str, location: str,
                 current: str, replacement: str, explanation: str):
        self.violation_type = violation_type  # e.g., "arity_mismatch", "undefined_name"
        self.location = location            # e.g., "line 1, def find_missing"
        self.current = current              # exact text to replace
        self.replacement = replacement      # exact replacement text
        self.explanation = explanation      # human-readable why

    def to_prompt(self) -> str:
        return (
            f"[CONSTRAINT VIOLATION: {self.violation_type}]\n"
            f"Location: {self.location}\n"
            f"Problem:  {self.current}\n"
            f"Fix:      {self.replacement}\n"
            f"Why:      {self.explanation}\n"
        )


class StructuralConstraintEngine:
    """
    Analyzes code structure to find and fix LOCAL errors.
    No LLM calls — pure AST manipulation.
    """

    def analyze(self, error_type: str, error_sig: str, failing_code: str,
                test_code: str = "") -> Optional[ConstraintViolation]:
        """Main entry point. Returns a concrete fix or None."""

        if error_type == "NameError" and "is not defined" in error_sig:
            return self._fix_undefined_name(error_sig, failing_code)

        if error_type == "TypeError" and "takes" in error_sig and "were given" in error_sig:
            return self._fix_arity_mismatch(error_sig, failing_code)

        if error_type == "TypeError" and "can't convert" in error_sig:
            return self._fix_type_conversion(error_sig, failing_code)

        if error_type == "SyntaxError":
            return self._fix_syntax_error(error_sig, failing_code)

        if error_type == "IndexError" and "index out of range" in error_sig:
            return self._fix_index_error(error_sig, failing_code)

        if error_type == "KeyError":
            return self._fix_key_error(error_sig, failing_code)

        if error_type == "AttributeError" and "has no attribute" in error_sig:
            return self._fix_attribute_error(error_sig, failing_code)

        if error_type == "ImportError" or error_type == "ModuleNotFoundError":
            return self._fix_import_error(error_sig, failing_code)

        if error_type == "ZeroDivisionError":
            return self._fix_zero_division(error_sig, failing_code)

        # Structural error we don't have a rule for
        return None

    # ── Individual Fix Rules ────────────────────────────────────────────

    def _fix_undefined_name(self, error_sig: str, failing_code: str) -> Optional[ConstraintViolation]:
        """NameError: name 'x' is not defined."""
        m = re.search(r"name '([^']+)' is not defined", error_sig)
        if not m:
            return None
        bad_name = m.group(1)

        # Parse code to find the line with the undefined name
        lines = failing_code.strip().split("\n")
        for i, line in enumerate(lines):
            if bad_name in line:
                # Look for similar names in scope (function params, local vars)
                scope_names = self._extract_scope_names(failing_code)
                replacement = self._find_closest_name(bad_name, scope_names)
                if replacement:
                    return ConstraintViolation(
                        violation_type="undefined_name",
                        location=f"line {i+1}",
                        current=line.strip(),
                        replacement=line.replace(bad_name, replacement).strip(),
                        explanation=f"'{bad_name}' is undefined. Did you mean '{replacement}'? "
                                      f"Available names in scope: {', '.join(scope_names[:5])}"
                    )
        return None

    def _fix_arity_mismatch(self, error_sig: str, failing_code: str) -> Optional[ConstraintViolation]:
        """TypeError: func() takes N positional arguments but M were given."""
        # Extract function name
        m = re.search(r"(\w+)\(\)", error_sig)
        if not m:
            return None
        func_name = m.group(1)

        # Parse expected vs actual arg count from error
        m2 = re.search(r"takes (\d+|\w+) positional arguments? but (\d+) were given", error_sig)
        if not m2:
            # Try alternate format
            m2 = re.search(r"takes from (\d+) to (\d+) positional arguments but (\d+) were given", error_sig)
        if not m2:
            return None

        # Find the function definition in code
        lines = failing_code.strip().split("\n")
        for i, line in enumerate(lines):
            if re.search(rf"def\s+{re.escape(func_name)}\s*\(", line):
                current_sig = line.strip()
                # Count current params
                params_match = re.search(r"def\s+\w+\((.*)\):", current_sig)
                if params_match:
                    params_str = params_match.group(1).strip()
                    current_count = len([p for p in params_str.split(",") if p.strip()]) if params_str else 0
                else:
                    current_count = 0

                # The error tells us how many were GIVEN
                # We need to figure out expected from the call site or tests
                # For now, use a heuristic: add/remove 1 parameter
                given = int(m2.group(len(m2.groups())))  # last group is "were given"

                if given > current_count:
                    # Need more params — add a generic one
                    if params_str:
                        new_params = params_str + ", n"
                    else:
                        new_params = "n"
                    new_sig = f"def {func_name}({new_params}):"
                    return ConstraintViolation(
                        violation_type="arity_mismatch (too few params)",
                        location=f"line {i+1}, function signature",
                        current=current_sig,
                        replacement=new_sig,
                        explanation=f"Your function takes {current_count} parameter(s) but is called with {given}. "
                                      f"Add a parameter to match the call."
                    )
                else:
                    # Need fewer params — this is trickier, might need to use defaults
                    new_sig = current_sig  # can't safely remove without knowing which
                    return ConstraintViolation(
                        violation_type="arity_mismatch (too many params)",
                        location=f"line {i+1}, function signature",
                        current=current_sig,
                        replacement=new_sig,
                        explanation=f"Your function takes {current_count} parameter(s) but is called with {given}. "
                                      f"Check which parameter is extra or add default values."
                    )
        return None

    def _fix_type_conversion(self, error_sig: str, failing_code: str) -> Optional[ConstraintViolation]:
        """TypeError: int() can't convert non-string with explicit base."""
        # Extract the failing conversion
        m = re.search(r"(\w+)\(\) can't convert non-string with explicit base", error_sig)
        if m:
            func_name = m.group(1)
            # Find line with the conversion
            lines = failing_code.strip().split("\n")
            for i, line in enumerate(lines):
                if f"{func_name}(" in line and "2)" in line:  # e.g., int(binary, 2)
                    return ConstraintViolation(
                        violation_type="type_conversion",
                        location=f"line {i+1}",
                        current=line.strip(),
                        replacement=line.replace(f"{func_name}(", f"{func_name}(str(").replace(", 2)", "), 2)") if ", 2)" in line else line.strip(),
                        explanation=f"{func_name}() needs a string when given a base. Wrap the argument in str()."
                    )
        return None

    def _fix_syntax_error(self, error_sig: str, failing_code: str) -> Optional[ConstraintViolation]:
        """SyntaxError: specific syntax issue."""
        # Many syntax errors are unrecoverable by regex, but some are common
        if "unexpected EOF" in error_sig:
            return ConstraintViolation(
                violation_type="syntax_error (missing closing)",
                location="end of function",
                current="(missing closing bracket or parenthesis)",
                replacement="Add the missing closing character",
                explanation="Your code is missing a closing bracket, parenthesis, or quote."
            )
        if "invalid syntax" in error_sig:
            # Try to identify common issues
            lines = failing_code.strip().split("\n")
            for i, line in enumerate(lines):
                if ":" in line and not line.strip().endswith(":"):
                    # Missing colon after if/for/while/def
                    if re.search(r"\b(if|for|while|def|class|elif|else)\b", line):
                        return ConstraintViolation(
                            violation_type="syntax_error (missing colon)",
                            location=f"line {i+1}",
                            current=line.strip(),
                            replacement=line.strip() + ":",
                            explanation="Missing colon after control statement or function definition."
                        )
        return None

    def _fix_index_error(self, error_sig: str, failing_code: str) -> Optional[ConstraintViolation]:
        """IndexError: list index out of range."""
        lines = failing_code.strip().split("\n")
        for i, line in enumerate(lines):
            if "[" in line and "]" in line:
                return ConstraintViolation(
                    violation_type="index_error",
                    location=f"line {i+1}",
                    current=line.strip(),
                    replacement=line.strip(),  # can't auto-fix without knowing list length
                    explanation="Index out of range. Check that the index is less than the list length. "
                                "Consider using negative indexing or len() check."
                )
        return None

    def _fix_key_error(self, error_sig: str, failing_code: str) -> Optional[ConstraintViolation]:
        """KeyError: missing dictionary key."""
        m = re.search(r"KeyError: '?([^'\s]+)'?", error_sig)
        if m:
            key = m.group(1)
            return ConstraintViolation(
                violation_type="key_error",
                location="dictionary access",
                current=f"dict[{key}]",
                replacement=f"dict.get({key}, default_value)",
                explanation=f"Key '{key}' may not exist. Use .get() with a default, or check with 'in' first."
            )
        return None

    def _fix_attribute_error(self, error_sig: str, failing_code: str) -> Optional[ConstraintViolation]:
        """AttributeError: module/object has no attribute 'x'."""
        m = re.search(r"has no attribute '([^']+)'", error_sig)
        if m:
            attr = m.group(1)
            return ConstraintViolation(
                violation_type="attribute_error",
                location="attribute access",
                current=f".{attr}",
                replacement=f"(check if available)",
                explanation=f"Attribute '{attr}' does not exist on this object. "
                            f"Check the object type or use hasattr() to guard."
            )
        return None

    def _fix_import_error(self, error_sig: str, failing_code: str) -> Optional[ConstraintViolation]:
        """ImportError/ModuleNotFoundError: missing module."""
        m = re.search(r"No module named '([^']+)'", error_sig)
        if m:
            module = m.group(1)
            return ConstraintViolation(
                violation_type="import_error",
                location="import statement",
                current=f"import {module}",
                replacement=f"# {module} may not be available. Use try/except or check if installed.",
                explanation=f"Module '{module}' is not installed. Consider using a built-in alternative."
            )
        return None

    def _fix_zero_division(self, error_sig: str, failing_code: str) -> Optional[ConstraintViolation]:
        """ZeroDivisionError: division by zero."""
        lines = failing_code.strip().split("\n")
        for i, line in enumerate(lines):
            if "/" in line or "%" in line or "//" in line:
                return ConstraintViolation(
                    violation_type="zero_division",
                    location=f"line {i+1}",
                    current=line.strip(),
                    replacement=line.strip(),  # can't auto-fix without knowing the guard condition
                    explanation="Division by zero. Add a check: if divisor != 0: before the division."
                )
        return None

    # ── Helpers ─────────────────────────────────────────────────────────

    def _extract_scope_names(self, code: str) -> List[str]:
        """Extract variable/parameter names from function scope."""
        names = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    for arg in node.args.args:
                        names.append(arg.arg)
                    for arg in node.args.posonlyargs:
                        names.append(arg.arg)
                    for arg in node.args.kwonlyargs:
                        names.append(arg.arg)
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    names.append(node.id)
        except:
            pass
        return list(set(names))

    def _find_closest_name(self, target: str, candidates: List[str]) -> Optional[str]:
        """Find the most similar name in scope (Levenshtein-like heuristic)."""
        if not candidates:
            return None

        # Exact substring match first
        for c in candidates:
            if target in c or c in target:
                return c

        # Character overlap heuristic
        best = None
        best_score = 0
        target_chars = set(target.lower())
        for c in candidates:
            c_chars = set(c.lower())
            if target_chars and c_chars:
                score = len(target_chars & c_chars) / len(target_chars | c_chars)
                if score > best_score and score > 0.3:
                    best_score = score
                    best = c

        return best


# ═══════════════════════════════════════════════════════════════════════
#  PROMPT COMPOSER — Semantic/Algorithmic Errors (λ < 0.6)
# ═══════════════════════════════════════════════════════════════════════

class PromptComposer:
    """
    For UNLOCAL errors (AssertionError, logic bugs): uses an LLM to compose
    a specific instruction connecting the past fix to the current code.

    This is NOT auto-fixing — it's translating a generic pattern into a
    concrete directive for THIS function.
    """

    def __init__(self, llm_client):
        self.llm = llm_client

    def compose(self, error_type: str, error_sig: str, failing_code: str,
                test_code: str, pattern_fix: str, pattern_context: str) -> str:
        """
        Build a meta-prompt asking the composer LLM to translate a generic
        past fix into a specific instruction for the current code.
        """

        meta_prompt = f"""You are a code constraint analyzer. Your job is to translate a generic past fix into a SPECIFIC instruction for the CURRENT code.

RULES:
1. Do NOT describe the past fix abstractly. Apply it concretely.
2. Reference the CURRENT function's actual variable names and structure.
3. Give ONE clear, actionable instruction — not a list of options.
4. If the past fix doesn't apply directly, say so and suggest the most likely fix.

CURRENT FUNCTION (failing):
```python
{failing_code}
```

CURRENT ERROR:
[{error_type}] {error_sig}

PAST FIX (from knowledge base — similar error was fixed by):
{pattern_fix}

PAST CONTEXT (where the fix applied):
{pattern_context or "(no context available)"}

OUTPUT FORMAT (exactly this, no extra text):
CONSTRAINT VIOLATED: <the structural or logical rule broken>
CURRENT PROBLEM: <which specific part of the current code is wrong>
CONCRETE FIX: <exact change to make, using current variable names>
WHY: <one sentence explaining why this fixes it>
"""

        try:
            response = self.llm.generate(prompt=meta_prompt, temperature=0.0,
                                         max_tokens=512, n=1)
            if response and response[0]:
                return self._clean_composer_output(response[0])
        except Exception:
            pass

        # Fallback: generic but still specific to current code
        return self._fallback_unlocal_prompt(error_type, error_sig, failing_code, pattern_fix)

    def _clean_composer_output(self, raw: str) -> str:
        """Extract the structured output from composer LLM response."""
        lines = raw.strip().split("\n")
        # If the LLM wrapped it in markdown, unwrap
        if "```" in raw:
            # Extract between code fences
            parts = raw.split("```")
            if len(parts) >= 2:
                raw = parts[1] if not parts[0].strip() else parts[0]

        # Ensure it starts with the right format
        if not raw.strip().startswith("CONSTRAINT VIOLATED:"):
            raw = "CONSTRAINT VIOLATED: (see analysis below)\n" + raw

        return raw.strip()

    def _fallback_unlocal_prompt(self, error_type: str, error_sig: str,
                                 failing_code: str, pattern_fix: str) -> str:
        """When composer fails, generate a structured fallback."""
        # Extract function name from failing code
        func_match = re.search(r"def\s+(\w+)\s*\(", failing_code)
        func_name = func_match.group(1) if func_match else "your function"

        return (
            f"[CONSTRAINT VIOLATION: algorithmic_error ({error_type})]\n"
            f"Location: function '{func_name}'\n"
            f"Problem:  {error_sig[:100]}\n"
            f"\n"
            f"A similar error was previously fixed by:\n"
            f"  {pattern_fix[:200]}\n"
            f"\n"
            f"INSTRUCTION:\n"
            f"Analyze your function '{func_name}' step by step. "
            f"Compare your algorithm to the fix above. "
            f"The logic or edge case handling is incorrect. "
            f"Apply the key insight from the past fix to your specific code."
        )


# ═══════════════════════════════════════════════════════════════════════
#  HYBRID ENGINE — Routes by Locality
# ═══════════════════════════════════════════════════════════════════════

class HybridConstraintEngine:
    """
    Main entry point. Routes to:
      • StructuralConstraintEngine  for λ >= 0.6 (local errors)
      • PromptComposer              for λ < 0.6 (unlocal errors)
    """

    def __init__(self, llm_client=None):
        self.structural = StructuralConstraintEngine()
        self.composer = PromptComposer(llm_client) if llm_client else None

    def build_toolbox_prompt(self, error_type: str, error_sig: str,
                             failing_code: str, test_code: str,
                             locality: float, pattern_fix: str,
                             pattern_context: str = "") -> Optional[str]:
        """
        Build the best possible toolbox prompt based on locality.
        Returns None if no useful instruction can be generated.
        """

        if locality >= 0.6:
            # LOCAL → try deterministic structural fix first
            violation = self.structural.analyze(error_type, error_sig,
                                                  failing_code, test_code)
            if violation:
                return violation.to_prompt()

            # Structural engine couldn't handle it → fallback to composer if available
            if self.composer:
                return self.composer.compose(error_type, error_sig, failing_code,
                                             test_code, pattern_fix, pattern_context)
            return None

        else:
            # UNLOCAL → always use composer (semantic/algorithmic)
            if self.composer:
                return self.composer.compose(error_type, error_sig, failing_code,
                                             test_code, pattern_fix, pattern_context)
            return None
