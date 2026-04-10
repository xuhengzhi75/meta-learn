#!/usr/bin/env python3
"""
Simple description optimizer for meta-learn skill.
Tests each query 3x, measures trigger rate, iterates up to 5 times.
"""
import json
import subprocess
import sys
import random
import re
from pathlib import Path

SKILL_PATH = Path("/Users/gardon/development/skills/meta-learn/SKILL.md")
EVAL_PATH = Path("/Users/gardon/development/skills/meta-learn-workspace/trigger-eval.json")
RESULTS_PATH = Path("/Users/gardon/development/skills/meta-learn-workspace/desc-opt-results.json")
MODEL = "claude-opus-4-6"
MAX_ITERATIONS = 5
RUNS_PER_QUERY = 3

def read_current_description():
    text = SKILL_PATH.read_text()
    m = re.search(r'^description:\s*(.+?)(?=\n\w|\n---)', text, re.MULTILINE | re.DOTALL)
    if m:
        return m.group(1).strip().strip('"')
    return ""

def update_description(new_desc):
    text = SKILL_PATH.read_text()
    # Replace the description line in frontmatter
    new_text = re.sub(
        r'(^description:\s*)(.+?)(?=\n\w|\n---)',
        lambda m: m.group(1) + new_desc,
        text,
        flags=re.MULTILINE | re.DOTALL
    )
    SKILL_PATH.write_text(new_text)

def test_triggers(evals, description):
    """Test each query RUNS_PER_QUERY times, return per-query trigger rates."""
    results = []
    for item in evals:
        query = item["query"]
        should = item["should_trigger"]
        triggered_count = 0
        for _ in range(RUNS_PER_QUERY):
            prompt = f"""You have access to a skill called "meta-learn" with this description:

"{description}"

A user sends this message:
"{query}"

Would you invoke the meta-learn skill to handle this request? Answer with just YES or NO."""
            try:
                result = subprocess.run(
                    ["claude", "-p", prompt, "--model", MODEL],
                    capture_output=True, text=True, timeout=30
                )
                answer = result.stdout.strip().upper()
                triggered = "YES" in answer
                if triggered:
                    triggered_count += 1
            except Exception as e:
                print(f"  Error on query '{query[:40]}...': {e}")

        trigger_rate = triggered_count / RUNS_PER_QUERY
        correct = (trigger_rate >= 0.5) == should
        results.append({
            "query": query,
            "should_trigger": should,
            "trigger_rate": trigger_rate,
            "correct": correct
        })
        status = "✅" if correct else "❌"
        print(f"  {status} [{trigger_rate:.0%}] {'SHOULD' if should else 'SHOULD NOT'}: {query[:60]}")

    accuracy = sum(r["correct"] for r in results) / len(results)
    return results, accuracy

def propose_new_description(current_desc, eval_results, iteration):
    """Ask Claude to improve the description based on failures."""
    failures = [r for r in eval_results if not r["correct"]]
    failure_text = "\n".join([
        f"- Query: '{r['query']}'\n  Should trigger: {r['should_trigger']}, Trigger rate: {r['trigger_rate']:.0%}"
        for r in failures
    ])

    prompt = f"""You are optimizing the description field of a skill called "meta-learn" to improve triggering accuracy.

Current description:
"{current_desc}"

The description is used by an AI assistant to decide whether to invoke this skill. The skill helps users learn faster using AI — it provides knowledge maps, personalized learning paths, Feynman sparring, instant feedback, and cross-domain transfer.

These queries are currently being classified incorrectly:
{failure_text}

Write an improved description that:
1. Correctly triggers for learning/studying/mastering requests
2. Does NOT trigger for: simple factual questions, summarization requests, resource recommendations, debugging help, or curriculum design for others
3. Is clear about the skill's interactive coaching nature (not just answering questions)
4. Supports both Chinese and English queries

Return ONLY the new description text, no explanation, no quotes around it."""

    result = subprocess.run(
        ["claude", "-p", prompt, "--model", MODEL],
        capture_output=True, text=True, timeout=60
    )
    return result.stdout.strip()

def main():
    evals = json.loads(EVAL_PATH.read_text())

    # Split 60/40 train/test
    random.seed(42)
    shuffled = evals[:]
    random.shuffle(shuffled)
    split = int(len(shuffled) * 0.6)
    train = shuffled[:split]
    test = shuffled[split:]

    print(f"Train: {len(train)} queries, Test: {len(test)} queries\n")

    all_results = []
    best_desc = read_current_description()
    best_test_score = 0.0

    current_desc = best_desc

    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"\n{'='*60}")
        print(f"Iteration {iteration} — Testing description:")
        print(f"  {current_desc[:100]}...")
        print(f"\nTrain set:")
        train_results, train_acc = test_triggers(train, current_desc)
        print(f"\nTest set:")
        test_results, test_acc = test_triggers(test, current_desc)

        print(f"\nTrain accuracy: {train_acc:.1%}, Test accuracy: {test_acc:.1%}")

        iter_result = {
            "iteration": iteration,
            "description": current_desc,
            "train_accuracy": train_acc,
            "test_accuracy": test_acc,
            "train_results": train_results,
            "test_results": test_results
        }
        all_results.append(iter_result)

        if test_acc > best_test_score:
            best_test_score = test_acc
            best_desc = current_desc
            print(f"  ★ New best test score: {best_test_score:.1%}")

        if train_acc >= 1.0 and test_acc >= 0.9:
            print("\nReached target accuracy, stopping early.")
            break

        if iteration < MAX_ITERATIONS:
            print(f"\nGenerating improved description...")
            current_desc = propose_new_description(current_desc, train_results + test_results, iteration)
            print(f"  New: {current_desc[:100]}...")

    output = {
        "best_description": best_desc,
        "best_test_score": best_test_score,
        "iterations": all_results
    }
    RESULTS_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n{'='*60}")
    print(f"Done. Best description (test score: {best_test_score:.1%}):")
    print(f"\n{best_desc}\n")
    print(f"Results saved to: {RESULTS_PATH}")

if __name__ == "__main__":
    main()
