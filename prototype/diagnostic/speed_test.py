"""
Quick GPU speed test for LM Studio.
Measures prompt processing and token generation speed.
Usage:
    python speed_test.py                    # test default model
    python speed_test.py --model deepseek-coder-v2-lite-instruct
"""
import requests
import time
import argparse

URL = "http://localhost:1234/v1/chat/completions"

def test_model(model, max_tokens=512):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a code generator. Output ONLY a markdown code block containing the Python function. No explanations."},
            {"role": "user", "content": "Write a function factorial(n) that returns n! using recursion."}
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "stream": False
    }

    print(f"\n{'='*50}")
    print(f"Speed Test: {model}")
    print(f"max_tokens: {max_tokens}")
    print(f"{'='*50}")

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

    print(f"Total time:        {elapsed:.1f}s")
    print(f"Completion tokens: {completion_tokens}")
    print(f"Total tokens:      {total_tokens}")
    print(f"Finish reason:     {finish_reason}")
    print(f"Has code block:    {has_code}")

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
        print("WARNING: max_tokens was hit before code appeared. Increase max_tokens.")
    
    return speed if (completion_tokens > 0 and elapsed > 0) else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="deepseek-r1-distill-qwen-7b",
                        help="Model to test")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--compare", action="store_true",
                        help="Compare R1 vs non-reasoning model")
    args = parser.parse_args()

    if args.compare:
        r1_speed = test_model("deepseek-r1-distill-qwen-7b", args.max_tokens)
        coder_speed = test_model("deepseek-coder-v2-lite-instruct", 512)
        print(f"\n{'='*50}")
        print("COMPARISON")
        print(f"  R1-7B:           {r1_speed:.1f} tok/s")
        print(f"  Coder-v2-lite:   {coder_speed:.1f} tok/s")
        print(f"  Speedup:         {coder_speed/max(r1_speed,0.1):.1f}x")
        print(f"{'='*50}")
    else:
        test_model(args.model, args.max_tokens)


if __name__ == "__main__":
    main()
