"""
Prompt & Response Logger
========================

Logs every interaction with the LLM for debugging.
Each entry captures:
  - Problem ID and attempt number
  - The FULL prompt sent to the model
  - The RAW response from the model
  - The extracted code
  - The test result (pass/fail + error)

This is the definitive record of what the model actually saw and produced.
"""

import os
import time
from typing import Optional


class PromptLogger:
    """Logs every prompt/response interaction to a text file."""

    def __init__(self, path: str):
        self.path = path
        self._write_header()

    def _write_header(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("LLM INTERACTION LOG\n")
            f.write("=" * 80 + "\n")
            f.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("Format per entry:\n")
            f.write("  [PROBLEM] <id> | [ATTEMPT] <n> | [RESULT] PASS/FAIL\n")
            f.write("  --- PROMPT ---\n")
            f.write("  <full prompt text>\n")
            f.write("  --- RESPONSE ---\n")
            f.write("  <raw model output>\n")
            f.write("  --- EXTRACTED CODE ---\n")
            f.write("  <code after extraction>\n")
            f.write("  --- TEST RESULT ---\n")
            f.write("  <pass/fail + error>\n")
            f.write("=" * 80 + "\n\n")

    def log(self, *, task_id: str, attempt: int, result: str,
            prompt: str, raw_response: str, extracted_code: str,
            test_passed: bool, test_error: Optional[str] = None,
            toolbox_used: bool = False):
        """Log a complete interaction cycle."""
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("-" * 80 + "\n")
            f.write(f"[PROBLEM] {task_id}\n")
            f.write(f"[ATTEMPT] {attempt}\n")
            f.write(f"[RESULT]  {result}\n")
            if toolbox_used:
                f.write("[TOOLBOX] YES (error-pattern hints were presented)\n")
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
            f.write("\n\n")
