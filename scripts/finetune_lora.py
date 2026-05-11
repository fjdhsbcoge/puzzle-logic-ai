"""
Fine-tune Qwen 2.5 7B with QLoRA on Empirical Training Data
===============================================================

Uses 4-bit quantization + LoRA adapters to fit on consumer GPUs.
Trains the model on verified empirical fixes from the knowledge graph.

Requirements:
    pip install transformers peft accelerate bitsandbytes datasets

Usage:
    python finetune_lora.py --model Qwen/Qwen2.5-Coder-7B-Instruct \
                            --data training_data.jsonl \
                            --output empirical_adapter

The fine-tuned model will learn: "given error X, produce fix Y"
"""

import argparse
import json
import os
import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM, 
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq,
    BitsAndBytesConfig
)


def load_training_data(path: str):
    """Load ShareGPT-format JSONL."""
    examples = []
    with open(path, 'r') as f:
        for line in f:
            examples.append(json.loads(line))
    return Dataset.from_list(examples)


def format_chat(example, tokenizer):
    """Convert messages to a single string for training."""
    messages = example['messages']
    text = tokenizer.apply_chat_template(
        messages, 
        tokenize=False, 
        add_generation_prompt=False
    )
    return {"text": text}


def tokenize_function(examples, tokenizer, max_length=1024):
    """Tokenize the formatted text."""
    outputs = tokenizer(
        examples['text'],
        truncation=True,
        max_length=max_length,
        padding='max_length',
        return_tensors=None,
    )
    # Labels are the same as input_ids for causal LM training
    outputs['labels'] = outputs['input_ids'].copy()
    return outputs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, required=True, 
                        help="Base model name or path (e.g., Qwen/Qwen2.5-Coder-7B-Instruct)")
    parser.add_argument("--data", type=str, required=True,
                        help="Training data JSONL file")
    parser.add_argument("--output", type=str, default="empirical_adapter",
                        help="Output directory for LoRA adapter")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--lora-r", type=int, default=16,
                        help="LoRA rank (higher = more capacity, default 16)")
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--max-length", type=int, default=1024)
    args = parser.parse_args()
    
    print(f"Loading base model: {args.model}")
    print(f"Training data: {args.data}")
    print(f"Output: {args.output}")
    
    # ── 4-bit quantization config with CPU offloading support ──
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        llm_int8_enable_fp32_cpu_offload=True,  # allow CPU offloading for layers that don't fit
    )
    
    # Auto-detect GPU memory and set limits
    if torch.cuda.is_available():
        total_vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        print(f"  GPU VRAM: {total_vram:.1f} GB")
        # Leave 1GB headroom for activations during training
        gpu_limit = max(1, int(total_vram - 1))
        max_memory = {0: f"{gpu_limit}GB", "cpu": "30GB"}
        print(f"  Using GPU: {gpu_limit}GB, rest to CPU")
    else:
        max_memory = None
    
    # ── Load model and tokenizer ──
    tokenizer = AutoTokenizer.from_pretrained(
        args.model,
        trust_remote_code=True,
        padding_side="right"
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=bnb_config,
        device_map="auto",
        max_memory=max_memory,
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    
    # Prepare for k-bit training
    model = prepare_model_for_kbit_training(model)
    
    # ── LoRA config ──
    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", 
                       "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    
    model = get_peft_model(model, lora_config)
    print(f"Trainable parameters: {model.print_trainable_parameters()}")
    
    # ── Load and prepare data ──
    print("Loading training data...")
    dataset = load_training_data(args.data)
    print(f"  {len(dataset)} examples")
    
    # Format and tokenize
    dataset = dataset.map(lambda x: format_chat(x, tokenizer), remove_columns=dataset.column_names)
    dataset = dataset.map(lambda x: tokenize_function(x, tokenizer, args.max_length), batched=True)
    
    # ── Training arguments ──
    training_args = TrainingArguments(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=1,  # reduced from 4 for lower VRAM
        gradient_accumulation_steps=8,    # compensate with larger grad accum
        learning_rate=args.lr,
        warmup_steps=10,
        logging_steps=10,
        save_strategy="epoch",
        fp16=False,
        bf16=True,
        optim="paged_adamw_8bit",
        report_to="none",
    )
    
    # ── Train ──
    print("Starting training...")
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        data_collator=DataCollatorForSeq2Seq(tokenizer, pad_to_multiple_of=8),
    )
    
    trainer.train()
    
    # ── Save adapter ──
    print(f"Saving adapter to {args.output}")
    model.save_pretrained(args.output)
    tokenizer.save_pretrained(args.output)
    
    print("\nDone! To use the fine-tuned model:")
    print(f"  1. Load base model + adapter from {args.output}")
    print(f"  2. Or merge: python scripts/merge_adapter.py --base {args.model} --adapter {args.output} --output merged_model")


if __name__ == "__main__":
    main()
