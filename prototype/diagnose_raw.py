import requests
import json

print("=" * 60)
print("RAW RESPONSE DUMP")
print("=" * 60)

payload = {
    "model": "deepseek-ai_-_deepseek-coder-6.7b-instruct",
    "messages": [
        {"role": "system", "content": "You are a coding assistant. Output only Python code in a markdown code block."},
        {"role": "user", "content": "Write a function add(a, b) that returns the sum."}
    ],
    "temperature": 0.3,
    "max_tokens": 512,
    "stream": False
}

try:
    r = requests.post("http://localhost:1234/v1/chat/completions", json=payload, timeout=60)
    data = r.json()
    print(json.dumps(data, indent=2))
    
    if "choices" in data and len(data["choices"]) > 0:
        msg = data["choices"][0]["message"]
        print("\n--- Message fields ---")
        for k, v in msg.items():
            preview = str(v)[:200].replace('\n', ' ')
            print(f"  {k}: {preview}")
    else:
        print("\nNO choices in response!")
        print(f"Response keys: {list(data.keys())}")
except Exception as e:
    print(f"ERROR: {e}")
