"""
LMStudio Concurrency Diagnostic v2
====================================
Tests BOTH the old OpenAI-compatible endpoint AND the new REST API v1 endpoint
to find which one works and whether LMStudio processes requests in parallel.

Usage:
    python lmstudio_diag.py
"""

import time
import threading
import json
import sys

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

# ── Config ──
OLD_URL = "http://localhost:1234/v1/chat/completions"
NEW_URL = "http://localhost:1234/api/v1/chat"

def test_endpoint(name, url, payload, headers, extract_content_fn):
    """Send 4 requests simultaneously and measure timing."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)[:200]}...")
    
    results = []
    lock = threading.Lock()
    
    def worker(idx):
        t0 = time.time()
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            t1 = time.time()
            
            if resp.status_code != 200:
                with lock:
                    results.append({
                        "idx": idx,
                        "status": f"HTTP {resp.status_code}",
                        "error": resp.text[:200],
                        "elapsed": t1 - t0,
                        "start": t0,
                        "tokens_per_sec": None
                    })
                return
            
            data = resp.json()
            content = extract_content_fn(data)
            
            # Try to get tokens_per_second from response
            tps = None
            if isinstance(data, dict):
                stats = data.get("stats", {})
                if stats:
                    tps = stats.get("tokens_per_second")
            
            with lock:
                results.append({
                    "idx": idx,
                    "status": "OK",
                    "content_preview": content[:60] if content else "(empty)",
                    "elapsed": t1 - t0,
                    "start": t0,
                    "tokens_per_sec": tps
                })
        except Exception as e:
            t1 = time.time()
            with lock:
                results.append({
                    "idx": idx,
                    "status": f"ERR: {e}",
                    "elapsed": t1 - t0,
                    "start": t0,
                    "tokens_per_sec": None
                })
    
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
    
    # Check results
    ok_count = sum(1 for r in results if r["status"] == "OK")
    if ok_count == 0:
        print("  ❌ ALL REQUESTS FAILED")
        for r in results:
            print(f"    Req {r['idx']}: {r['status']}")
        return False
    
    print(f"\n  Results ({ok_count}/4 succeeded):")
    print(f"  {'Req':>4} {'Start':>8} {'Elapsed':>10} {'TPS':>10} {'Status'}")
    for r in results:
        tps_str = f"{r['tokens_per_sec']:.1f}" if r['tokens_per_sec'] else "N/A"
        print(f"  {r['idx']:>4} {r['start']-overall_t0:>8.2f}s {r['elapsed']:>10.2f}s {tps_str:>10} {r['status']}")
    
    wall_time = overall_t1 - overall_t0
    sum_time = sum(r['elapsed'] for r in results if r['status'] == 'OK')
    
    print(f"\n  Wall-clock time: {wall_time:.2f}s")
    print(f"  Sum of individual times: {sum_time:.2f}s")
    
    if wall_time < max(r['elapsed'] for r in results if r['status'] == 'OK') * 1.5:
        print(f"\n  ✅ PARALLEL: Wall time ~= single request time")
        print(f"     GPU is processing multiple requests concurrently!")
        return True
    else:
        print(f"\n  ❌ SERIAL: Wall time ~= sum of requests")
        print(f"     LMStudio is QUEUEING requests. 'Max Concurrent Predictions'")
        print(f"     may apply only to the inference engine, not the HTTP queue.")
        return False


# ═══════════════════════════════════════════════════════════════════════
# Test 1: Old OpenAI-compatible endpoint
# ═══════════════════════════════════════════════════════════════════════

def old_extract(data):
    try:
        return data["choices"][0]["message"]["content"]
    except:
        return str(data)[:100]

old_payload = {
    "model": "local-model",
    "messages": [
        {"role": "system", "content": "You are a helpful coding assistant."},
        {"role": "user", "content": "Write a Python function that returns 1+1."}
    ],
    "temperature": 0.0,
    "max_tokens": 100,
    "stream": False
}

old_headers = {"Content-Type": "application/json"}

old_works = test_endpoint("Old API (/v1/chat/completions)", OLD_URL, old_payload, old_headers, old_extract)


# ═══════════════════════════════════════════════════════════════════════
# Test 2: New REST API v1 endpoint
# ═══════════════════════════════════════════════════════════════════════

def new_extract(data):
    try:
        for item in data.get("output", []):
            if item.get("type") == "message":
                return item.get("content", "")
        return str(data)[:100]
    except:
        return str(data)[:100]

new_payload = {
    "model": "local-model",
    "input": "Write a Python function that returns 1+1.",
    "system_prompt": "You are a helpful coding assistant.",
    "temperature": 0.0,
    "max_output_tokens": 100,
    "stream": False
}

new_headers = {"Content-Type": "application/json"}
# If you have API tokens enabled, uncomment:
# new_headers["Authorization"] = "Bearer YOUR_TOKEN_HERE"

new_works = test_endpoint("New REST API v1 (/api/v1/chat)", NEW_URL, new_payload, new_headers, new_extract)


# ═══════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════

print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")

if old_works:
    print("✅ Old API works AND processes requests in parallel")
if new_works:
    print("✅ New REST API v1 works AND processes requests in parallel")

if not old_works and not new_works:
    print("❌ Neither endpoint showed parallel processing.")
    print("\nPossible causes:")
    print("  1. LMStudio's 'Max Concurrent Predictions' only affects internal")
    print("     batching, not the HTTP API server queue.")
    print("  2. The server is single-threaded for API requests.")
    print("  3. Only one model instance is loaded.")
    print("\nRecommended fix:")
    print("  Run MULTIPLE LMStudio instances on different ports:")
    print("    Instance 1: http://localhost:1234/v1")
    print("    Instance 2: http://localhost:1235/v1")
    print("    Instance 3: http://localhost:1236/v1")
    print("    Instance 4: http://localhost:1237/v1")
    print("  Then round-robin requests across them.")
