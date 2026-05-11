# 🧩 Puzzle Logic Agent v2.4

**Empirical constraint satisfaction for coding.**

The agent generates code, executes it, catches errors, queries a learned knowledge graph for fix patterns, retries with hints, and records validated solutions -- so it gets smarter over time.

---

## 🚀 Quick Start (Web UI -- Recommended)

The easiest way to use the agent is through the browser interface.

```bash
# 1. Install LM Studio (https://lmstudio.ai) and download Qwen2.5-Coder-3B-Instruct
#    OR install Ollama (https://ollama.com) and pull a model: ollama pull qwen2.5-coder:3b

# 2. Start your LLM backend
#    LM Studio: Load model, go to Developer tab, click "Start Server"
#    Ollama: Run `ollama serve` in a terminal

# 3. Install dependency
pip install requests

# 4. Start the web server
python puzzle_logic_server.py

# 5. Open your browser to http://localhost:8080
```

That's it! No more command-line flags or PowerShell confusion.

---

## 📎 File Management

The web UI supports loading and unloading multiple code files:

| Action | How |
|--------|-----|
| **Attach file(s)** | Click the paperclip icon or drag & drop files onto the chat input |
| **Remove one file** | Click the X on the file pill |
| **Remove all files** | Click "Clear all" in the file pills bar |
| **Preview contents** | Click the file icon in the toolbar to open the file preview panel |

### Supported File Formats

- **Python**: `.py`
- **JavaScript/TypeScript**: `.js`, `.ts`, `.jsx`, `.tsx`
- **C/C++**: `.c`, `.cpp`, `.h`, `.hpp`
- **Java**: `.java`
- **Go**: `.go`
- **Rust**: `.rs`
- **Swift/Kotlin**: `.swift`, `.kt`
- **Ruby/PHP**: `.rb`, `.php`
- **Web**: `.html`, `.htm`, `.css`, `.scss`, `.sass`, `.less`
- **Data/Config**: `.json`, `.xml`, `.yaml`, `.yml`, `.csv`
- **Other**: `.sql`, `.sh`, `.bat`, `.ps1`, `.md`, `.txt`

Files are automatically tagged with their language for syntax highlighting. When you send a message with attached files, the agent receives the full file contents in the prompt.

---

## ⚙️ How It Works (The Puzzle Logic Loop)

```
  GENERATE ----> EXECUTE ----> PASS? --YES--> LEARN (record fix)
                    |
                   NO
                    v
             CATCH ERROR
                    |
                    v
         QUERY KNOWLEDGE GRAPH
         "Seen this error before?"
                    |
                    v
          RETRIEVE FIX TOOLBOX
     (past patterns as options, not directives)
                    |
                    v
               RETRY + HINT
                    |
                    v
                 PASS? --YES--> LEARN
```

The key insight: **the compiler IS the constraint engine.** Its output tells us exactly what's wrong. We extract that error fingerprint, search our graph of validated fixes, present them as a *toolbox* (the model decides which pattern fits), and when it eventually passes, we record the validated fix pattern for next time.

---

## 🖥️ Web UI Features

- **Chat tab**: Type natural language requests, get streaming responses with markdown and syntax highlighting
- **Fix + Test tab**: Paste your code and optional tests, run the full Puzzle Logic loop
- **Knowledge tab**: Browse learned error-fix patterns with confidence bars
- **File attachments**: Drag & drop or click paperclip to attach multiple code files
- **File preview panel**: Inspect attached files before sending
- **Conversation history**: Chats saved locally in your browser
- **Live stats**: See how many patterns the agent has learned
- **Backend selector**: Switch between LM Studio and Ollama without restarting

---

## ⌨️ Commands

```bash
# Generate code from a natural language description
python puzzle_logic_agent.py --generate "Write a function to check if a number is prime"

# Fix a file with tests (generate -> execute -> catch errors -> learn)
python puzzle_logic_agent.py broken_script.py --test test_script.py --attempts 3

# See knowledge graph statistics
python puzzle_logic_agent.py --stats

# Log all LLM interactions for debugging
python puzzle_logic_agent.py my_script.py --test test_my_script.py --log agent.log

# Start web UI with Ollama backend
python puzzle_logic_server.py --backend ollama --port 8080
```

---

## 💾 Knowledge Persistence

Your learned patterns are stored in `puzzle_logic_knowledge.json`. This file grows as you use the agent:

| Session | Typical Patterns | Behavior |
|---------|-----------------|----------|
| 1 | 0 | Clean attempts, learns from first errors |
| 3 | 5-10 | Common fixes applied automatically (NameError, TypeError) |
| 5 | 15-25 | Domain expertise emerges in your specific codebase |
| 10 | 30+ | Most recurring errors fixed on first retry |

The knowledge graph stores *structural* fix patterns, not full code:

```json
{
  "patterns": [
    {
      "error_type": "TypeError",
      "error_signature": "takes 2 positional arguments but 3 were given",
      "fix_strategy": "FUNCTION SIGNATURE MISMATCH: check assert and update def line",
      "confidence": 1.0,
      "times_seen": 3,
      "times_fixed": 2
    }
  ]
}
```

---

## 🏗️ Architecture

- **Synapse** (`LMStudioClient` / `OllamaBackend`): The LLM that generates code
- **OS** (`ErrorPatternGraph`): The constraint engine that validates and maintains belief state
- **Sandbox** (`execute_code`): Subprocess-based Python execution with timeout
- **Toolbox** (`get_fix_toolbox`): Retrieved patterns presented as options, not directives

This is the **Synapse x OS** architecture: the LLM generates candidates, the OS validates them against hard constraints (compiler output), and the Omega parameter is implicitly controlled by how aggressively we trust learned patterns.

---

## 🔌 Backend Options

### LM Studio (Default)
- Download: https://lmstudio.ai
- Best for: GUI users, easy model management, GPU acceleration
- Server port: 1234
- Start: Load model -> Developer tab -> Start Server

### Ollama
- Download: https://ollama.com
- Best for: Terminal users, lightweight, scripted workflows
- Server port: 11434
- Start: `ollama serve` (or run as system service)
- Pull model: `ollama pull qwen2.5-coder:3b`

Switch backends in the web UI sidebar, or use `--backend ollama` on the command line.

---

## ⚠️ Limitations

- Requires LM Studio or Ollama running locally
- Error patterns are classified by error type + signature -- not by deep causal program analysis
- Best for Python coding tasks (other languages supported for generation, tests run as Python)
- Single parameter (confidence threshold) controls pattern matching sensitivity

---

## 🗺️ Roadmap

- VS Code extension
- Support for pytest/unittest test discovery
- Causal error analysis (delta between failing and passing code)
- Multi-language test execution (not just Python sandbox)
- Team knowledge sharing (shared pattern databases)
- Contract Graph: learn function pre/postconditions from validated solutions

---

## 📁 Files

| File | Description |
|------|-------------|
| `puzzle_logic_agent.py` | CLI tool + core engine (required by server) |
| `puzzle_logic_server.py` | Web server (run this for the UI) |
| `templates/index.html` | Browser UI (must be in `templates/` folder) |
| `puzzle_logic_knowledge.json` | Your learned patterns (auto-created) |
| `requirements.txt` | Just `requests` |

---

## 📜 License

MIT
