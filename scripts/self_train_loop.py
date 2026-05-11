"""
Self-Training Loop for Puzzle Logic — v2 (Accumulative Knowledge Graph)
=========================================================================

Iteratively runs MBPP, accumulates empirical knowledge, and fine-tunes.

Key design: The knowledge graph LIVES across iterations. We track what
was added/updated each round. Fine-tuning uses ALL historical data.

Flow per iteration:
  1. Load existing knowledge graph (or start fresh on iter 1)
  2. Run MBPP benchmark with current model
  3. Log NEW patterns added this iteration
  4. Extract training data from ALL historical logs
  5. Fine-tune base model on accumulated dataset
  6. Merge adapter
  7. Next iteration

Usage:
    # Start from zero (base model, fresh graph)
    python scripts/self_train_loop.py --model qwen2.5-coder-7b-instruct --limit 974 --iterations 3

    # Continue from previous iteration (merged model, keep graph)
    python scripts/self_train_loop.py --model ./puzzle_logic_model_merged_v1 --limit 974 --iterations 2
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_DIR = SCRIPT_DIR.parent
PROTOTYPE_DIR = REPO_DIR / "prototype"


def run_command(cmd, cwd=None, timeout=None):
    """Run a shell command and stream output."""
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=False, text=True, timeout=timeout)
    if result.returncode != 0:
        print(f"ERROR: Command failed with code {result.returncode}")
        return False
    return True


def backup_and_reset_log():
    """Archive the previous log, start fresh for this iteration."""
    log_file = PROTOTYPE_DIR / "puzzle_logic_log.json"
    if log_file.exists():
        # Archive with timestamp
        archive_name = f"puzzle_logic_log_{time.strftime('%Y%m%d_%H%M%S')}.json"
        archive_path = PROTOTYPE_DIR / archive_name
        log_file.rename(archive_path)
        print(f"  Archived previous log to: {archive_name}")
        return archive_path
    return None


def run_benchmark(model_name, limit, workers=4):
    """Run the MBPP benchmark."""
    runner = PROTOTYPE_DIR / "mbpp_three_way_runner_v26.py"
    if not runner.exists():
        print(f"ERROR: Runner not found at {runner}")
        return False

    cmd = [
        sys.executable, str(runner),
        "--model", model_name,
        "--limit", str(limit),
        "--workers", str(workers),
    ]
    return run_command(cmd, cwd=str(PROTOTYPE_DIR), timeout=limit * 45)


def analyze_graph_growth(old_kg_path, new_kg_path):
    """Compare knowledge graphs to find new/updated patterns."""
    if not old_kg_path or not old_kg_path.exists():
        return {"total_before": 0, "total_after": 0, "new_patterns": 0, "updated_patterns": 0}

    with open(old_kg_path, 'r') as f:
        old = json.load(f)
    with open(new_kg_path, 'r') as f:
        new = json.load(f)

    old_patterns = {p.get('error_signature', '') + '|' + p.get('fix_strategy', '') for p in old.get('patterns', [])}
    new_patterns = {p.get('error_signature', '') + '|' + p.get('fix_strategy', '') for p in new.get('patterns', [])}

    new_count = len(new_patterns - old_patterns)
    updated = len(new_patterns & old_patterns)  # patterns that existed and were updated

    return {
        "total_before": len(old_patterns),
        "total_after": len(new_patterns),
        "new_patterns": new_count,
        "updated_patterns": updated,
    }


def extract_training_data(all_logs, output_file):
    """Extract training data from ALL historical logs."""
    prep_script = SCRIPT_DIR / "prepare_training_data.py"
    if not prep_script.exists():
        print(f"ERROR: prepare_training_data.py not found")
        return False

    # Combine all logs into a single file for processing
    combined_log = REPO_DIR / "_combined_log_temp.json"
    all_baseline = []
    all_basic = []
    all_advanced = []

    for log_file in all_logs:
        if not log_file.exists():
            continue
        with open(log_file, 'r') as f:
            data = json.load(f)
        all_baseline.extend(data.get('baseline_results', []))
        all_basic.extend(data.get('basic_results', []))
        all_advanced.extend(data.get('advanced_results', []))

    with open(combined_log, 'w') as f:
        json.dump({
            "model": "combined",
            "baseline_results": all_baseline,
            "basic_results": all_basic,
            "advanced_results": all_advanced,
        }, f)

    cmd = [
        sys.executable, str(prep_script),
        "--log", str(combined_log),
        "--output", str(output_file),
    ]
    success = run_command(cmd, cwd=str(REPO_DIR))
    combined_log.unlink()  # Clean up temp file
    return success


def count_training_examples(data_file):
    """Count examples in the training data file."""
    if not data_file.exists():
        return 0
    count = 0
    with open(data_file, 'r') as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def fine_tune(base_model, data_file, output_dir, epochs=3):
    """Fine-tune the base model with QLoRA."""
    ft_script = SCRIPT_DIR / "finetune_lora.py"
    if not ft_script.exists():
        print(f"ERROR: finetune_lora.py not found")
        return False

    cmd = [
        sys.executable, str(ft_script),
        "--model", base_model,
        "--data", str(data_file),
        "--output", str(output_dir),
        "--epochs", str(epochs),
    ]
    return run_command(cmd, cwd=str(REPO_DIR), timeout=3600 * 6)


def merge_adapter(base_model, adapter_dir, output_dir):
    """Merge LoRA adapter back into base model."""
    merge_script = SCRIPT_DIR / "merge_adapter.py"
    if not merge_script.exists():
        print(f"ERROR: merge_adapter.py not found")
        return False

    cmd = [
        sys.executable, str(merge_script),
        "--base", base_model,
        "--adapter", str(adapter_dir),
        "--output", str(output_dir),
    ]
    return run_command(cmd, cwd=str(REPO_DIR), timeout=3600)


def load_results(log_file):
    """Load and summarize benchmark results."""
    if not log_file.exists():
        return None
    with open(log_file, 'r') as f:
        data = json.load(f)

    n = len(data.get('baseline_results', []))
    baseline_passed = sum(1 for r in data.get('baseline_results', []) if r.get('passed'))
    basic_passed = sum(1 for r in data.get('basic_results', []) if r.get('passed'))
    advanced_passed = sum(1 for r in data.get('advanced_results', []) if r.get('passed'))

    return {
        'n': n,
        'baseline': baseline_passed,
        'basic': basic_passed,
        'advanced': advanced_passed,
        'baseline_pct': baseline_passed / n * 100 if n else 0,
        'basic_pct': basic_passed / n * 100 if n else 0,
        'advanced_pct': advanced_passed / n * 100 if n else 0,
    }


def print_iteration_summary(iter_num, results, graph_stats=None):
    """Print formatted summary."""
    print("\n" + "=" * 60)
    print(f"  ITERATION {iter_num} RESULTS")
    print("=" * 60)
    print(f"  Problems:     {results['n']}")
    print(f"  Baseline:     {results['baseline']}/{results['n']} = {results['baseline_pct']:.1f}%")
    print(f"  Basic V2:     {results['basic']}/{results['n']} = {results['basic_pct']:.1f}%")
    print(f"  Advanced V2:  {results['advanced']}/{results['n']} = {results['advanced_pct']:.1f}%")
    if graph_stats:
        print()
        print(f"  Knowledge Graph Growth:")
        print(f"    Before:     {graph_stats['total_before']} patterns")
        print(f"    After:      {graph_stats['total_after']} patterns")
        print(f"    NEW:        {graph_stats['new_patterns']} patterns")
        print(f"    Updated:    {graph_stats['updated_patterns']} patterns")
    print("=" * 60)


def print_lmstudio_instructions(model_path, iter_num):
    """Print instructions for loading the merged model into LMStudio."""
    print("\n" + "=" * 60)
    print(f"  NEXT STEP: Load Model for Iteration {iter_num + 1}")
    print("=" * 60)
    print(f"  Merged model: {model_path}")
    print()
    print("  1. Open LMStudio")
    print("  2. Developer → Load a Model")
    print(f"  3. Select folder: {model_path}")
    print("  4. Set GPU offload to maximum")
    print("  5. Start the server")
    print("  6. Confirm at http://localhost:1234/v1/models")
    print()
    print("  Then continue the loop:")
    print(f"    python scripts/self_train_loop.py --model {model_path} --limit ...")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Puzzle Logic Self-Training Loop (Accumulative)")
    parser.add_argument("--model", type=str, required=True,
                        help="Model identifier for LMStudio API (e.g., qwen2.5-coder-7b-instruct).")
    parser.add_argument("--base-model", type=str, default=None,
                        help="HuggingFace model ID OR local path for fine-tuning. "
                             "Examples: 'Qwen/Qwen2.5-Coder-7B-Instruct' or 'C:\\models\\qwen7b'. "
                             "If not set, uses --model value (must be valid HF ID or local path).")
    parser.add_argument("--limit", type=int, default=974,
                        help="Number of MBPP problems per iteration (default: 974)")
    parser.add_argument("--iterations", type=int, default=3,
                        help="Number of self-training iterations (default: 3)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Concurrent workers for benchmark (default: 4)")
    parser.add_argument("--epochs", type=int, default=3,
                        help="Fine-tuning epochs per iteration (default: 3)")
    parser.add_argument("--fresh-start", action="store_true",
                        help="Delete knowledge graph and start from zero (only for iteration 1)")
    parser.add_argument("--skip-benchmark", action="store_true",
                        help="Skip benchmark (use existing puzzle_logic_log.json)")
    parser.add_argument("--skip-finetune", action="store_true",
                        help="Skip fine-tuning (just extract training data)")
    args = parser.parse_args()

    current_model = args.model
    results_history = []
    all_log_files = []
    current_kg = PROTOTYPE_DIR / "puzzle_logic_knowledge.json"

    for iteration in range(1, args.iterations + 1):
        print("\n" + "=" * 70)
        print(f"  ITERATION {iteration} / {args.iterations}")
        print(f"  Model: {current_model}")
        print("=" * 70)

        # ── Step 1: Archive previous log, keep knowledge graph ──
        if not args.skip_benchmark:
            print("\n[1/6] Archiving previous log (keeping knowledge graph)...")
            archived_log = backup_and_reset_log()
            if archived_log:
                all_log_files.append(archived_log)
                print(f"  Historical logs: {len(all_log_files)}")

            if args.fresh_start and iteration == 1:
                print("  --fresh-start: Deleting knowledge graph")
                if current_kg.exists():
                    current_kg.unlink()

        # ── Step 2: Run benchmark ──
        log_file = PROTOTYPE_DIR / "puzzle_logic_log.json"
        old_kg = current_kg if current_kg.exists() else None

        if not args.skip_benchmark:
            print(f"\n[2/6] Running MBPP benchmark ({args.limit} problems)...")
            print("  Keep LMStudio running.")
            success = run_benchmark(current_model, args.limit, args.workers)
            if not success:
                print("ERROR: Benchmark failed. Stopping.")
                return
        else:
            print("\n[2/6] Skipping benchmark (using existing log)")
            if not log_file.exists():
                print("ERROR: No existing log file.")
                return

        # ── Step 3: Analyze knowledge graph growth ──
        print("\n[3/6] Analyzing knowledge graph growth...")
        graph_stats = analyze_graph_growth(old_kg, current_kg)
        print(f"  Graph: {graph_stats['total_before']} → {graph_stats['total_after']} "
              f"(+{graph_stats['new_patterns']} new, {graph_stats['updated_patterns']} updated)")

        # ── Step 4: Extract cumulative training data ──
        # Add current log to historical collection
        all_log_files.append(log_file)

        data_file = REPO_DIR / f"training_data_iter{iteration}.jsonl"
        print(f"\n[4/6] Extracting training data from ALL {len(all_log_files)} historical logs...")
        success = extract_training_data(all_log_files, data_file)
        if not success:
            print("ERROR: Training data extraction failed.")
            return

        n_examples = count_training_examples(data_file)
        print(f"  Total training examples (all iterations): {n_examples}")

        # Load and print results
        results = load_results(log_file)
        if results:
            print_iteration_summary(iteration, results, graph_stats)
            results_history.append(results)

        if args.skip_finetune:
            print("\n[5/6] Skipping fine-tuning")
            print("[6/6] Skipping merge")
            continue

        # Determine the actual model path for fine-tuning
        ft_model = args.base_model or args.model
        
        # ── Step 5: Fine-tune on cumulative data ──
        adapter_dir = REPO_DIR / f"empirical_adapter_iter{iteration}"
        print(f"\n[5/6] Fine-tuning with QLoRA (cumulative data, {n_examples} examples)...")
        print(f"  Base model for training: {ft_model}")
        print("  This will take 2-4 hours.")
        print("  NOTE: If this fails with 'Repository Not Found', you need to either:")
        print("    A) Download the model from HuggingFace first:")
        print(f"       huggingface-cli download Qwen/Qwen2.5-Coder-7B-Instruct --local-dir C:\\models\\qwen7b")
        print("    B) Pass the local model path: --base-model C:\\models\\qwen7b")
        success = fine_tune(ft_model, data_file, adapter_dir, args.epochs)
        if not success:
            print("ERROR: Fine-tuning failed.")
            return

        # ── Step 6: Merge adapter ──
        merged_dir = REPO_DIR / f"puzzle_logic_model_merged_iter{iteration}"
        print(f"\n[6/6] Merging adapter into base model ({merged_dir})...")
        # Use ft_model (local path or HF ID) for merge, not the LMStudio identifier
        merge_base = args.base_model or current_model
        success = merge_adapter(merge_base, adapter_dir, merged_dir)
        if not success:
            print("ERROR: Merge failed.")
            return

        # Update model for next iteration
        current_model = str(merged_dir)
        print_lmstudio_instructions(current_model, iteration)

    # ── Final summary ──
    print("\n" + "=" * 70)
    print("  SELF-TRAINING LOOP COMPLETE")
    print("=" * 70)
    for i, r in enumerate(results_history, 1):
        print(f"  Iteration {i}: B={r['baseline_pct']:.1f}%  Ba={r['basic_pct']:.1f}%  Ad={r['advanced_pct']:.1f}%")
    print("=" * 70)


if __name__ == "__main__":
    main()
