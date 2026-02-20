"""
Run 10 SQL gen tasks and send scored traces to the Braintrust project Logs tab.

Each trace appears as a row in the Logs view with:
  - input:  { question, db_path }
  - output: { sql, result, iterations }
  - expected: { expected_sql }
  - scores: { sql_correctness, pass_exp_k }

Run:
    uv run python scripts/run_log_examples.py
"""

import os
import sys
from pathlib import Path

import braintrust
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.agent import run_sql_gen_task
from data.sql_tasks import TASKS, setup_db

_DB_PATH = os.environ.get("SEMA4_DB_PATH", "/tmp/sema4_eval.db")
_N = 10  # number of tasks to run


def main() -> None:
    if not os.environ.get("BRAINTRUST_API_KEY"):
        print("Error: BRAINTRUST_API_KEY not set.")
        sys.exit(1)

    setup_db(_DB_PATH)
    print(f"DB: {_DB_PATH}")

    # init_logger routes @traced spans to the project Logs tab (not Experiments)
    braintrust.init_logger(project="sema4-demo")

    tasks = TASKS[:_N]
    print(f"Running {len(tasks)} tasks → Braintrust Logs...\n")

    for i, task in enumerate(tasks, 1):
        question = task["question"]
        expected = {"expected_sql": task["expected_sql"]}
        print(f"[{i}/{len(tasks)}] {question[:70]}...")

        result = run_sql_gen_task(
            task={
                "question": question,
                "db_schema_desc": task["db_schema_desc"],
            },
            db_path=_DB_PATH,
            expected=expected,
        )

        score = result.get("scores", {})
        sql_score = score.get("sql_correctness", "n/a") if isinstance(score, dict) else "n/a"
        print(f"         sql_correctness={sql_score}  iterations={result.get('iterations')}\n")

    print("Done. Open Braintrust → sema4-demo → Logs to view scored traces.")


if __name__ == "__main__":
    main()
