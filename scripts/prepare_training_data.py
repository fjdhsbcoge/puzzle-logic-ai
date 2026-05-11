"""
Prepare Training Data from Puzzle Logic Knowledge Graph
=========================================================

Converts verified patterns from the knowledge graph into ShareGPT/ChatML
format for LoRA fine-tuning. Each pattern becomes one training example:

  User: original prompt + error message
  Assistant: verified fix code

Usage:
    python prepare_training_data.py --kg puzzle_logic_knowledge.json --output training_data.jsonl
    python prepare_training_data.py --log puzzle_logic_log.json --output training_data.jsonl
"""

import argparse
import json
import os
from typing import List, Dict


def pattern_to_example(pattern: Dict) -> Dict:
    """Convert a single knowledge graph pattern to a training example."""
    
    err_type = pattern.get('error_type', 'Error')
    err_sig = pattern.get('error_signature', '')
    failing_line = pattern.get('failing_line', '')
    fix_strategy = pattern.get('fix_strategy', '')
    context = pattern.get('context', '')
    confidence = pattern.get('confidence', 0.5)
    times_fixed = pattern.get('times_fixed', 0)
    
    # Build user prompt: problem context + error feedback
    user_parts = [
        "Write a Python function to solve the following problem.",
        "",
    ]
    
    if context:
        user_parts.append(f"Previous attempt context: {context}")
        user_parts.append("")
    
    if failing_line:
        user_parts.append(f"The code failed at: {failing_line}")
    
    user_parts.append(f"Error: [{err_type}] {err_sig}")
    user_parts.append("")
    user_parts.append("Fix the code based on this error. Output only the corrected function.")
    
    user_content = "\n".join(user_parts)
    
    # Extract the actual code fix from fix_strategy
    assistant_content = extract_code_from_fix(fix_strategy)
    
    return {
        "messages": [
            {"role": "system", "content": "You are a helpful coding assistant. Write clean, correct Python code."},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content}
        ],
        "metadata": {
            "confidence": confidence,
            "times_fixed": times_fixed,
            "error_type": err_type,
        }
    }


def extract_code_from_fix(fix_strategy: str) -> str:
    """Extract code from a fix strategy string."""
    if not fix_strategy:
        return "# No fix available"
    
    # If fix contains actual code (starts with def, import, return, etc.)
    lines = fix_strategy.split('\n')
    code_lines = []
    in_code = False
    
    for line in lines:
        stripped = line.strip()
        # Check for code-like content
        if stripped.startswith(('def ', 'return ', 'import ', 'for ', 'if ', 'while ', 'class ')):
            in_code = True
            code_lines.append(line)
        elif in_code and (stripped.startswith(('    ', '\t')) or stripped == ''):
            code_lines.append(line)
        elif 'def ' in stripped and '->' in stripped:
            # Extract the signature change
            code_lines.append(f"# {fix_strategy}")
            in_code = True
    
    if code_lines:
        return '\n'.join(code_lines)
    
    # Fallback: return the strategy as a comment + placeholder
    return f"# Fix strategy: {fix_strategy}\n# (Implement based on the error description)"


def log_to_examples(log_data: Dict) -> List[Dict]:
    """Convert full log data (with prompt_log) to training examples.
    Only include sessions that eventually passed."""
    
    examples = []
    
    for result in log_data.get('advanced_results', []):
        if not result.get('passed') or 'prompt_log' not in result:
            continue
        
        prompt_log = result['prompt_log']
        if len(prompt_log) < 2:
            continue  # Need at least 2 attempts to show revision
        
        # Find the last failed attempt and the successful one
        failed_attempts = [pl for pl in prompt_log[:-1] if not pl.get('passed', False)]
        success_attempt = prompt_log[-1]
        
        if not failed_attempts:
            continue
        
        # Use the last failed attempt's prompt + error
        last_fail = failed_attempts[-1]
        
        # Build training example
        user_content = last_fail['prompt']
        assistant_content = success_attempt.get('response_code', success_attempt.get('response_raw', ''))
        
        if not assistant_content:
            continue
        
        examples.append({
            "messages": [
                {"role": "system", "content": "You are a helpful coding assistant. Write clean, correct Python code."},
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": assistant_content}
            ]
        })
    
    return examples


def kg_to_examples(kg_data: Dict) -> List[Dict]:
    """Convert knowledge graph patterns to training examples."""
    
    examples = []
    
    for pattern in kg_data.get('patterns', []):
        if pattern.get('times_fixed', 0) == 0:
            continue  # Only verified patterns
        
        example = pattern_to_example(pattern)
        examples.append(example)
    
    return examples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kg", type=str, help="Knowledge graph JSON file")
    parser.add_argument("--log", type=str, help="Log JSON file (with prompt_log)")
    parser.add_argument("--output", type=str, default="training_data.jsonl")
    parser.add_argument("--min-confidence", type=float, default=0.0)
    parser.add_argument("--min-fixes", type=int, default=1)
    args = parser.parse_args()
    
    examples = []
    
    # From knowledge graph
    if args.kg and os.path.exists(args.kg):
        print(f"Loading knowledge graph: {args.kg}")
        with open(args.kg, 'r') as f:
            kg = json.load(f)
        kg_examples = kg_to_examples(kg)
        print(f"  {len(kg_examples)} examples from knowledge graph")
        examples.extend(kg_examples)
    
    # From log
    if args.log and os.path.exists(args.log):
        print(f"Loading log: {args.log}")
        with open(args.log, 'r') as f:
            log = json.load(f)
        log_examples = log_to_examples(log)
        print(f"  {len(log_examples)} examples from log (passed after retry)")
        examples.extend(log_examples)
    
    # Filter
    if args.min_confidence > 0:
        before = len(examples)
        examples = [e for e in examples 
                   if e.get('metadata', {}).get('confidence', 1.0) >= args.min_confidence]
        print(f"  Filtered by confidence >= {args.min_confidence}: {before} -> {len(examples)}")
    
    # Write
    print(f"\nWriting {len(examples)} examples to {args.output}")
    with open(args.output, 'w') as f:
        for ex in examples:
            f.write(json.dumps(ex) + '\n')
    
    # Stats
    print(f"\nTraining data summary:")
    print(f"  Total examples: {len(examples)}")
    
    # Show sample
    if examples:
        print(f"\nSample example:")
        sample = examples[0]
        for msg in sample['messages']:
            print(f"  [{msg['role']}] {msg['content'][:100]}...")


if __name__ == "__main__":
    main()
