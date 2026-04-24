"""
Puzzle Logic AI — Prototype
============================

A minimal implementation of the Puzzle Logic Coding Agent.

Files:
- lmstudio_client.py    — Connects to LM Studio local API
- belief_graph.py       — Tracks code knowledge as a graph
- constraint_engine.py  — Validates code against empirical constraints
- puzzle_logic_agent.py — The main agent (Ω-gated decision loop)
- demo.py              — Runnable demonstration
- sample_project/      — A test Python project

Quick Start:
1. Install LM Studio and load a model
2. pip install requests pytest
3. python demo.py

Architecture:
- Synapse: Local LLM (DeepSeek/Qwen via LM Studio)
- OS: Belief Graph + Constraint Engine + Ω Controller
- Interface: Compiler + pytest (the empirical ground truth)
"""

__version__ = "0.1.0"
