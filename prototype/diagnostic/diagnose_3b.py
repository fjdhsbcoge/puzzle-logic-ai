"""
Diagnostic: What does the 3B Coder actually output on MBPP problems?
Tests 3 problems with full raw response visibility.
"""
import requests
import json
import sys

MODEL = "qwen2.5-coder-3b-instruct"
URL = "http://localhost:1234/v1/chat/completions"

def test_problem(problem_idx):
    from datasets import load_dataset
    ds = load_dataset("mbpp", split="train")
    p = ds[problem_idx]
    
    print(f"\n{'='*60}")
    print(f"PROBLEM {problem_idx}: {p['text'][:80]}...")
    print(f"TESTS: {p['test_list']}")
    print(f"{'='*60}")
    
    prompt = (
        p["text"] + "\n\n"
        "Write a Python function to solve this. "
        "Output the complete function inside a markdown code block."
    )
    
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful coding assistant. Write clean, correct Python code."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 1024,
        "stream": False
    }
    
    import time
    start = time.time()
    r = requests.post(URL, json=payload, timeout=120)
    elapsed = time.time() - start
    
    data = r.json()
    content = data["choices"][0]["message"].get("content", "")
    finish = data["choices"][0].get("finish_reason", "?")
    tokens = data.get("usage", {}).get("completion_tokens", 0)
    
    print(f"Time: {elapsed:.1f}s | Tokens: {tokens} | Finish: {finish}")
    print(f"Response length: {len(content)} chars")
    print(f"\n--- RAW RESPONSE ---")
    print(content)
    print(f"--- END RESPONSE ---")
    
    # Try code extraction
    import re
    match = re.search(r"```(?:python)?\n(.*?)```", content, re.DOTALL)
    if match:
        code = match.group(1).strip()
        print(f"\n--- EXTRACTED CODE ---")
        print(code[:300])
        print(f"--- (truncated) ---")
        
        # Test it
        test_prog = code + "\n\n" + "\n".join(p["test_list"]) + "\n"
        import tempfile, subprocess, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(test_prog)
            tp = f.name
        try:
            result = subprocess.run([sys.executable, tp], capture_output=True, text=True, timeout=5)
            passed = result.returncode == 0
            print(f"\nTEST RESULT: {'PASS' if passed else 'FAIL'}")
            if not passed:
                print(f"ERROR: {result.stderr[:200]}")
        except Exception as e:
            print(f"TEST CRASH: {e}")
        finally:
            os.unlink(tp)
    else:
        print("\nNO CODE BLOCK FOUND!")
        # Show if def is present
        if "def " in content:
            print("But 'def ' was found in raw text — extraction regex failed")


# Test 3 different problems
test_problem(0)
test_problem(1)
test_problem(10)
