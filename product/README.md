# Puzzle Logic Agent v1.0

Download and use immediately. No benchmark code, no research overhead.

## Quick Start

```bash
# 1. Install LM Studio (https://lmstudio.ai) and download Qwen2.5-Coder-3B-Instruct
# 2. Start the server (Developer tab -> Start Server on port 1234)

# 3. Install this tool
pip install requests

# 4. Use it
python puzzle_logic_agent.py --chat "Write a function to check if a number is prime" --model qwen2.5-coder-3b-instruct

# Or fix an existing file
python puzzle_logic_agent.py my_script.py --model qwen2.5-coder-3b-instruct
```

## How It Works

1. You write a prompt or load a Python file
2. The agent sends it to your local LLM
3. If the code fails, it searches your personal error history for similar past errors
4. It presents fix suggestions learned from previous successful corrections
5. Knowledge accumulates in `puzzle_logic_knowledge.json` — it gets smarter over time

## Features

- **Model-agnostic**: Works with any LLM in LM Studio (Qwen, DeepSeek, Llama, Mistral)
- **Privacy-first**: Everything runs locally — no cloud API keys
- **Self-improving**: Error patterns accumulate across sessions
- **Simple**: Single Python file, no complex setup

## Knowledge Persistence

Your learned patterns are stored in `puzzle_logic_knowledge.json`. This file grows as you use the agent:

- First session: empty, learns from your errors
- Fifth session: 20+ patterns, fixes common issues instantly
- Tenth session: domain expertise in your specific codebase

## Commands

```bash
# Generate code from description
python puzzle_logic_agent.py --chat "Write a function to sort a list of tuples by the second element"

# Fix an existing file
python puzzle_logic_agent.py broken_script.py

# See what the agent has learned
python puzzle_logic_agent.py --stats
```

## Limitations (v1.0)

- Requires LM Studio running locally
- Error patterns are classified by type (NameError, TypeError, etc.) — not by deep causal analysis
- Best for Python coding tasks
- No integration with external test frameworks yet

## Roadmap

- VS Code extension
- Support for pytest/unittest integration
- Causal error analysis (compare failing vs. passing code)
- Multi-language support (JavaScript, Rust)
- Team knowledge sharing (shared pattern databases)

## License

MIT
