"""
Debug HumanEval test construction for Problem 0.
Shows exactly what test program gets executed and why it fails.
"""
import json
import tempfile
import subprocess
import sys
import os

with open("HumanEval.jsonl") as f:
    p0 = json.loads(f.readline())

# Construct test program exactly as the runner does
prompt = p0["prompt"]

# Simulate a correct completion
completion = """from typing import List

def has_close_elements(numbers: List[float], threshold: float) -> bool:
    for i in range(len(numbers)):
        for j in range(i + 1, len(numbers)):
            if abs(numbers[i] - numbers[j]) < threshold:
                return True
    return False
"""

test = p0["test"]

# Method 1: prompt + completion + test (our current approach)
prog1 = prompt + "\n" + completion + "\n" + test + "\n"

# Method 2: just completion + test (original approach)
prog2 = completion + "\n" + test + "\n"

# Method 3: prompt + body-only + test (canonical approach)
prog3 = prompt + "\n    for i in range(len(numbers)):\n        for j in range(i + 1, len(numbers)):\n            if abs(numbers[i] - numbers[j]) < threshold:\n                return True\n    return False\n\n" + test + "\n"

for name, prog in [("Method 1: prompt+completion+test", prog1),
                   ("Method 2: completion+test", prog2),
                   ("Method 3: prompt+body+test", prog3)]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(prog)
        tp = f.name
    
    try:
        result = subprocess.run([sys.executable, tp], capture_output=True, text=True, timeout=5)
        print(f"\n{'='*60}")
        print(f"{name}")
        print(f"Return code: {result.returncode}")
        if result.returncode != 0:
            print(f"STDERR:\n{result.stderr[:300]}")
        else:
            print("PASS!")
    except Exception as e:
        print(f"CRASH: {e}")
    finally:
        os.unlink(tp)
