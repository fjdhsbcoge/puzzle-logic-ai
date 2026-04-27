"""
Quick diagnostic: what does the model output for HumanEval/0?
"""
from humaneval_compare_runner import load_humaneval
from lmstudio_client import LMStudioClient
from mbpp_cg_runner import extract_code

p = load_humaneval()[0]
print("=" * 60)
print(f"Problem: {p['task_id']}")
print(f"Prompt length: {len(p['prompt'])} chars")
print(f"Prompt ends with:\n{p['prompt'][-200:]}")
print("=" * 60)

synapse = LMStudioClient(model="qwen2.5-coder-3b-instruct")
raw = synapse.generate(prompt=p["prompt"], temperature=0.0, max_tokens=1024, n=1)
raw_text = raw[0] if raw and raw[0] else ""

print(f"\nRaw response length: {len(raw_text)} chars")
print(f"Raw response:\n{'-'*40}")
print(raw_text)
print(f"{'-'*40}")

extracted = extract_code(raw_text)
print(f"\nExtracted code length: {len(extracted)} chars")
print(f"Extracted code:\n{'-'*40}")
print(extracted)
print(f"{'-'*40}")

# Check if it starts with 'python'
if extracted.startswith("python"):
    print("\nWARNING: Extracted code starts with 'python' — extraction bug!")
else:
    print("\nOK: Extracted code starts correctly")
