r"""
Push Results to GitHub
======================

Commits puzzle_logic_log.json, knowledge graph, and training data
to the git repo and pushes to GitHub. Run this anytime to save progress
remotely, or set up Windows Task Scheduler to run it automatically.

Usage:
    # Manual push
    python scripts/push_results.py

    # Push with custom message
    python scripts/push_results.py --message "After 500 problems, iter 1"

Setup for auto-push every 6 hours:
    1. Open Task Scheduler (taskschd.msc)
    2. Create Basic Task → Name: "PuzzleLogic Push"
    3. Trigger: Daily, repeat every 6 hours
    4. Action: Start program
       Program: python
       Arguments: C:\Users\Tobias Rickert\Desktop\puzzle-logic-ai\scripts\push_results.py
    5. Finish
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).parent.parent


def run_git(cmd, cwd=None):
    """Run a git command."""
    result = subprocess.run(
        ["git"] + cmd,
        cwd=cwd or str(REPO_DIR),
        capture_output=True,
        text=True
    )
    return result.returncode == 0, result.stdout, result.stderr


def main():
    parser = argparse.ArgumentParser(description="Push Puzzle Logic results to GitHub")
    parser.add_argument("--message", type=str, default=None,
                        help="Custom commit message. Default: auto-generated timestamp.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be committed without actually pushing.")
    args = parser.parse_args()

    # Check if git repo exists
    ok, _, _ = run_git(["status"])
    if not ok:
        print("ERROR: Not a git repository. Run 'git init' and 'git remote add origin <url>' first.")
        return 1

    # Auto-generate commit message if not provided
    if not args.message:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        args.message = f"Results update: {now}"

    # Check which result files exist
    files_to_commit = []
    for pattern in ["puzzle_logic_log*.json", "puzzle_logic_knowledge*.json", "training_data*.jsonl", "console_output.txt"]:
        for f in REPO_DIR.rglob(pattern):
            if f.is_file():
                files_to_commit.append(str(f.relative_to(REPO_DIR)))

    if not files_to_commit:
        print("No result files found to commit.")
        return 0

    print(f"Files to commit ({len(files_to_commit)}):")
    for f in files_to_commit[:10]:
        print(f"  {f}")
    if len(files_to_commit) > 10:
        print(f"  ... and {len(files_to_commit) - 10} more")

    if args.dry_run:
        print(f"\nDry run — would commit with message: '{args.message}'")
        return 0

    # Stage files
    for f in files_to_commit:
        run_git(["add", f])

    # Check if there's anything to commit
    ok, stdout, _ = run_git(["diff", "--cached", "--quiet"])
    if ok:
        print("No changes to commit.")
        return 0

    # Commit
    ok, stdout, stderr = run_git(["commit", "-m", args.message])
    if not ok:
        print(f"Commit failed: {stderr}")
        return 1

    print(f"Committed: {args.message}")

    # Push
    ok, stdout, stderr = run_git(["push", "origin", "main"])
    if not ok:
        # Try 'master' branch name
        ok, stdout, stderr = run_git(["push", "origin", "master"])
        if not ok:
            print(f"Push failed: {stderr}")
            print("Check your git remote: git remote -v")
            return 1

    print("Pushed to GitHub successfully!")
    print(f"View results at: https://github.com/YOUR_USERNAME/puzzle-logic-ai")
    return 0


if __name__ == "__main__":
    sys.exit(main())
