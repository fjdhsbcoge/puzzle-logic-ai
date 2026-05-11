"""
Puzzle Logic Agent v4.0  --  Personality-Aware Constraint Satisfaction
=====================================================================

Three-tier execution:

  1. CONSTRAINT ENGINE (v3.0) — Local errors: AST-based structural auto-fix
  2. PERSONALITY TOOLBOX (v4.0) — Unlocal errors: OCEAN-C weighted patterns
  3. RAW ERROR (Basic V2) — Fallback: strategy rotation

Model-level personality adapts system prompts, toolbox size, and retry temperature.
Pattern-level personality controls individual decay rates and selection scores.

Usage:
  python puzzle_logic_agent.py my_script.py --model qwen2.5-coder-3b-instruct
  python puzzle_logic_agent.py my_script.py --test test_my_script.py --attempts 3
  python puzzle_logic_agent.py --generate "Write a function..."
  python puzzle_logic_agent.py --stats
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

# ═══════════════════════════════════════════════════════════════════════
#  Shared utilities (extracted to utils.py — deepened module boundary)
# ═══════════════════════════════════════════════════════════════════════

from utils import (
    extract_error_fingerprint, infer_fix_strategy, compute_locality,
    code_delta, same_pattern, sig_similarity, extract_func_name,
    extract_code, execute_code,
)

# ═══════════════════════════════════════════════════════════════════════
#  v4.0 — Personality + Constraint Engine Imports
# ═══════════════════════════════════════════════════════════════════════

try:
    from personality_engine import (
        PersonalityKnowledgeGraph,
        PersonalityPatternNode,
        PatternPersonality,
    )
    from model_personality import (
        PersonalityAwareKnowledgeGraph,
        ModelPersonality,
        PersonalityPromptBuilder,
        PersonalityAggregator,
    )
    from constraint_engine import HybridConstraintEngine
    V4_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] v4.0 engine imports failed: {e}")
    V4_AVAILABLE = False
    PersonalityKnowledgeGraph = None
    PersonalityAwareKnowledgeGraph = None
    HybridConstraintEngine = None

# ═══════════════════════════════════════════════════════════════════════
#  v3.5 Legacy fallback (deepened to legacy.py)
# ═══════════════════════════════════════════════════════════════════════

if not V4_AVAILABLE:
    from legacy import CoherentKnowledgeGraph, ErrorPatternNode
else:
    # Legacy not needed at import time, but keep name available for type hints
    CoherentKnowledgeGraph = None
    ErrorPatternNode = None


# ═══════════════════════════════════════════════════════════════════════
#  Color utilities (terminal output)
# ═══════════════════════════════════════════════════════════════════════

def cyan(s):   return f"\033[36m{s}\033[0m"
def green(s):  return f"\033[32m{s}\033[0m"
def red(s):    return f"\033[31m{s}\033[0m"
def yellow(s): return f"\033[33m{s}\033[0m"
def bold(s):   return f"\033[1m{s}\033[0m"


# ═══════════════════════════════════════════════════════════════════════
#  Strategy Rotation (Basic V2)
# ═══════════════════════════════════════════════════════════════════════

class StrategyExtractor:
    """Guess what fix strategy was tried from a code diff."""

    RULES = [
        ("add parameter",       lambda d: "def " in d and "," in d),
        ("remove parameter",    lambda d: "def " in d and "," not in d and "():" in d),
        ("change return value",   lambda d: "return " in d),
        ("add import",          lambda d: "import " in d or "from " in d),
        ("change operator",     lambda d: any(op in d for op in [" + ", " - ", " * ", " / ", " % ", " ** ", " // ", " == ", " != ", " < ", " > "])),
        ("change condition",    lambda d: "if " in d or "else:" in d or "elif " in d),
        ("add loop",            lambda d: "for " in d or "while " in d),
        ("add guard/check",     lambda d: any(g in d for g in ["if not", "if len", "if isinstance", "if type", "try:", "except"])),
        ("change variable",     lambda d: " = " in d and not "==" in d),
        ("change function name",lambda d: "def " in d),
    ]

    def extract(self, old_code: str, new_code: str) -> str:
        """Guess the strategy from the code delta."""
        if not old_code or not new_code:
            return "unknown"
        old_lines = set(l.strip() for l in old_code.strip().split("\n") if l.strip())
        new_lines = set(l.strip() for l in new_code.strip().split("\n") if l.strip())
        delta_lines = list(old_lines.symmetric_difference(new_lines))
        delta_text = "\n".join(delta_lines)

        for name, test in self.RULES:
            if test(delta_text):
                return name
        return "code change"


class AttemptTracker:
    """Tracks strategies tried within a single problem to avoid repetition."""

    def __init__(self):
        self.attempts: List[Dict] = []

    def record(self, error_type: str, old_code: str, new_code: str, passed: bool):
        strategy = StrategyExtractor().extract(old_code, new_code)
        self.attempts.append({
            "error_type": error_type,
            "strategy": strategy,
            "passed": passed,
        })

    def get_rotation_hint(self) -> str:
        """Generate a hint about what NOT to try again."""
        failed = [a["strategy"] for a in self.attempts if not a["passed"]]
        if not failed:
            return ""
        seen = set()
        unique_failed = []
        for s in failed:
            if s not in seen:
                seen.add(s)
                unique_failed.append(s)

        lines = [
            "",
            "[Strategy rotation -- do NOT repeat what already failed]",
            f"Failed approaches for this problem: {', '.join(unique_failed)}",
            "Try a completely different strategy. Think about what the error REALLY means.",
        ]
        return "\n".join(lines)

    def get_successful_strategy(self) -> str:
        """Return the strategy that worked, if any."""
        for a in reversed(self.attempts):
            if a["passed"]:
                return a["strategy"]
        return ""


# ═══════════════════════════════════════════════════════════════════════
#  LLM Client
# ═══════════════════════════════════════════════════════════════════════

class LMStudioClient:
    EMPIRICAL_SYSTEM_PROMPT = "You are a helpful coding assistant. Write clean, correct Python code."

    def __init__(self, base_url="http://localhost:1234/v1", model=None, timeout=300):
        self.base_url      = base_url.rstrip("/")
        self.model         = model
        self.timeout       = timeout
        self.chat_endpoint = f"{self.base_url}/chat/completions"

    def generate(self, prompt, system_message=None, temperature=0.0, max_tokens=1024, n=1):
        import requests
        messages = [
            {"role": "system", "content": system_message or self.EMPIRICAL_SYSTEM_PROMPT},
            {"role": "user",   "content": prompt}
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
                    response = requests.post(self.chat_endpoint, json=payload,
                                              timeout=self.timeout)
                    response.raise_for_status()
                    data = response.json()
                    break
                except requests.exceptions.ReadTimeout:
                    print(yellow(f"  [Timeout] Retry {attempt+1}/3..."))
                    time.sleep(2 ** attempt)
                    if attempt == 2:
                        candidates.append("")
                        break
                except Exception as e:
                    print(red(f"  [Error] {e}"))
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
        text = re.sub(r" thinking.*?end thinking ", "", text, flags=re.DOTALL)
        return text.strip()

    def check_health(self):
        try:
            import requests
            return requests.get(f"{self.base_url}/models", timeout=5).status_code == 200
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════════
#  v4.0 Core Agent — Integrated Personality + Constraint Engine
# ═══════════════════════════════════════════════════════════════════════

class PuzzleLogicAgent:
    """
    v4.0 — Three-tier execution:
      1. Constraint Engine (AST auto-fix for local errors)
      2. Personality Toolbox (OCEAN-C weighted pattern selection)
      3. Raw Error + Strategy Rotation (Basic V2 fallback)
    """

    def __init__(self, model: str, knowledge_path: str = "puzzle_logic_knowledge.json"):
        self.synapse   = LMStudioClient(model=model)
        self.logger    = None

        if V4_AVAILABLE:
            pattern_graph = PersonalityKnowledgeGraph(storage_path=knowledge_path)
            self.knowledge = PersonalityAwareKnowledgeGraph(pattern_graph)
            self.constraint_engine = HybridConstraintEngine()
            self.v4_mode = True
        else:
            self.knowledge = CoherentKnowledgeGraph(storage_path=knowledge_path)
            self.constraint_engine = None
            self.v4_mode = False

    def solve(self, prompt: str, test_code: str = None, n_attempts: int = 3,
              max_tokens: int = 1024, task_id: str = "task",
              mode: str = "advanced") -> Dict:
        """
        mode = "baseline"  -- clean attempts, no error info
        mode = "basic"     -- raw error + strategy rotation (Basic V2)
        mode = "advanced"  -- constraint engine + personality toolbox (v4.0)
        """
        print(f"\n{bold('[Puzzle Logic]')} {cyan(task_id)}  [mode={mode}]")

        if self.v4_mode:
            self.knowledge.refresh_model_personality()
            mp = self.knowledge.model_personality
            print(f"  Model: {mp}")
            print(f"  Patterns: {len(self.knowledge.patterns.patterns)} | Ω={self.knowledge.patterns.omega:.3f}")
        else:
            print(f"  Knowledge: {len(self.knowledge.patterns)} patterns | Ω={self.knowledge.omega}")

        failure_history   = []
        last_error        = ""
        last_failing_code = ""
        used_toolbox      = False
        used_constraint   = False
        shown_patterns    = []
        tracker = AttemptTracker() if mode in ("basic", "advanced") else None

        for attempt in range(1, n_attempts + 1):
            full_prompt = prompt
            shown_patterns = []
            ce_hint = ""

            if failure_history and last_error:
                if mode == "baseline":
                    pass
                elif mode == "basic":
                    rotation = tracker.get_rotation_hint() if tracker else ""
                    full_prompt = (
                        prompt + "\n\n"
                        f"[Previous attempt FAILED with this error:]\n"
                        f"```\n{last_error}\n```\n"
                        f"Fix the code based on this error message.{rotation}"
                    )
                elif mode == "advanced":
                    # v4.0: Constraint Engine (first line of defense)
                    if self.v4_mode and self.constraint_engine:
                        err_fp = extract_error_fingerprint(last_error)
                        err_type = err_fp[0]
                        locality_info = self.knowledge.patterns.record_error(
                            last_error, context=prompt[:200], code=last_failing_code
                        )
                        locality = locality_info.get("locality", 0.5)

                        ce_prompt = self.constraint_engine.build_toolbox_prompt(
                            error_type=err_type, error_sig=err_fp[1],
                            failing_code=last_failing_code, test_code=test_code or "",
                            locality=locality, pattern_fix="", pattern_context="",
                        )
                        if ce_prompt:
                            used_constraint = True
                            ce_hint = f"\n[Structural Analysis] {ce_prompt}\n"

                    # v4.0: Personality-Weighted Toolbox
                    if self.v4_mode:
                        toolbox_text, shown_patterns = self.knowledge.get_toolbox(
                            last_error, last_failing_code
                        )
                    else:
                        toolbox_text, shown_patterns = self.knowledge.get_coherent_toolbox(
                            last_error, top_k=3
                        )

                    if toolbox_text:
                        full_prompt = prompt + "\n\n" + toolbox_text + ce_hint + "\n"
                        used_toolbox = True
                    else:
                        rotation = tracker.get_rotation_hint() if tracker else ""
                        full_prompt = (
                            prompt + "\n\n"
                            f"[Previous attempt FAILED with this error:]\n"
                            f"```\n{last_error}\n```\n"
                            f"Fix the code based on this error message.{rotation}{ce_hint}"
                        )

            # Adaptive system prompt for v4.0
            system_prompt = None
            temperature = 0.0
            if self.v4_mode and mode == "advanced":
                system_prompt = self.knowledge.get_system_prompt()
                temperature = self.knowledge.model_personality.retry_temperature()

            print(f"\n  {yellow('[Attempt ' + str(attempt) + ']')} ", end="")
            if mode == "advanced":
                if used_constraint and not used_toolbox:
                    print(f"{cyan('[constraint engine]')}")
                elif used_toolbox:
                    print(f"{yellow('[personality toolbox]')}")
                elif failure_history:
                    print(f"{yellow('[raw error + rotation]')}")
                else:
                    print(f"{cyan('[clean]')}")
            elif mode == "basic" and failure_history:
                print(f"{yellow('[raw error + rotation]')}")
            else:
                print(f"{cyan('[clean]')}")

            print(f"    -> LLM (temp={temperature})...", end=" ", flush=True)
            raw_list = self.synapse.generate(
                prompt=full_prompt,
                system_message=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens, n=1
            )
            raw_text = raw_list[0] if raw_list else ""
            print("done")

            code = extract_code(raw_text)
            if not code:
                print(f"    {red('No code extracted')}")
                last_error = "extraction failed"
                if self.v4_mode:
                    self.knowledge.patterns.record_error("extraction failed")
                else:
                    self.knowledge.record_error("extraction failed")
                failure_history.append(last_error)
                if tracker:
                    tracker.record("extraction", "", "", False)
                continue

            print(f"    Code: {code.split(chr(10))[0][:60]}...")

            if test_code is None:
                return {
                    "code": code, "passed": True, "attempts": attempt,
                    "error": None, "used_toolbox": used_toolbox,
                    "used_constraint": used_constraint,
                    "patterns_learned": len(self.knowledge.patterns.patterns) if self.v4_mode else len(self.knowledge.patterns),
                }

            test_program = prompt + "\n" + code + "\n" + test_code + "\n"
            print(f"    -> Exec...", end=" ", flush=True)
            result = execute_code(test_program)

            if result["passed"]:
                print(f"{green('PASS')}")
                if last_error:
                    if self.v4_mode:
                        self.knowledge.patterns.record_fix(
                            last_error, failing_code=last_failing_code, fixed_code=code,
                            llm_client=self.synapse, ingredients=shown_patterns
                        )
                    else:
                        self.knowledge.record_fix(last_error, failing_code=last_failing_code,
                                                   fixed_code=code, llm_client=self.synapse)
                if tracker:
                    tracker.record(extract_error_fingerprint(last_error)[0],
                                     last_failing_code, code, True)
                return {
                    "code": code, "passed": True, "attempts": attempt,
                    "error": None, "used_toolbox": used_toolbox,
                    "used_constraint": used_constraint,
                    "patterns_learned": len(self.knowledge.patterns.patterns) if self.v4_mode else len(self.knowledge.patterns),
                }
            else:
                error_text = result.get("error", "unknown")
                print(f"{red('FAIL')} -- {yellow(error_text[:80])}")
                if self.v4_mode:
                    self.knowledge.patterns.record_error(error_text, context=prompt[:200], code=code)
                    if mode == "advanced" and used_toolbox and shown_patterns:
                        self.knowledge.patterns.record_toolbox_failure(shown_patterns)
                else:
                    self.knowledge.record_error(error_text, context=prompt[:200], code=code)
                    if mode == "advanced" and used_toolbox and shown_patterns:
                        self.knowledge.record_toolbox_failure(shown_patterns)
                failure_history.append(error_text)
                if tracker:
                    tracker.record(extract_error_fingerprint(error_text)[0],
                                     last_failing_code, code, False)
                last_error = error_text
                last_failing_code = code

        print(f"\n  {red('All ' + str(n_attempts) + ' attempts failed.')}")
        return {
            "code": code if 'code' in dir() else "", "passed": False,
            "attempts": n_attempts, "error": last_error,
            "used_toolbox": used_toolbox,
            "used_constraint": used_constraint,
            "patterns_learned": len(self.knowledge.patterns.patterns) if self.v4_mode else len(self.knowledge.patterns),
        }

    def show_stats(self):
        if self.v4_mode:
            self.knowledge.patterns.print_summary()
            self.knowledge.print_model_character()
        else:
            self.knowledge.print_summary()


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

def print_banner():
    print(cyan(r"""
    ____       _       _         _            _   _
   |  _ \_   _| | __ _| | ____ _| | ___  __ _| |_(_) ___  _ __
   | |_) | | | | |/ _` | |/ / _` | |/ _ \/ _` | __| |/ _ \| '_ \
   |  __/| |_| | | (_| |   < (_| | |  __/ (_| | |_| | (_) | | | |
   |_|    \__, |_\__, |_|\_\__, |_|\___|\__,_|\__|_|\___/|_| |_|
          |___/    |___/    |___/
    ____                            _       _
   |  _ \  ___  _ __ ___   ___   __| |_   _| | ___  ___
   | | | |/ _ \| '_ ` _ \ / _ \ / _` | | | | |/ _ \/ __|
   | |_| | (_) | | | | | | (_) | (_| | |_| | |  __/\__ \
   |____/ \___/|_| |_| |_|\___/ \__,_|\__,_|_|\___||___/
    """))
    print(bold("    v4.0 -- Constraint Engine + OCEAN-C Personality + Basic V2 Fallback\n"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", nargs="?")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--test", type=str, default=None)
    parser.add_argument("--generate", type=str, default=None)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--knowledge", type=str, default="puzzle_logic_knowledge.json")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--mode", type=str, default="advanced", choices=["baseline", "basic", "advanced"],
                        help="Mode: baseline | basic | advanced")
    args = parser.parse_args()

    print_banner()

    if args.stats:
        agent = PuzzleLogicAgent(model="", knowledge_path=args.knowledge)
        agent.show_stats()
        return

    model = args.model
    if not model:
        try:
            import requests
            r = requests.get("http://localhost:1234/v1/models", timeout=5)
            model = r.json()["data"][0]["id"]
            print(f"Auto-detected: {bold(model)}")
        except Exception:
            print(red("[Error] Model not detected. Start LM Studio server."))
            sys.exit(1)

    agent = PuzzleLogicAgent(model=model, knowledge_path=args.knowledge)
    if not agent.synapse.check_health():
        print(red("[Error] LM Studio not running on localhost:1234"))
        sys.exit(1)
    print(green("LM Studio connected OK"))

    if args.generate:
        result = agent.solve(args.generate, n_attempts=1, max_tokens=args.max_tokens, mode="baseline")
        print(result.get("code", "(no code)"))
        return

    if args.file:
        if not os.path.exists(args.file):
            print(red(f"[Error] File not found: {args.file}"))
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as f:
            code = f.read()
        test_code = None
        if args.test and os.path.exists(args.test):
            with open(args.test, "r", encoding="utf-8") as f:
                test_code = f.read()
        result = agent.solve(code, test_code=test_code, n_attempts=args.attempts,
                             max_tokens=args.max_tokens, mode=args.mode)
        print(f"\n{bold('=' * 60)}")
        if result["passed"]:
            print(f"{green('SUCCESS')} in {result['attempts']} attempt(s)")
        else:
            print(f"{red('FAILED')} after {result['attempts']} attempt(s)")
        if result.get("code"):
            print(result["code"])
        return

    print("No input provided. Use --generate, --file, or --stats.")


if __name__ == "__main__":
    main()
