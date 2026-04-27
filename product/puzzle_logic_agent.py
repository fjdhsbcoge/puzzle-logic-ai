"""
Puzzle Logic Agent v2.0
=======================

A CLI tool that brings Puzzle Logic reasoning to your coding workflow.

HOW IT WORKS (the Puzzle Logic loop):
  1. Reads your Python file or coding request
  2. Sends it to a local LLM (LM Studio) for completion/fixing
  3. EXECUTES the code in a sandbox (subprocess)
  4. If it FAILS:
     a. Extract error fingerprint
     b. Query the Error-Pattern Knowledge Graph: "Have we seen this before?"
     c. Present validated fix patterns as a TOOLBOX (model decides which fits)
     d. Retry with the hint
  5. If it PASSES:
     a. Validate: the solution is correct
     b. LEARN: store the error-fix pattern for next time

Knowledge persists across sessions in puzzle_logic_knowledge.json.

Usage:
  python puzzle_logic_agent.py my_script.py --model qwen2.5-coder-3b-instruct
  python puzzle_logic_agent.py my_script.py --test test_my_script.py --model qwen2.5-coder-3b-instruct
  python puzzle_logic_agent.py --generate "Write a function to reverse a list" --model qwen2.5-coder-3b-instruct
  python puzzle_logic_agent.py --stats

Setup:
  1. Install LM Studio (https://lmstudio.ai)
  2. Download a model (e.g., Qwen2.5-Coder-3B-Instruct)
  3. Start the server (Developer tab -> Start Server)
  4. Run this script
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from typing import Optional, Dict, List, Tuple
from collections import defaultdict
from datetime import datetime

# ─── Terminal colors (safe for all platforms) ──────────────────────────

def cyan(s: str) -> str:
    return f"\033[36m{s}\033[0m"

def green(s: str) -> str:
    return f"\033[32m{s}\033[0m"

def red(s: str) -> str:
    return f"\033[31m{s}\033[0m"

def yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m"

def bold(s: str) -> str:
    return f"\033[1m{s}\033[0m"


# ═════════════════════════════════════════════════════════════════════════
#  LM Studio Client
# ═════════════════════════════════════════════════════════════════════════

class LMStudioClient:
    """Connects to the local LM Studio OpenAI-compatible API."""

    def __init__(self, base_url="http://localhost:1234/v1", model=None, timeout=300):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.chat_endpoint = f"{self.base_url}/chat/completions"

    def generate(self, prompt, temperature=0.0, max_tokens=1024, n=1, system_message=None):
        import requests
        messages = [
            {"role": "system", "content": system_message or "You are a helpful coding assistant. Write clean, correct Python code."},
            {"role": "user", "content": prompt}
        ]

        candidates = []
        for _ in range(n):
            payload = {
                "model": self.model or "local-model",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False
            }

            data = None
            for attempt in range(3):
                try:
                    response = requests.post(
                        self.chat_endpoint,
                        json=payload,
                        timeout=self.timeout
                    )
                    response.raise_for_status()
                    data = response.json()
                    break
                except requests.exceptions.ReadTimeout:
                    print(yellow(f"  [LM Studio Warning] Timeout (attempt {attempt+1}/3). Retrying..."))
                    time.sleep(2 ** attempt)
                    if attempt == 2:
                        print(red("  [LM Studio Error] All retries exhausted."))
                        candidates.append("")
                        break
                except Exception as e:
                    print(red(f"  [LM Studio Error] {e}"))
                    candidates.append("")
                    break
            else:
                if data is None:
                    candidates.append("")
                    continue

            if data is None:
                continue

            msg = data["choices"][0]["message"]
            content = msg.get("content", "")
            if not content.strip() and "reasoning_content" in msg:
                content = msg["reasoning_content"]
            if not content.strip() and "reasoning" in msg:
                content = msg["reasoning"]
            content = self._strip_think_tags(content)
            candidates.append(content)

        return candidates

    def _strip_think_tags(self, text):
        if not text:
            return ""
        text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        return text.strip()

    def check_health(self):
        try:
            import requests
            response = requests.get(f"{self.base_url}/models", timeout=5)
            return response.status_code == 200
        except:
            return False


# ═════════════════════════════════════════════════════════════════════════
#  Code Extraction
# ═════════════════════════════════════════════════════════════════════════

def extract_code(text: str) -> str:
    """Extract code from model output, handling various formats."""
    if not text:
        return ""

    blocks = re.findall(r"```(?:\n|\r\n)?(?:python(?:\n|\r\n))?(.*?)```", text, re.DOTALL)
    for block in blocks:
        block = block.strip()
        if block and ("def " in block or "return" in block or "for " in block or "if " in block):
            if block.startswith("python\n"):
                block = block[7:].strip()
            elif block.startswith("python"):
                block = block[6:].strip()
            return block

    text = text.strip()
    if text and ("def " in text or "return" in text or "for " in text or "if " in text):
        return text

    return ""


# ═════════════════════════════════════════════════════════════════════════
#  Error-Pattern Knowledge Graph (Full version)
# ═════════════════════════════════════════════════════════════════════════

def extract_error_fingerprint(error_text: str) -> Tuple[str, str]:
    """Extract (error_type, normalized_signature) from a Python traceback."""
    if not error_text:
        return ("Unknown", "empty error")

    error_lower = error_text.lower()

    match = re.search(r"NameError:\s*name\s*['\"](\w+)['\"]\s*is not defined", error_text)
    if match:
        return ("NameError", f"name '{match.group(1)}' not defined")

    if "NameError" in error_text:
        return ("NameError", "undefined name")

    match = re.search(r"TypeError:\s*(.+?)(?:\n|$)", error_text)
    if match:
        return ("TypeError", match.group(1).strip())

    match = re.search(r"SyntaxError:\s*(.+?)(?:\n|$)", error_text)
    if match:
        return ("SyntaxError", match.group(1).strip())

    if "AssertionError" in error_text or "assert" in error_lower:
        return ("AssertionError", "wrong output")

    if "IndexError" in error_text:
        return ("IndexError", "index out of range")

    if "KeyError" in error_text:
        match = re.search(r"KeyError:\s*['\"]?(\w+)['\"]?", error_text)
        if match:
            return ("KeyError", f"key '{match.group(1)}' not found")
        return ("KeyError", "missing key")

    if "ImportError" in error_text or "ModuleNotFoundError" in error_text:
        return ("ImportError", "module not found")

    if "IndentationError" in error_text:
        return ("IndentationError", "bad indentation")

    if "timeout" in error_lower:
        return ("Timeout", "execution timed out")

    first_line = error_text.split("\n")[0][:80]
    return ("Other", first_line)


def infer_fix_strategy(error_type: str, error_sig: str) -> str:
    """Infer a structural fix strategy from the error type and signature."""
    if error_type == "TypeError" and "takes" in error_sig and "argument" in error_sig:
        match = re.search(r"takes\s+(\d+).*?but\s+(\d+)\s+were", error_sig)
        if match:
            return (
                f"FUNCTION SIGNATURE MISMATCH: takes {match.group(1)} args "
                f"but test calls with {match.group(2)}. Check the assert statement "
                f"and update your function's def line to match."
            )
        return "FUNCTION SIGNATURE MISMATCH: test calls your function with a different number of arguments. Check the assert and update def line."

    if error_type == "TypeError":
        if "'NoneType'" in error_sig:
            return "Function returns None. Ensure all code paths have a return statement."
        if "not subscriptable" in error_sig:
            return "Trying to index a non-list. Check the data type before indexing."
        if "not iterable" in error_sig:
            return "Trying to loop over a non-iterable. Check the input type before iterating."
        return "Type mismatch: check that the function handles expected input types."

    if error_type == "NameError":
        return "Ensure function name exactly matches what test expects. Check assert for correct name."

    if error_type == "SyntaxError":
        return "Syntax error. Check for missing colons, mismatched parentheses, or bad indentation."

    if error_type == "AssertionError":
        return "Logic error: function runs but returns wrong value. Trace through with test input step by step."

    if error_type == "IndexError":
        return "Index out of range. Check for empty lists or loop bounds exceeding length."

    if error_type == "IndentationError":
        return "Fix indentation: Python requires consistent 4-space blocks."

    return f"Error {error_type}: review message carefully and compare with expected behavior."


class ErrorPatternNode:
    """A validated error-fix pattern."""

    def __init__(self, error_type: str, error_signature: str,
                 fix_strategy: str, context: str = ""):
        self.error_type = error_type
        self.error_signature = error_signature
        self.fix_strategy = fix_strategy
        self.confidence = 1.0
        self.context = context
        self.times_seen = 1
        self.times_fixed = 0
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return {
            "error_type": self.error_type,
            "error_signature": self.error_signature,
            "fix_strategy": self.fix_strategy,
            "confidence": self.confidence,
            "context": self.context,
            "times_seen": self.times_seen,
            "times_fixed": self.times_fixed,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ErrorPatternNode":
        n = cls(
            error_type=d["error_type"],
            error_signature=d["error_signature"],
            fix_strategy=d["fix_strategy"],
            context=d.get("context", ""),
        )
        n.confidence = d.get("confidence", 1.0)
        n.times_seen = d.get("times_seen", 1)
        n.times_fixed = d.get("times_fixed", 0)
        n.timestamp = d.get("timestamp", datetime.now().isoformat())
        return n


class ErrorPatternGraph:
    """
    Graph of error patterns and their validated fixes.
    Learns empirically: every error teaches a lesson.
    """

    def __init__(self, storage_path: str = "puzzle_logic_knowledge.json"):
        self.storage_path = storage_path
        self.patterns: List[ErrorPatternNode] = []
        self.by_type: Dict[str, List[ErrorPatternNode]] = defaultdict(list)
        self._load()

    def record_error(self, error_text: str, context: str = "", code: str = "") -> str:
        """Record an error occurrence. Returns the error fingerprint."""
        err_type, err_sig = extract_error_fingerprint(error_text)

        for p in self.by_type.get(err_type, []):
            if self._similar_error(p.error_signature, err_sig):
                p.times_seen += 1
                p.confidence *= 0.95
                self._save()
                return f"{err_type}: {err_sig}"

        fix = infer_fix_strategy(err_type, err_sig)
        node = ErrorPatternNode(
            error_type=err_type,
            error_signature=err_sig,
            fix_strategy=fix,
            context=context[:200] if context else ""
        )
        self.patterns.append(node)
        self.by_type[err_type].append(node)
        self._save()
        return f"{err_type}: {err_sig}"

    def record_fix(self, error_text: str):
        """Call when an error was eventually fixed. Increases confidence."""
        err_type, err_sig = extract_error_fingerprint(error_text)
        for p in self.by_type.get(err_type, []):
            if self._similar_error(p.error_signature, err_sig):
                p.times_fixed += 1
                p.confidence = min(1.0, p.confidence + 0.1)
                self._save()
                return

    def get_fix_toolbox(self, error_text: str, top_k: int = 3) -> str:
        """
        Retrieve a toolbox of relevant error-fix patterns.

        NOT a directive -- the model evaluates each piece and decides
        whether it structurally fits the current problem.
        """
        err_type, err_sig = extract_error_fingerprint(error_text)

        candidates = []
        for p in self.by_type.get(err_type, []):
            sim = self._error_similarity(p.error_signature, err_sig)
            if sim > 0.3:
                candidates.append((sim * p.confidence, p))

        for etype, plist in self.by_type.items():
            if etype == err_type:
                continue
            for p in plist:
                sim = self._error_similarity(p.error_signature, err_sig)
                if sim > 0.7:
                    candidates.append((sim * p.confidence * 0.6, p))

        candidates.sort(key=lambda x: -x[0])

        if not candidates:
            return (
                f"[Error knowledge base: no prior patterns for {err_type}]\n"
                f"This appears to be a new error type. Analyze the error message "
                f"carefully and determine the root cause yourself."
            )

        lines = [
            f"[Error knowledge base: {err_type} -- {len(candidates)} related patterns found]",
            "Below are past errors and their validated fixes. REVIEW EACH and decide",
            "whether it structurally fits YOUR current problem. Use none, one, or combine.",
            "Do NOT blindly apply -- evaluate fit like a puzzle piece.",
            ""
        ]

        for i, (score, pattern) in enumerate(candidates[:top_k], 1):
            relevance = "high" if score > 0.7 else ("medium" if score > 0.4 else "low")
            lines.append(
                f"  Pattern {i} [relevance: {relevance}, validated {pattern.times_fixed}x]:\n"
                f"    Past error: [{pattern.error_type}] {pattern.error_signature}\n"
                f"    Validated fix: {pattern.fix_strategy}\n"
            )

        lines.append(
            "\nNow analyze YOUR error and decide which pattern (if any) applies. "
            "Then write the corrected code."
        )

        return "\n".join(lines)

    def _similar_error(self, sig1: str, sig2: str) -> bool:
        if sig1 == sig2:
            return True
        s1 = sig1.replace("'", "").replace('"', '').lower()
        s2 = sig2.replace("'", "").replace('"', '').lower()
        if s1 == s2:
            return True
        tokens1 = set(s1.split())
        tokens2 = set(s2.split())
        shared = tokens1 & tokens2
        if len(shared) >= min(len(tokens1), len(tokens2)) * 0.6:
            return True
        return False

    def _error_similarity(self, sig1: str, sig2: str) -> float:
        s1 = sig1.replace("'", "").replace('"', '').lower()
        s2 = sig2.replace("'", "").replace('"', '').lower()
        if s1 == s2:
            return 1.0
        tokens1 = set(s1.split())
        tokens2 = set(s2.split())
        if not tokens1 or not tokens2:
            return 0.0
        return len(tokens1 & tokens2) / len(tokens1 | tokens2)

    def stats(self) -> Dict:
        if not self.patterns:
            return {"n_patterns": 0, "total_seen": 0, "total_fixed": 0, "patterns": []}
        by_type_count = defaultdict(int)
        for p in self.patterns:
            by_type_count[p.error_type] += 1
        return {
            "n_patterns": len(self.patterns),
            "by_type": dict(by_type_count),
            "total_seen": sum(p.times_seen for p in self.patterns),
            "total_fixed": sum(p.times_fixed for p in self.patterns),
            "avg_confidence": sum(p.confidence for p in self.patterns) / len(self.patterns),
            "patterns": [p.to_dict() for p in self.patterns]
        }

    def print_summary(self):
        print(f"\n{bold('Error Pattern Knowledge Graph')} ({len(self.patterns)} patterns):")
        if not self.patterns:
            print("  (empty -- no patterns learned yet)")
            return
        for p in sorted(self.patterns, key=lambda x: -x.confidence):
            status = green("FIXED") if p.times_fixed > 0 else yellow("seen")
            print(f"  [{p.error_type}] {p.error_signature[:50]}")
            print(f"    Fix: {p.fix_strategy[:70]}...")
            print(f"    Confidence: {p.confidence:.2f} | {status} {p.times_seen}x | Fixed {p.times_fixed}x")

    def _save(self):
        data = {"patterns": [p.to_dict() for p in self.patterns]}
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for pd in data.get("patterns", []):
                        node = ErrorPatternNode.from_dict(pd)
                        self.patterns.append(node)
                        self.by_type[node.error_type].append(node)
            except Exception:
                pass


# ═════════════════════════════════════════════════════════════════════════
#  Code Execution (Sandbox)
# ═════════════════════════════════════════════════════════════════════════

def execute_code(python_code: str, timeout: int = 5) -> Dict:
    """
    Execute Python code in a subprocess sandbox.
    Returns: {"passed": bool, "error": str or None, "stdout": str}
    """
    if not python_code or not python_code.strip():
        return {"passed": False, "error": "No code to execute", "stdout": ""}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(python_code)
        temp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True, text=True, timeout=timeout
        )
        passed = result.returncode == 0
        error = result.stderr if not passed else None
        if error and len(error) > 500:
            error = error[:500] + "..."
        return {"passed": passed, "error": error, "stdout": result.stdout}
    except subprocess.TimeoutExpired:
        return {"passed": False, "error": "Timeout -- possible infinite loop or slow code", "stdout": ""}
    except Exception as e:
        return {"passed": False, "error": str(e), "stdout": ""}
    finally:
        try:
            os.unlink(temp_path)
        except:
            pass


# ═════════════════════════════════════════════════════════════════════════
#  Prompt Logger
# ═════════════════════════════════════════════════════════════════════════

class PromptLogger:
    """Logs every prompt/response interaction to a text file."""

    def __init__(self, path: str):
        self.path = path
        self._write_header()

    def _write_header(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("PUZZLE LOGIC AGENT -- LLM INTERACTION LOG\n")
            f.write("=" * 80 + "\n")
            f.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("Format per entry:\n")
            f.write("  [TASK] <id> | [ATTEMPT] <n> | [RESULT] PASS/FAIL\n")
            f.write("  --- PROMPT ---\n")
            f.write("  <full prompt text>\n")
            f.write("  --- RESPONSE ---\n")
            f.write("  <raw model output>\n")
            f.write("  --- EXTRACTED CODE ---\n")
            f.write("  <code after extraction>\n")
            f.write("  --- TEST RESULT ---\n")
            f.write("  <pass/fail + error>\n")
            f.write("  --- TOOLBOX USED ---\n")
            f.write("  <yes/no + which patterns>\n")
            f.write("=" * 80 + "\n\n")

    def log(self, *, task_id: str, attempt: int, result: str,
            prompt: str, raw_response: str, extracted_code: str,
            test_passed: bool, test_error: Optional[str] = None,
            toolbox_used: bool = False, toolbox_content: str = ""):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("-" * 80 + "\n")
            f.write(f"[TASK] {task_id}\n")
            f.write(f"[ATTEMPT] {attempt}\n")
            f.write(f"[RESULT]  {result}\n")
            f.write(f"[TOOLBOX] {'YES' if toolbox_used else 'NO'}\n")
            f.write("-" * 80 + "\n\n")

            f.write("--- PROMPT (sent to LLM) ---\n")
            f.write(prompt)
            f.write("\n\n")

            f.write("--- RESPONSE (raw from LLM) ---\n")
            f.write(raw_response)
            f.write("\n\n")

            f.write("--- EXTRACTED CODE ---\n")
            f.write(extracted_code if extracted_code else "(extraction failed)")
            f.write("\n\n")

            f.write("--- TEST RESULT ---\n")
            f.write(f"Passed: {test_passed}\n")
            if test_error:
                err = test_error[:500].replace("\n", "\\n")
                f.write(f"Error:  {err}\n")
            f.write("\n")

            if toolbox_used and toolbox_content:
                f.write("--- TOOLBOX CONTENT ---\n")
                f.write(toolbox_content)
                f.write("\n\n")


# ═════════════════════════════════════════════════════════════════════════
#  Core Agent: The Puzzle Logic Loop
# ═════════════════════════════════════════════════════════════════════════

class PuzzleLogicAgent:
    """
    The Puzzle Logic Agent.

    Architecture:
      Synapse (LLM) generates candidates.
      OS (ErrorPatternGraph) validates and maintains belief state.

    Loop:
      1. Generate code (clean prompt)
      2. Execute in sandbox
      3. If PASS -> learn (record fix pattern)
      4. If FAIL ->
         a. Record error
         b. Query knowledge graph for fix toolbox
         c. Retry with toolbox (model decides which pattern fits)
         d. If PASS on retry -> learn the validated fix
      5. Repeat until max attempts
    """

    def __init__(self, model: str, knowledge_path: str = "puzzle_logic_knowledge.json"):
        self.synapse = LMStudioClient(model=model)
        self.knowledge = ErrorPatternGraph(storage_path=knowledge_path)
        self.logger: Optional[PromptLogger] = None

    def solve(self, prompt: str, test_code: Optional[str] = None,
              n_attempts: int = 3, max_tokens: int = 1024,
              task_id: str = "task") -> Dict:
        """
        Solve a coding problem with the full Puzzle Logic loop.

        Args:
            prompt: The coding prompt (problem description + signature)
            test_code: Optional test code to run against the solution.
                       If provided, the solution is executed and validated.
                       If None, just returns the generated code.
            n_attempts: Max attempts (each attempt queries KG on failure)
            max_tokens: Max tokens per generation
            task_id: Identifier for logging

        Returns:
            {"code": str, "passed": bool, "attempts": int, "error": str or None,
             "used_toolbox": bool, "patterns_learned": int}
        """
        print(f"\n{bold('[Puzzle Logic Agent]')} Solving {cyan(task_id)}")
        print(f"  Knowledge: {len(self.knowledge.patterns)} patterns | "
              f"Max attempts: {n_attempts}")
        if self.logger:
            print(f"  Logging: {self.logger.path}")

        failure_history = []
        last_error = ""
        used_toolbox = False

        for attempt in range(1, n_attempts + 1):
            # Build prompt: clean on attempt 1, toolbox on retries
            error_toolbox = ""
            if failure_history and last_error:
                error_toolbox = self.knowledge.get_fix_toolbox(last_error, top_k=3)

            full_prompt = prompt
            if error_toolbox:
                full_prompt = prompt + "\n\n" + error_toolbox + "\n"
                used_toolbox = True
                print(f"\n  {yellow('[Attempt ' + str(attempt) + ']')} Using knowledge toolbox:")
                # Show compact toolbox summary
                for line in error_toolbox.split("\n")[:3]:
                    print(f"    {line}")
                if len(error_toolbox.split("\n")) > 3:
                    print(f"    ... ({len(error_toolbox.split(chr(10))) - 3} more lines)")
            else:
                print(f"\n  {cyan('[Attempt ' + str(attempt) + ']')} Clean prompt (no hints)")

            # Generate code
            print(f"    -> Querying LLM...", end=" ", flush=True)
            raw_list = self.synapse.generate(prompt=full_prompt, temperature=0.0, max_tokens=max_tokens, n=1)
            raw_text = raw_list[0] if raw_list and raw_list[0] else ""
            print("done")

            code = extract_code(raw_text)
            if not code:
                print(f"    {red('No code extracted from response')}")
                last_error = "extraction failed"
                self.knowledge.record_error("extraction failed")
                failure_history.append(last_error)
                if self.logger:
                    self.logger.log(
                        task_id=task_id, attempt=attempt, result="FAIL",
                        prompt=full_prompt, raw_response=raw_text,
                        extracted_code="(extraction failed)",
                        test_passed=False, test_error="extraction failed",
                        toolbox_used=bool(error_toolbox), toolbox_content=error_toolbox
                    )
                continue

            print(f"    Code: {code.split(chr(10))[0][:60]}...")

            # If no test code, just return the generated code (chat mode)
            if test_code is None:
                if self.logger:
                    self.logger.log(
                        task_id=task_id, attempt=attempt, result="GENERATED",
                        prompt=full_prompt, raw_response=raw_text,
                        extracted_code=code, test_passed=True, test_error=None,
                        toolbox_used=bool(error_toolbox), toolbox_content=error_toolbox
                    )
                return {
                    "code": code, "passed": True, "attempts": attempt,
                    "error": None, "used_toolbox": used_toolbox,
                    "patterns_learned": 0
                }

            # Execute the code with the test
            test_program = prompt + "\n" + code + "\n" + test_code + "\n"
            print(f"    -> Executing...", end=" ", flush=True)
            result = execute_code(test_program)

            if result["passed"]:
                print(f"{green('PASSED')}")
                if last_error:
                    self.knowledge.record_fix(last_error)
                if self.logger:
                    self.logger.log(
                        task_id=task_id, attempt=attempt, result="PASS",
                        prompt=full_prompt, raw_response=raw_text,
                        extracted_code=code, test_passed=True, test_error=None,
                        toolbox_used=bool(error_toolbox), toolbox_content=error_toolbox
                    )
                return {
                    "code": code, "passed": True, "attempts": attempt,
                    "error": None, "used_toolbox": used_toolbox,
                    "patterns_learned": len(self.knowledge.patterns)
                }
            else:
                error_text = result.get("error", "unknown")
                print(f"{red('FAILED')} -- {yellow(error_text[:80])}")
                self.knowledge.record_error(error_text, context=prompt[:200], code=code)
                failure_history.append(error_text)
                last_error = error_text
                if self.logger:
                    self.logger.log(
                        task_id=task_id, attempt=attempt, result="FAIL",
                        prompt=full_prompt, raw_response=raw_text,
                        extracted_code=code, test_passed=False, test_error=error_text,
                        toolbox_used=bool(error_toolbox), toolbox_content=error_toolbox
                    )

        # All attempts exhausted
        print(f"\n  {red('All ' + str(n_attempts) + ' attempts failed.')}")
        return {
            "code": code if 'code' in dir() else "",
            "passed": False, "attempts": n_attempts,
            "error": last_error, "used_toolbox": used_toolbox,
            "patterns_learned": len(self.knowledge.patterns)
        }

    def fix_file(self, file_path: str, test_path: Optional[str] = None,
                 n_attempts: int = 3, max_tokens: int = 1024) -> Dict:
        """
        Fix a Python file. If a test file is provided, validates the fix.
        """
        if not os.path.exists(file_path):
            return {"code": "", "passed": False, "error": f"File not found: {file_path}"}

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        test_code = None
        if test_path and os.path.exists(test_path):
            with open(test_path, "r", encoding="utf-8") as f:
                test_code = f.read()

        prompt = (
            f"Here is a Python file that needs to be fixed:\n\n"
            f"```python\n{content}\n```\n\n"
            f"Write the complete corrected Python code. "
            f"Output only the corrected code in a markdown code block."
        )

        return self.solve(prompt, test_code=test_code, n_attempts=n_attempts,
                         max_tokens=max_tokens, task_id=os.path.basename(file_path))

    def generate_code(self, request: str, n_attempts: int = 3,
                      max_tokens: int = 1024) -> Dict:
        """Generate code from a natural language request."""
        prompt = (
            f"{request}\n\n"
            f"Write clean, correct Python code. "
            f"Output only the code in a markdown code block."
        )
        return self.solve(prompt, test_code=None, n_attempts=1,
                         max_tokens=max_tokens, task_id="generate")

    def show_stats(self):
        """Display knowledge graph statistics."""
        stats = self.knowledge.stats()
        print(f"\n{bold('Knowledge Graph Statistics')}")
        print(f"  Total patterns: {stats['n_patterns']}")
        print(f"  Total errors seen: {stats.get('total_seen', 0)}")
        print(f"  Total fixes validated: {stats.get('total_fixed', 0)}")
        if stats['n_patterns'] > 0:
            print(f"  Average confidence: {stats['avg_confidence']:.2f}")
            print(f"\n{bold('By error type:')}")
            for etype, count in sorted(stats.get('by_type', {}).items(), key=lambda x: -x[1]):
                print(f"    {etype}: {count}")
        self.knowledge.print_summary()


# ═════════════════════════════════════════════════════════════════════════
#  CLI
# ═════════════════════════════════════════════════════════════════════════

def print_banner():
    print(cyan(r"""
    ____       _       _         _            _   _
   |  _ \ _   _| | __ _| | ____ _| | ___  __ _| |_(_) ___  _ __
   | |_) | | | | |/ _` | |/ / _` | |/ _ \/ _` | __| |/ _ \| '_ \
   |  __/| |_| | | (_| |   < (_| | |  __/ (_| | |_| | (_) | | | |
   |_|    \__, |_|\__,_|_|\_\__, |_|\___|\__,_|\__|_|\___/|_| |_|
          |___/                |___/
    ____                            _       _
   |  _ \  ___  _ __ ___   ___   __| |_   _| | ___  ___
   | | | |/ _ \| '_ ` _ \ / _ \ / _` | | | | |/ _ \/ __|
   | |_| | (_) | | | | | | (_) | (_| | |_| | |  __/\__ \
   |____/ \___/|_| |_| |_|\___/ \__,_|\__,_|_|\___||___/
    """))
    print(bold("    v2.0 -- Puzzle Logic: Empirical Constraint Satisfaction\n"))


def main():
    parser = argparse.ArgumentParser(
        description="Puzzle Logic Agent -- AI coding with empirical validation and learning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fix a file (no tests)
  python puzzle_logic_agent.py my_script.py --model qwen2.5-coder-3b-instruct

  # Fix a file with tests (runs code, catches errors, learns)
  python puzzle_logic_agent.py my_script.py --test test_my_script.py --model qwen2.5-coder-3b-instruct

  # Generate code from description
  python puzzle_logic_agent.py --generate "Write a function to reverse a list" --model qwen2.5-coder-3b-instruct

  # Show knowledge graph stats
  python puzzle_logic_agent.py --stats
        """
    )
    parser.add_argument("file", nargs="?", help="Python file to fix/generate")
    parser.add_argument("--model", type=str, default=None, help="LM Studio model ID")
    parser.add_argument("--test", type=str, default=None, help="Test file to validate against")
    parser.add_argument("--generate", type=str, default=None, help="Natural language coding request")
    parser.add_argument("--attempts", type=int, default=3, help="Max attempts per problem (default: 3)")
    parser.add_argument("--max-tokens", type=int, default=1024, help="Max tokens per generation")
    parser.add_argument("--knowledge", type=str, default="puzzle_logic_knowledge.json", help="Knowledge base path")
    parser.add_argument("--stats", action="store_true", help="Show knowledge base statistics and exit")
    parser.add_argument("--log", type=str, default=None, help="Log all LLM interactions to file")
    parser.add_argument("--timeout", type=int, default=5, help="Test execution timeout in seconds (default: 5)")
    args = parser.parse_args()

    print_banner()

    # Stats mode
    if args.stats:
        agent = PuzzleLogicAgent(model="", knowledge_path=args.knowledge)
        agent.show_stats()
        return

    # Auto-detect model
    model = args.model
    if not model:
        try:
            import requests
            r = requests.get("http://localhost:1234/v1/models", timeout=5)
            data = r.json()
            model = data["data"][0]["id"]
            print(f"Auto-detected model: {bold(model)}")
        except Exception:
            print(red("[Error] Could not detect model. Use --model or start LM Studio."))
            sys.exit(1)

    agent = PuzzleLogicAgent(model=model, knowledge_path=args.knowledge)

    if not agent.synapse.check_health():
        print(red("[Error] LM Studio not running on localhost:1234"))
        print("Start LM Studio, load a model, and click 'Start Server' in the Developer tab.")
        sys.exit(1)

    print(green("LM Studio connected OK"))

    # Set up logger
    if args.log:
        agent.logger = PromptLogger(args.log)
        print(f"Logging to: {args.log}")

    # Generate mode
    if args.generate:
        result = agent.generate_code(args.generate, n_attempts=1, max_tokens=args.max_tokens)
        print(f"\n{bold('=' * 60)}")
        print(bold("GENERATED CODE:"))
        print("=" * 60)
        print(result.get("code", "(no code generated)"))
        print("=" * 60)
        return

    # File fix mode
    if args.file:
        if not os.path.exists(args.file):
            print(red(f"[Error] File not found: {args.file}"))
            sys.exit(1)

        test_code = None
        if args.test:
            if not os.path.exists(args.test):
                print(red(f"[Error] Test file not found: {args.test}"))
                sys.exit(1)
            with open(args.test, "r", encoding="utf-8") as f:
                test_code = f.read()
            print(f"Test file: {args.test}")

        result = agent.fix_file(args.file, test_path=args.test,
                               n_attempts=args.attempts, max_tokens=args.max_tokens)

        print(f"\n{bold('=' * 60)}")
        if result["passed"]:
            print(f"{green('RESULT: SUCCESS')} in {result['attempts']} attempt(s)")
            if result.get("used_toolbox"):
                print(f"  {yellow('Knowledge toolbox was used to guide the fix')}")
        else:
            print(f"{red('RESULT: FAILED')} after {result['attempts']} attempt(s)")
            if result.get("error"):
                print(f"  Last error: {red(result['error'][:100])}")

        if result.get("code"):
            print(f"\n{bold('CODE:')}")
            print("-" * 60)
            print(result["code"])
            print("-" * 60)

        agent.show_stats()
        return

    # No arguments
    parser.print_help()


if __name__ == "__main__":
    main()
