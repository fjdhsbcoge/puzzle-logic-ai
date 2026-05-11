"""
LMStudio Concurrency Diagnostic
=================================
Sends 4 identical simple requests simultaneously and measures
whether they return at the same time (parallel) or one-by-one (serial).

Usage:
    python lmstudio_concurrency_test.py
"""

import time
import threading
import requests

URL = "http://localhost:1234/v1/chat/completions"
PAYLOAD = {
    "model": "local-model",
    "messages": [
        {"role": "user", "content": "Write a Python function that returns 1+1."}
    ],
    "temperature": 0.0,
    "max_tokens": 100,
    "stream": False
}

def send_request(idx):
    t0 = time.time()
    try:
        response = requests.post(URL, json=PAYLOAD, timeout=60)
        response.raise_for_status()
        t1 = time.time()
        return {"idx": idx, "status": "OK", "elapsed": t1 - t0, "start": t0}
    except Exception as e:
        t1 = time.time()
        return {"idx": idx, "status": f"ERR: {e}", "elapsed": t1 - t0, "start": t0}

results = []
lock = threading.Lock()

def worker(idx):
    r = send_request(idx)
    with lock:
        results.append(r)

print("Sending 4 identical requests SIMULTANEOUSLY...")
print("If LMStudio processes them in parallel, all 4 should finish at roughly the same time.")
print("If it queues them, you'll see sequential finish times.\n")

threads = []
overall_t0 = time.time()
for i in range(4):
    t = threading.Thread(target=worker, args=(i,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()

overall_t1 = time.time()

# Sort by start time
results.sort(key=lambda x: x["start"])

print("Results:")
print(f"{'Req':>4} {'Start':>8} {'Elapsed':>10} {'Status'}")
for r in results:
    print(f"{r['idx']:>4} {r['start']-overall_t0:>8.2f}s {r['elapsed']:>10.2f}s {r['status']}")

print(f"\nTotal wall-clock time: {overall_t1 - overall_t0:.2f}s")
print(f"Sum of individual times: {sum(r['elapsed'] for r in results):.2f}s")

if (overall_t1 - overall_t0) < max(r['elapsed'] for r in results) * 1.5:
    print("\n✅ PARALLEL: Wall time ~= single request time. LMStudio IS processing concurrently.")
else:
    print("\n❌ SERIAL: Wall time ~= sum of requests. LMStudio is QUEUING them.")
    print("   The 'Max Concurrent Predictions' setting may not apply to the API endpoint.")
