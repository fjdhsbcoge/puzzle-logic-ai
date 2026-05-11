"""
Download Model from HuggingFace
=================================

Simple script to download a model without needing huggingface-cli.

Usage:
    python scripts/download_model.py --model Qwen/Qwen2.5-Coder-7B-Instruct --output C:\models\qwen7b
"""

import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="Qwen/Qwen2.5-Coder-7B-Instruct",
                        help="HuggingFace model ID")
    parser.add_argument("--output", type=str, required=True,
                        help="Local directory to save the model")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading: {args.model}")
    print(f"Saving to:   {output_dir}")
    print()

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from huggingface_hub import snapshot_download
        
        # Method 1: Use snapshot_download (faster, resumes interrupted downloads)
        print("Method: snapshot_download")
        snapshot_download(
            repo_id=args.model,
            local_dir=str(output_dir),
            local_dir_use_symlinks=False,
            resume_download=True,
        )
        print(f"\nDone! Model saved to: {output_dir}")
        
    except ImportError:
        print("ERROR: transformers or huggingface_hub not installed.")
        print("Run: pip install transformers huggingface_hub")
        return
    except Exception as e:
        print(f"ERROR: {e}")
        print()
        print("If you see '401 Unauthorized' or 'Repository Not Found':")
        print("  1. Go to https://huggingface.co/settings/tokens")
        print("  2. Create a 'Read' token")
        print("  3. Run this in Python:")
        print("     from huggingface_hub import login")
        print("     login('YOUR_TOKEN_HERE')")
        return


if __name__ == "__main__":
    main()
