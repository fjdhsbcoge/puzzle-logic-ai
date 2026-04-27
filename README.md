# Puzzle Logic Agent v2.0

**Empirical constraint satisfaction for coding.**

The agent generates code, executes it, catches errors, queries a learned knowledge graph for fix patterns, retries with hints, and records validated solutions — so it gets smarter over time.

---

## Recommended: Open WebUI + Puzzle Logic Pipeline

The best experience is using **Open WebUI** (a free, open-source chat interface) with our **Puzzle Logic Pipeline** plugin. This gives you:

- **Conversation memory** (remembers context across messages)
- **Drag & drop file upload** (multiple files, any code format)
- **Beautiful dark UI** with markdown, code highlighting, streaming
- **Auto-execution**: code runs in sandbox, errors caught, knowledge graph consulted
- **Works with LM Studio or Ollama** (any OpenAI-compatible backend)

### Quick Start

```bash
# 1. Install Open WebUI (requires Python 3.11+)
pip install open-webui

# 2. Start your LLM backend FIRST
#    LM Studio: Load model, Developer tab -> Start Server (port 1234)
#    Ollama: ollama serve (port 11434)

# 3. Start Open WebUI
open-webui serve

# 4. Open browser to http://localhost:8080
#    - Sign in (create any account, it's local-only)
#    - Go to Settings -> Admin Panel -> Settings -> Connections
#    - Add OpenAI API connection: http://localhost:1234/v1 (for LM Studio)
#    - Or: http://localhost:11434/v1 (for Ollama)

# 5. Copy the Pipeline file to Open WebUI's pipelines folder
mkdir -p ~/.config/open-webui/pipelines
cp pipeline/puzzle_logic_pipeline.py ~/.config/open-webui/pipelines/
cp product/puzzle_logic_agent.py ~/.config/open-webui/pipelines/

# 6. In Open WebUI chat, select "Puzzle Logic" from the model dropdown
#    Drag a .py file into the chat, type "fix this", send
```

---

## Alternative: Standalone Web UI

If you prefer not to install Open WebUI, use our built-in web server.
Conversation memory is limited (saves to browser localStorage only).

```bash
python product/puzzle_logic_server.py
# Open browser to http://localhost:8080
```

---

## Alternative: Command Line

```bash
# Generate code
python product/puzzle_logic_agent.py --generate "Write a function..."

# Fix a file with tests
python product/puzzle_logic_agent.py broken.py --test test_broken.py --attempts 3

# See knowledge graph stats
python product/puzzle_logic_agent.py --stats
```

---

## How It Works

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

---

## File Management

All interfaces support loading and unloading code files:

| Action | How |
|--------|-----|
| Attach file(s) | Drag & drop, or click paperclip |
| Remove one file | Click the X on the file pill |
| Remove all files | Click "Clear all" |
| Preview contents | Open file preview panel |

### Supported Formats

Python, JavaScript, TypeScript, C, C++, Java, Go, Rust, Swift, Kotlin, Ruby, PHP, HTML, CSS, JSON, YAML, SQL, Shell, Markdown, Text, CSV

---

## Architecture

- **Synapse** (LLM): LM Studio or Ollama — generates code
- **OS** (`ErrorPatternGraph`): Validates against compiler output
- **Sandbox** (`execute_code`): Subprocess execution with timeout
- **Toolbox** (`get_fix_toolbox`): Patterns as options, not directives
- **Pipeline** (Open WebUI): Intercepts requests, runs loop, formats results

---

## License

MIT
