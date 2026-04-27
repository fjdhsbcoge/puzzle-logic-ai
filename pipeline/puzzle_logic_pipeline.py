"""
Puzzle Logic Pipeline for Open WebUI
=====================================

An Open WebUI Filter Pipeline that brings empirical constraint satisfaction
to any chat. Works with LM Studio, Ollama, or any OpenAI-compatible backend.

What it does:
  1. Detects file attachments in chat messages
  2. Builds structured prompts with explicit file analysis instructions
  3. After LLM responds: extracts code, runs in sandbox, catches errors
  4. Queries Error-Pattern Knowledge Graph for fix hints on failure
  5. Retries with toolbox hints until code passes or max attempts reached
  6. Returns formatted result with execution status

Install:
    pip install open-webui
    open-webui serve

Setup:
    1. Copy this file to your Open WebUI pipelines directory
       (usually ~/.config/open-webui/pipelines/ or set via PIPELINES_DIR)
    2. In Open WebUI chat, select "Puzzle Logic" from the model dropdown
    3. Attach code files (drag & drop), type your request, send

The pipeline uses puzzle_logic_agent.py as its engine. Both files must be
in the same directory (or adjust the import path below).
"""

import os
import sys
import re
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

# Try to import from adjacent puzzle_logic_agent.py
try:
    from puzzle_logic_agent import (
        ErrorPatternGraph, execute_code, extract_code,
        extract_error_fingerprint, infer_fix_strategy,
    )
except ImportError:
    # If pipeline is in a different directory, try adding parent to path
    _here = os.path.dirname(os.path.abspath(__file__))
    _parent = os.path.dirname(_here)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from puzzle_logic_agent import (
        ErrorPatternGraph, execute_code, extract_code,
        extract_error_fingerprint, infer_fix_strategy,
    )


# ═════════════════════════════════════════════════════════════════════════
#  Pipeline Class (Open WebUI Filter API)
# ═════════════════════════════════════════════════════════════════════════

class Pipeline:
    """
    Open WebUI Filter Pipeline.

    Hooks:
      inlet(body, user)  -> modify request BEFORE LLM
      outlet(body, user) -> modify response AFTER LLM
    """

    class Valves:
        """Configuration exposed in Open WebUI UI."""
        def __init__(self):
            # Connect to all models
            self.pipelines = ["*"]
            # Run before other filters
            self.priority = 0
            # Max retry attempts for code execution
            self.max_attempts = 3
            # Knowledge base file path
            self.knowledge_path = "puzzle_logic_knowledge.json"
            # Whether to auto-execute code found in responses
            self.auto_execute = True
            # Timeout for code sandbox (seconds)
            self.sandbox_timeout = 5

    def __init__(self):
        self.type = "filter"
        self.name = "Puzzle Logic"
        self.valves = self.Valves()
        self.knowledge = None
        self._init_knowledge()

    def _init_knowledge(self):
        path = getattr(self.valves, 'knowledge_path', 'puzzle_logic_knowledge.json')
        self.knowledge = ErrorPatternGraph(storage_path=path)

    async def on_startup(self):
        print(f"[{self.name}] Pipeline started. Patterns loaded: {len(self.knowledge.patterns)}")

    async def on_shutdown(self):
        print(f"[{self.name}] Pipeline stopped.")

    # ─── inlet: before LLM ──────────────────────────────────────────────

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        """
        Intercept request before it goes to the LLM.
        Extract attached files, build structured prompt with analysis instructions.
        """
        messages = body.get("messages", [])
        if not messages:
            return body

        last_msg = messages[-1]
        if last_msg.get("role") != "user":
            return body

        content = last_msg.get("content", "")
        if not content:
            return body

        # Check if message has file attachments (Open WebUI format)
        files = self._extract_files_from_message(content)

        if files:
            # Rebuild the last user message with structured prompt
            structured = self._build_structured_prompt(content, files)
            messages[-1]["content"] = structured
            body["messages"] = messages

            # Also inject a system message if not present
            body = self._ensure_system_prompt(body, has_files=True)

        return body

    # ─── outlet: after LLM ──────────────────────────────────────────────

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        """
        Intercept response after LLM returns.
        Extract code, execute in sandbox, catch errors, retry with knowledge.
        """
        if not self.valves.auto_execute:
            return body

        choices = body.get("choices", [])
        if not choices:
            return body

        msg = choices[0].get("message", {})
        content = msg.get("content", "")
        if not content:
            return body

        # Extract code from response
        code = extract_code(content)
        if not code:
            return body

        # Check if the user requested code execution (simple heuristic)
        user_messages = [m.get("content", "") for m in body.get("messages", []) if m.get("role") == "user"]
        last_user = user_messages[-1] if user_messages else ""
        should_execute = self._should_execute(last_user, content)

        if not should_execute:
            return body

        # Run the Puzzle Logic execution loop
        result = self._execute_with_retries(code, last_user)

        # Append execution result to the assistant's response
        if result["attempts"] > 0:
            status_emoji = "✅" if result["passed"] else "❌"
            extra = f"\n\n---\n**Execution Result:** {status_emoji} {'PASSED' if result['passed'] else 'FAILED'}"
            if result["attempts"] > 1:
                extra += f" (after {result['attempts']} attempts)"
            if result.get("error"):
                extra += f"\n```\n{result['error'][:300]}\n```"
            if result.get("used_toolbox"):
                extra += "\n🔧 Knowledge toolbox was used."

            msg["content"] = content + extra
            choices[0]["message"] = msg
            body["choices"] = choices

        return body

    # ─── Helpers ────────────────────────────────────────────────────────

    def _extract_files_from_message(self, content: str) -> List[Dict[str, str]]:
        """Extract file attachments from Open WebUI message content."""
        files = []

        # Open WebUI embeds files as markdown images or file references
        # Pattern: [File: filename](path) or ```language blocks from uploads
        file_refs = re.findall(r'\[File:\s*([^\]]+)\]', content)
        for ref in file_refs:
            # Try to find associated code block
            block_match = re.search(
                rf'\[File:\s*{re.escape(ref)}\].*?```(\w+)?\n(.*?)```',
                content, re.DOTALL
            )
            if block_match:
                lang = block_match.group(1) or "text"
                code = block_match.group(2)
                files.append({"name": ref.strip(), "lang": lang, "content": code})

        # Also detect raw code blocks that look like file uploads
        # (when user pastes code directly)
        if not files:
            code_blocks = re.findall(r'```(\w+)?\n(.*?)```', content, re.DOTALL)
            for lang, code in code_blocks:
                if len(code) > 20 and any(kw in code for kw in ['def ', 'class ', 'import ', 'function ', 'from ']):
                    ext = (lang or "py").lower()
                    if ext in ('py', 'python', ''):
                        ext = "py"
                    files.append({"name": f"code_snippet.{ext}", "lang": lang or "python", "content": code})

        return files

    def _build_structured_prompt(self, original: str, files: List[Dict]) -> str:
        """Build a prompt that forces the model to analyze attached files."""
        lines = [
            f"I have attached {len(files)} file(s). Please read them carefully, then respond to my request.",
            "",
            "=== MY REQUEST ===",
            original,
            "",
            "=== ATTACHED FILES ===",
        ]
        for f in files:
            lines.append(f"[File: {f['name']}]")
            lines.append(f"```{f['lang']}")
            lines.append(f["content"])
            lines.append("```")
            lines.append("")
        lines.append("=== YOUR ANALYSIS ===")
        lines.append(
            "Provide a thorough response. If I asked you to improve/fix code, give the COMPLETE improved version. "
            "Reference specific functions and lines. Be specific, not generic."
        )
        return "\n".join(lines)

    def _ensure_system_prompt(self, body: dict, has_files: bool = False) -> dict:
        """Inject or update system prompt in messages array."""
        messages = body.get("messages", [])

        # Find existing system message
        sys_idx = None
        for i, m in enumerate(messages):
            if m.get("role") == "system":
                sys_idx = i
                break

        if has_files:
            sys_text = (
                "You are a senior software engineer. When the user attaches code files, "
                "you MUST read and analyze them carefully. Reference specific functions, "
                "variables, and line numbers. If asked to fix or improve code, output the "
                "COMPLETE corrected code in a markdown block. Be thorough and specific, never generic."
            )
        else:
            sys_text = "You are a helpful coding assistant. Write clean, correct code."

        if sys_idx is not None:
            messages[sys_idx]["content"] = sys_text
        else:
            messages.insert(0, {"role": "system", "content": sys_text})

        body["messages"] = messages
        return body

    def _should_execute(self, user_prompt: str, assistant_response: str) -> bool:
        """Heuristic: should we auto-execute code from the response?"""
        # Execute if user asked to run/fix/test/check code
        action_words = ['run', 'execute', 'test', 'fix', 'check', 'debug', 'try', 'verify', 'advance']
        user_lower = user_prompt.lower()
        has_action = any(w in user_lower for w in action_words)

        # And assistant gave us code
        has_code = '```' in assistant_response and any(kw in assistant_response for kw in ['def ', 'class ', 'import '])

        return has_action and has_code

    def _execute_with_retries(self, code: str, context: str) -> Dict:
        """Run Puzzle Logic execution loop on extracted code."""
        failure_history = []
        last_error = ""
        used_toolbox = False
        max_attempts = getattr(self.valves, 'max_attempts', 3)
        timeout = getattr(self.valves, 'sandbox_timeout', 5)

        for attempt in range(1, max_attempts + 1):
            # On retry, query knowledge graph for hints
            error_toolbox = ""
            if failure_history and last_error and attempt > 1:
                error_toolbox = self.knowledge.get_fix_toolbox(last_error, top_k=3)
                used_toolbox = True
                # Prepend fix hints as comments in the code
                if error_toolbox:
                    code = f"# FIX HINT: {error_toolbox[:200]}\n{code}"

            # Execute
            result = execute_code(code, timeout=timeout)

            if result["passed"]:
                if last_error:
                    self.knowledge.record_fix(last_error)
                return {
                    "code": code, "passed": True,
                    "attempts": attempt, "error": None,
                    "used_toolbox": used_toolbox,
                }
            else:
                error_text = result.get("error", "unknown")
                self.knowledge.record_error(error_text, context=context[:200], code=code)
                failure_history.append(error_text)
                last_error = error_text

        return {
            "code": code, "passed": False,
            "attempts": max_attempts, "error": last_error,
            "used_toolbox": used_toolbox,
        }


# ═════════════════════════════════════════════════════════════════════════
#  Standalone test
# ═════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import asyncio

    async def test():
        p = Pipeline()
        await p.on_startup()

        # Test inlet with file attachment
        body = {
            "messages": [
                {"role": "system", "content": "You are a helper."},
                {"role": "user", "content": "fix this\n```python\ndef add(a,b):\n    return a+b\n```"}
            ]
        }
        result = await p.inlet(body, None)
        print("\n--- Inlet Result ---")
        print(result["messages"][-1]["content"][:500])

        # Test outlet with code response
        body2 = {
            "messages": result["messages"],
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Here is the fixed code:\n```python\ndef add(a, b):\n    return a + b\n```"
                }
            }]
        }
        result2 = await p.outlet(body2, None)
        print("\n--- Outlet Result ---")
        print(result2["choices"][0]["message"]["content"])

        await p.on_shutdown()

    asyncio.run(test())
