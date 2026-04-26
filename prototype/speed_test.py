"""
Quick GPU speed test for LM Studio.
Measures prompt processing and token generation speed.
"""
import requests
import time
import json

URL = "http://localhost:1234/v1/chat/completions"
MODEL = "deepseek-r1-distill-qwen-7b"

payload = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": "You are a code generator. Output ONLY a markdown code block containing the Python function. No explanations."},
        {"role": "user", "content": "Write a function factorial(n) that returns n! using recursion."}
    ],
    "temperature": 0.3,
    "max_tokens": 512,
    "stream": False
}

print("Speed Test: Sending prompt to LM Studio...")
print(f"Model: {MODEL}")
print(f"max_tokens: {payload['max_tokens']}")
print()

start = time.time()
r = requests.post(URL, json=payload, timeout=300)
elapsed = time.time() - start

data = r.json()
usage = data.get("usage", {})
completion_tokens = usage.get("completion_tokens", 0)
total_tokens = usage.get("total_tokens", 0)
finish_reason = data["choices"][0].get("finish_reason", "?")

content = data["choices"][0]["message"].get("content", "")
has_code = "```" in content or "def " in content

print(f"Total time:      {elapsed:.1f}s")
print(f"Completion tokens: {completion_tokens}")
print(f"Total tokens:      {total_tokens}")
print(f"Finish reason:     {finish_reason}")
print(f"Has code block:    {has_code}")
print()

if completion_tokens > 0 and elapsed > 0:
    speed = completion_tokens / elapsed
    print(f"Generation speed:  {speed:.1f} tok/s")
    if speed > 30:
        print("  => EXCELLENT (GPU fully utilized)")
    elif speed > 15:
        print("  => GOOD (GPU working)")
    elif speed > 5:
        print("  => SLOW (partial GPU offload or CPU fallback)")
    else:
        print("  => VERY SLOW (mostly CPU)")
else:
    print("Could not calculate speed (no completion tokens)")

if finish_reason == "length":
    print("\nWARNING: finish_reason='length' - max_tokens was hit before code appeared.")
    print("Suggestion: increase max_tokens to 1024 or 2048.")
