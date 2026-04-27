"""
Puzzle Logic Agent -- Web Server v2
====================================

A KIMI-inspired web UI for the Puzzle Logic Agent.

Usage:
    python puzzle_logic_server.py

Then open your browser to: http://localhost:8080

Features:
  - Chat interface with markdown rendering and code highlighting
  - Streaming text responses
  - Fix + Test panel with the full Puzzle Logic loop
  - Knowledge graph visualization
  - Conversation history (saved locally in browser)
  - Works with LM Studio or Ollama

No extra dependencies beyond `requests`.
"""

import argparse
import http.server
import json
import os
import socketserver
import sys
import urllib.parse
from typing import Optional, Dict

# Import the agent
from puzzle_logic_agent import (
    PuzzleLogicAgent, ErrorPatternGraph, execute_code,
    extract_code, LMStudioClient
)


# ═════════════════════════════════════════════════════════════════════════
#  Backend Abstraction (LM Studio or Ollama)
# ═════════════════════════════════════════════════════════════════════════

class LMStudioBackend:
    """OpenAI-compatible API (LM Studio)."""
    def __init__(self, model: str, base_url="http://localhost:1234/v1", timeout=300):
        self.client = LMStudioClient(base_url=base_url, model=model, timeout=timeout)
    
    def generate(self, prompt: str, system_message: str = None, temperature=0.0, max_tokens=1024) -> str:
        raw_list = self.client.generate(prompt=prompt, system_message=system_message, temperature=temperature, max_tokens=max_tokens, n=1)
        return raw_list[0] if raw_list else ""
    
    def check_health(self) -> bool:
        return self.client.check_health()
    
    def list_models(self):
        import requests
        try:
            r = requests.get(f"{self.client.base_url}/models", timeout=5)
            data = r.json()
            return [m.get("id", "unknown") for m in data.get("data", [])]
        except:
            return []


class OllamaBackend:
    """Ollama native API."""
    def __init__(self, model: str, base_url="http://localhost:11434", timeout=300):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
    
    def generate(self, prompt: str, system_message: str = None, temperature=0.0, max_tokens=1024) -> str:
        import requests
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_message or "You are a helpful coding assistant.",
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            "stream": False,
        }
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except Exception as e:
            print(f"[Ollama Error] {e}")
            return ""
    
    def check_health(self) -> bool:
        import requests
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def list_models(self):
        import requests
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            data = response.json()
            return [m.get("name", "unknown") for m in data.get("models", [])]
        except:
            return []


class AgentAPI:
    """Wraps the PuzzleLogicAgent for web API use."""
    
    def __init__(self, backend_type="lmstudio", model: str = None, 
                 knowledge_path="puzzle_logic_knowledge.json"):
        self.backend_type = backend_type
        self.model = model
        self.knowledge_path = knowledge_path
        self.backend = None
        self.knowledge = None
        self._init_backend()
    
    def _init_backend(self):
        if self.backend_type == "ollama":
            self.backend = OllamaBackend(model=self.model or "qwen2.5-coder:3b")
        else:
            self.backend = LMStudioBackend(model=self.model)
        self.knowledge = ErrorPatternGraph(storage_path=self.knowledge_path)
    
    def generate(self, prompt: str, max_tokens=1024) -> Dict:
        """Generate code from a prompt (no test execution)."""
        # Detect if prompt contains attached files and adjust system message
        has_files = "=== ATTACHED FILES ===" in prompt or "[File:" in prompt or "[Attached file:" in prompt
        
        if has_files:
            # Use a more instructive system prompt for file analysis
            system_msg = (
                "You are a senior software engineer. The user has attached code files. "
                "Your task is to carefully read and analyze the attached code, then respond "
                "precisely to the user's request. Reference specific functions, variables, and "
                "lines from the code when giving advice. If asked to improve code, provide the "
                "complete improved version in a code block. Be thorough and specific."
            )
        else:
            system_msg = "You are a helpful coding assistant. Write clean, correct Python code."
        
        raw = self.backend.generate(prompt=prompt, system_message=system_msg, temperature=0.0, max_tokens=max_tokens)
        code = extract_code(raw)
        return {"raw": raw, "code": code, "success": bool(code)}
    
    def fix(self, prompt: str, test_code: str = None, 
            n_attempts: int = 3, max_tokens: int = 1024) -> Dict:
        failure_history = []
        last_error = ""
        used_toolbox = False
        
        # Detect if prompt contains attached files
        has_files = "=== ATTACHED FILES ===" in prompt or "[File:" in prompt
        system_msg = None
        if has_files:
            system_msg = (
                "You are a senior software engineer. The user has attached code files. "
                "Your task is to carefully read and analyze the attached code, then respond "
                "precisely to the user's request. Reference specific functions, variables, and "
                "lines from the code when giving advice. If asked to improve code, provide the "
                "complete improved version in a code block. Be thorough and specific."
            )
        
        for attempt in range(1, n_attempts + 1):
            error_toolbox = ""
            if failure_history and last_error:
                error_toolbox = self.knowledge.get_fix_toolbox(last_error, top_k=3)
            
            full_prompt = prompt
            if error_toolbox:
                full_prompt = prompt + "\n\n" + error_toolbox + "\n"
                used_toolbox = True
            
            raw = self.backend.generate(prompt=full_prompt, system_message=system_msg, temperature=0.0, max_tokens=max_tokens)
            code = extract_code(raw)
            
            if not code:
                last_error = "extraction failed"
                self.knowledge.record_error("extraction failed")
                failure_history.append(last_error)
                continue
            
            if test_code is None or not test_code.strip():
                return {"code": code, "passed": True, "attempts": attempt,
                        "error": None, "used_toolbox": used_toolbox,
                        "patterns": len(self.knowledge.patterns)}
            
            test_program = prompt + "\n" + code + "\n" + test_code + "\n"
            result = execute_code(test_program)
            
            if result["passed"]:
                if last_error:
                    self.knowledge.record_fix(last_error)
                return {"code": code, "passed": True, "attempts": attempt,
                        "error": None, "stdout": result.get("stdout", ""),
                        "used_toolbox": used_toolbox,
                        "patterns": len(self.knowledge.patterns)}
            else:
                error_text = result.get("error", "unknown")
                self.knowledge.record_error(error_text, context=prompt[:200], code=code)
                failure_history.append(error_text)
                last_error = error_text
        
        return {"code": code if 'code' in dir() else "", "passed": False,
                "attempts": n_attempts, "error": last_error,
                "used_toolbox": used_toolbox,
                "patterns": len(self.knowledge.patterns)}
    
    def get_stats(self) -> Dict:
        return self.knowledge.stats()
    
    def health(self) -> Dict:
        return {"backend": self.backend_type,
                "connected": self.backend.check_health(),
                "model": self.model,
                "models_available": self.backend.list_models()}


# ═════════════════════════════════════════════════════════════════════════
#  HTTP Server
# ═════════════════════════════════════════════════════════════════════════

class AgentHandler(http.server.BaseHTTPRequestHandler):
    api: AgentAPI = None
    html_path: str = ""  # Path to the HTML template
    
    def log_message(self, format, *args):
        pass  # Suppress default logging
    
    def _send_json(self, data: Dict, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))
    
    def _send_html(self, html: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))
    
    def _read_json(self) -> Dict:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        try:
            return json.loads(body)
        except:
            return {}
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        if path == "/" or path == "/index.html":
            try:
                with open(self.html_path, "r", encoding="utf-8") as f:
                    self._send_html(f.read())
            except Exception as e:
                self._send_html(f"<h1>Error</h1><p>Could not load UI: {e}</p>", 500)
        
        elif path == "/api/stats":
            self._send_json(self.api.get_stats())
        
        elif path == "/api/health":
            self._send_json(self.api.health())
        
        else:
            self._send_json({"error": "Not found"}, 404)
    
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        data = self._read_json()
        
        if path == "/api/generate":
            prompt = data.get("prompt", "")
            max_tokens = data.get("max_tokens", 1024)
            result = self.api.generate(prompt, max_tokens=max_tokens)
            self._send_json(result)
        
        elif path == "/api/fix":
            prompt = data.get("prompt", "")
            test_code = data.get("test", None)
            n_attempts = data.get("n_attempts", 3)
            max_tokens = data.get("max_tokens", 1024)
            result = self.api.fix(prompt, test_code=test_code,
                                 n_attempts=n_attempts, max_tokens=max_tokens)
            self._send_json(result)
        
        else:
            self._send_json({"error": "Not found"}, 404)


def run_server(port=8080, backend="lmstudio", model=None, 
               knowledge_path="puzzle_logic_knowledge.json"):
    # Find the HTML template
    script_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(script_dir, "templates", "index.html")
    
    if not os.path.exists(html_path):
        print(f"[Error] UI template not found at: {html_path}")
        print(f"        Make sure the 'templates/' folder is next to this script.")
        sys.exit(1)
    
    AgentHandler.api = AgentAPI(backend_type=backend, model=model, knowledge_path=knowledge_path)
    AgentHandler.html_path = html_path
    
    with socketserver.TCPServer(("", port), AgentHandler) as httpd:
        print(f"\n  {'='*50}")
        print(f"   Puzzle Logic Agent Web Server v2")
        print(f"  {'='*50}")
        print(f"   Backend: {backend}")
        print(f"   URL: http://localhost:{port}")
        print(f"   Templates: {html_path}")
        print(f"   Press Ctrl+C to stop\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Server stopped.")


def main():
    parser = argparse.ArgumentParser(description="Puzzle Logic Agent Web Server v2")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--backend", type=str, default="lmstudio", choices=["lmstudio", "ollama"])
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--knowledge", type=str, default="puzzle_logic_knowledge.json")
    args = parser.parse_args()
    
    run_server(port=args.port, backend=args.backend, model=args.model,
               knowledge_path=args.knowledge)


if __name__ == "__main__":
    main()
