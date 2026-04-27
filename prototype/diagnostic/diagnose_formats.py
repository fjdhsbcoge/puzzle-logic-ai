import requests
import json

MODEL = "deepseek-ai_-_deepseek-coder-6.7b-instruct"
URL = "http://localhost:1234/v1/chat/completions"

def try_format(name, messages, temp=0.3, max_tokens=512):
    print(f"\n{'='*60}")
    print(f"FORMAT: {name}")
    print(f"{'='*60}")
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temp,
        "max_tokens": max_tokens,
        "stream": False
    }
    try:
        r = requests.post(URL, json=payload, timeout=60)
        data = r.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content", "")
        finish = data["choices"][0].get("finish_reason", "?")
        usage = data.get("usage", {})
        
        print(f"  finish_reason: {finish}")
        print(f"  completion_tokens: {usage.get('completion_tokens', '?')}")
        print(f"  content length: {len(content)} chars")
        
        # Show first/last non-empty part
        stripped = content.strip()
        if stripped:
            preview = stripped[:200].replace('\n', '\\n')
            print(f"  preview: {preview}")
            if "def " in content or "```" in content:
                print("  STATUS: CONTAINS CODE")
            else:
                print("  STATUS: no code detected")
        else:
            print("  STATUS: EMPTY or only whitespace")
    except Exception as e:
        print(f"  ERROR: {e}")

# Test 1: Current format (system + user)
try_format("system+user (current)", [
    {"role": "system", "content": "You are a helpful coding assistant. Write clean, correct Python code. Output only the code inside a markdown code block. Do not include explanations outside the code block."},
    {"role": "user", "content": "Write a function add(a, b) that returns the sum."}
])

# Test 2: No system message
try_format("user-only, no system", [
    {"role": "user", "content": "Write a Python function add(a, b) that returns the sum. Output only the function code inside a markdown code block."}
])

# Test 3: Different wording — more direct
try_format("direct instruction", [
    {"role": "user", "content": "```python\ndef add(a, b):\n    # your code here\n```\n\nComplete the function above."}
])

# Test 4: No code block request — just ask for code
try_format("plain code request", [
    {"role": "user", "content": "Write the Python function:\n\ndef add(a, b):\n    return a + b\n\nNow write a function multiply(a, b) that returns the product. Output the complete function."}
])

# Test 5: Using assistant role prefix
try_format("assistant prefix", [
    {"role": "user", "content": "Write a Python function add(a, b) that returns the sum."},
    {"role": "assistant", "content": "```python\ndef add(a, b):\n    "}
], max_tokens=256)

# Test 6: Try R1-distilled model instead
print(f"\n{'='*60}")
print("SWITCHING MODEL to deepseek-r1-distill-qwen-7b")
print(f"{'='*60}")
MODEL = "deepseek-r1-distill-qwen-7b"
try_format("r1-7b system+user", [
    {"role": "system", "content": "You are a helpful coding assistant. Write clean, correct Python code. Output only the code inside a markdown code block."},
    {"role": "user", "content": "Write a function add(a, b) that returns the sum."}
])

print("\n" + "="*60)
print("SUMMARY: Which format produced actual code?")
print("="*60)
