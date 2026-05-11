"""
Merge LoRA Adapter into Base Model
====================================

After fine-tuning, merge the adapter weights back into the base model
for faster inference (no adapter overhead).

Usage:
    python merge_adapter.py --base Qwen/Qwen2.5-Coder-7B-Instruct \
                            --adapter empirical_adapter \
                            --output puzzle_logic_model_merged
"""

import argparse
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=str, required=True, help="Base model path")
    parser.add_argument("--adapter", type=str, required=True, help="LoRA adapter path")
    parser.add_argument("--output", type=str, default="puzzle_logic_model_merged")
    parser.add_argument("--push", action="store_true", help="Push to HuggingFace Hub")
    args = parser.parse_args()
    
    print(f"Loading base model: {args.base}")
    model = AutoModelForCausalLM.from_pretrained(
        args.base,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
    
    print(f"Loading adapter: {args.adapter}")
    model = PeftModel.from_pretrained(model, args.adapter)
    
    print("Merging adapter into base model...")
    model = model.merge_and_unload()
    
    print(f"Saving merged model to {args.output}")
    model.save_pretrained(args.output)
    tokenizer.save_pretrained(args.output)
    
    if args.push:
        print(f"Pushing to HuggingFace Hub...")
        model.push_to_hub(args.output)
        tokenizer.push_to_hub(args.output)
    
    print("Done!")
    print(f"Merged model saved to: {args.output}")
    print(f"Load with: AutoModelForCausalLM.from_pretrained('{args.output}')")


if __name__ == "__main__":
    main()
