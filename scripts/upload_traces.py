"""
Upload tau bench JSON traces to Braintrust.

Creates:
  - Dataset "Tau Bench Telecom Tasks" (shared task definitions)
  - Experiment "gpt-5-medium" (gpt5_medium.json)
  - Experiment "gpt-5.1-codex-max-medium" (gpt51cm_azure_medium.json)

Run:
    uv run python scripts/upload_traces.py
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import braintrust
from dotenv import load_dotenv

load_dotenv()

PROJECT = "sema4-demo"
DATASET_NAME = "Tau Bench Telecom Tasks"
TRACES_DIR = Path(__file__).parent.parent / "example-traces"

TRACE_FILES = {
    "gpt-5-medium": TRACES_DIR / "gpt5_medium.json",
    "gpt-5.1-codex-max-medium": TRACES_DIR / "gpt51cm_azure_medium.json",
}


def load_trace(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def pass_exp_k(rewards: list[float]) -> float:
    """Sierra metric: 1.0 only if ALL trials succeeded."""
    if not rewards:
        return 0.0
    return 1.0 if all(r == 1.0 for r in rewards) else 0.0


def pass_at_k(rewards: list[float]) -> float:
    """Standard: fraction of trials that succeeded."""
    if not rewards:
        return 0.0
    return sum(rewards) / len(rewards)


def upload_dataset(tasks: list[dict]) -> None:
    """Upsert the shared task dataset in Braintrust."""
    print(f"Upserting dataset '{DATASET_NAME}' with {len(tasks)} tasks...")

    dataset = braintrust.init_dataset(
        project=PROJECT,
        name=DATASET_NAME,
    )

    for task in tasks:
        task_id = task["id"]
        eval_criteria = task.get("evaluation_criteria", {})

        dataset.insert(
            id=str(task_id),
            input={
                "ticket": task.get("ticket", ""),
                "user_scenario": task.get("user_scenario", ""),
                "evaluation_criteria": eval_criteria,
            },
            expected={
                "actions": eval_criteria.get("actions", []),
                "env_assertions": eval_criteria.get("env_assertions", []),
            },
            metadata={
                "task_id": task_id,
                "domain": "telecom",
                "description": task.get("description", ""),
            },
        )

    dataset.flush()
    print(f"  Dataset upsert complete.")


def upload_experiment(experiment_name: str, trace: dict) -> None:
    """Create a Braintrust experiment from one trace file."""
    model = trace["info"]["agent_info"]["llm"]
    num_trials = trace["info"].get("num_trials", 1)
    tasks_by_id = {t["id"]: t for t in trace["tasks"]}
    simulations = trace["simulations"]

    print(f"\nCreating experiment '{experiment_name}' ({model}, {len(simulations)} sims)...")

    # Pre-compute pass_exp_k per task_id across all trials
    rewards_by_task: dict[str, list[float]] = defaultdict(list)
    for sim in simulations:
        task_id = sim["task_id"]
        reward = sim["reward_info"]["reward"]
        rewards_by_task[task_id].append(reward)

    task_pass_exp_k = {
        task_id: pass_exp_k(rewards)
        for task_id, rewards in rewards_by_task.items()
    }
    task_pass_at_k = {
        task_id: pass_at_k(rewards)
        for task_id, rewards in rewards_by_task.items()
    }

    experiment = braintrust.init(
        project=PROJECT,
        experiment=experiment_name,
    )

    for sim in simulations:
        task_id = sim["task_id"]
        task = tasks_by_id.get(task_id, {})
        messages = sim.get("messages", [])

        # Find last agent message
        last_agent_msg = ""
        for msg in reversed(messages):
            role = msg.get("role", "")
            if role == "assistant":
                content = msg.get("content", "")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            last_agent_msg = block.get("text", "")
                            break
                elif isinstance(content, str):
                    last_agent_msg = content
                break

        experiment.log(
            id=f"{task_id}-trial{sim['trial']}",
            input={
                "ticket": task.get("ticket", ""),
                "user_scenario": task.get("user_scenario", ""),
            },
            output={
                "termination_reason": sim.get("termination_reason", ""),
                "message_count": len(messages),
                "last_agent_message": last_agent_msg[:500] if last_agent_msg else "",
            },
            expected={
                "actions": task.get("evaluation_criteria", {}).get("actions", []),
                "env_assertions": task.get("evaluation_criteria", {}).get("env_assertions", []),
            },
            scores={
                "reward": sim["reward_info"]["reward"],
                "pass_exp_k": task_pass_exp_k.get(task_id, 0.0),
                "pass_at_k": task_pass_at_k.get(task_id, 0.0),
            },
            metadata={
                "trial": sim["trial"],
                "model": model,
                "domain": "telecom",
                "agent_cost": sim.get("agent_cost"),
                "duration": sim.get("duration"),
                "task_id": task_id,
                "num_trials": num_trials,
            },
            metrics={
                "duration": sim.get("duration", 0),
            },
        )

    experiment.flush()
    print(f"  Logged {len(simulations)} spans.")
    print(f"  pass_exp_k (mean): {sum(task_pass_exp_k.values()) / len(task_pass_exp_k):.3f}")
    print(f"  pass_at_k  (mean): {sum(task_pass_at_k.values()) / len(task_pass_at_k):.3f}")


def main() -> None:
    if not os.environ.get("BRAINTRUST_API_KEY"):
        print("Error: BRAINTRUST_API_KEY not set. Copy .env.example → .env and fill it in.")
        sys.exit(1)

    # Load traces
    traces = {}
    for name, path in TRACE_FILES.items():
        if not path.exists():
            print(f"Warning: {path} not found, skipping.")
            continue
        traces[name] = load_trace(path)
        print(f"Loaded {path.name}: {len(traces[name]['simulations'])} simulations")

    if not traces:
        print("No trace files found.")
        sys.exit(1)

    # Upload dataset from first trace (tasks are shared)
    first_trace = next(iter(traces.values()))
    upload_dataset(first_trace["tasks"])

    # Upload one experiment per trace
    for experiment_name, trace in traces.items():
        upload_experiment(experiment_name, trace)

    print("\nDone! Open Braintrust and compare experiments side-by-side:")
    print("  https://www.braintrust.dev/app")


if __name__ == "__main__":
    main()
