"""
LM Studio Client
Connects to the local LM Studio OpenAI-compatible API.
Handles DeepSeek R1 reasoning traces and code extraction.
"""

import requests
import re


class LMStudioClient:
    def __init__(self, base_url="http://localhost:1234/v1", model=None, timeout=120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.chat_endpoint = f"{self.base_url}/chat/completions"
    
    def generate(self, prompt, temperature=0.7, max_tokens=2048, n=1):
        """
        Generate candidate code completions from the local model.
        Returns a list of candidate strings.
        """
        messages = [
            {"role": "system", "content": "You are a helpful coding assistant. Write clean, correct Python code. Output only the code inside a markdown code block. Do not include explanations outside the code block."},
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
            
            try:
                response = requests.post(
                    self.chat_endpoint,
                    json=payload,
                    timeout=self.timeout
                )
                response.raise_for_status()
                data = response.json()
                
                msg = data["choices"][0]["message"]
                
                # DeepSeek R1 models may put reasoning in a separate field.
                # Try content first, then reasoning_content, then reasoning.
                content = msg.get("content", "")
                if not content.strip() and "reasoning_content" in msg:
                    content = msg["reasoning_content"]
                if not content.strip() and "reasoning" in msg:
                    content = msg["reasoning"]
                
                # Some models wrap reasoning in <think>...</think> tags.
                # Remove those to get the actual answer.
                content = self._strip_think_tags(content)
                
                candidates.append(content)
            except Exception as e:
                print(f"[LM Studio Error] {e}")
                candidates.append("")
        
        return candidates
    
    def _strip_think_tags(self, text):
        """Remove <think>...</think> reasoning blocks from DeepSeek R1."""
        if not text:
            return ""
        # Remove <think>...</think> content
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        # Also handle variations
        text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)
        return text.strip()
    
    def check_health(self):
        """Check if LM Studio server is running."""
        try:
            response = requests.get(f"{self.base_url}/models", timeout=5)
            return response.status_code == 200
        except:
            return False
