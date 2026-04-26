"""
LM Studio Client
Connects to the local LM Studio OpenAI-compatible API.
Handles DeepSeek R1 reasoning traces and code extraction.
"""

import requests
import re
import time


class LMStudioClient:
    def __init__(self, base_url="http://localhost:1234/v1", model=None, timeout=300):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.chat_endpoint = f"{self.base_url}/chat/completions"
    
    def generate(self, prompt, temperature=0.7, max_tokens=1024, n=1):
        """
        Generate candidate code completions from the local model.
        Returns a list of candidate strings.
        """
        messages = [
            {"role": "system", "content": "You are a code generator. Output ONLY a markdown code block containing the Python function. Do NOT explain. Do NOT show reasoning. Do NOT think step by step. No preamble, no commentary, no analysis. Just the code inside triple backticks."},
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
            
            # Retry with exponential backoff on timeout
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
                    print(f"[LM Studio Warning] Timeout (attempt {attempt+1}/3). Retrying...")
                    time.sleep(2 ** attempt)
                    if attempt == 2:
                        print("[LM Studio Error] All retries exhausted. Returning empty.")
                        candidates.append("")
                        break
                except Exception as e:
                    print(f"[LM Studio Error] {e}")
                    candidates.append("")
                    break
            else:
                # Only reached if all retries timed out
                if data is None:
                    candidates.append("")
                    continue
            
            if data is None:
                continue
                
            msg = data["choices"][0]["message"]
            
            # DeepSeek R1 models may put reasoning in a separate field.
            # Try content first, then reasoning_content, then reasoning.
            content = msg.get("content", "")
            if not content.strip() and "reasoning_content" in msg:
                content = msg["reasoning_content"]
            if not content.strip() and "reasoning" in msg:
                content = msg["reasoning"]
            
            # Some models wrap reasoning in <thinking>...</thinking> tags.
            # Remove those to get the actual answer.
            content = self._strip_think_tags(content)
            
            # Warn if model returns only whitespace (broken/corrupted model)
            stripped = content.strip()
            if not stripped or all(c in '\n\r\t ()' for c in stripped):
                finish_reason = data["choices"][0].get("finish_reason", "?")
                print(f"[LM Studio Warning] Model '{self.model or 'default'}' returned only whitespace/garbage (finish_reason={finish_reason}). The model may be corrupted or misconfigured in LM Studio.")
            
            candidates.append(content)
        
        return candidates
    
    def _strip_think_tags(self, text):
        """Remove <thinking>...</thinking> reasoning blocks from DeepSeek R1."""
        if not text:
            return ""
        # Remove <thinking>...</thinking> content
        text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)
        # Also handle variations
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        return text.strip()
    
    def check_health(self):
        """Check if LM Studio server is running."""
        try:
            response = requests.get(f"{self.base_url}/models", timeout=5)
            return response.status_code == 200
        except:
            return False
