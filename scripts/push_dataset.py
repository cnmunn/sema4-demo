"""
Push the 12 SQL gen tasks to Braintrust as a named dataset.

Creates / upserts "SQL Gen Tasks" in project "sema4-demo".
Each row:
  input    = { question, db_schema_desc }
  expected = { expected_sql }
  metadata = { task_id }

Run:
    uv run python scripts/push_dataset.py
"""

import os
import sys
from pathlib import Path

import braintrust
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.sql_tasks import TASKS

PROJECT = "sema4-demo"
DATASET_NAME = "SQL Gen Tasks"


def main() -> None:
    if not os.environ.get("BRAINTRUST_API_KEY"):
        print("Error: BRAINTRUST_API_KEY not set.")
        sys.exit(1)

    print(f"Pushing {len(TASKS)} tasks → dataset '{DATASET_NAME}'...")

    dataset = braintrust.init_dataset(project=PROJECT, name=DATASET_NAME)

    for task in TASKS:
        dataset.insert(
            id=task["id"],
            input={
                "question": task["question"],
                "db_schema_desc": task["db_schema_desc"],
            },
            expected={
                "expected_sql": task["expected_sql"],
            },
            metadata={
                "task_id": task["id"],
            },
        )

    dataset.flush()
    print(f"Done — {len(TASKS)} rows upserted into '{DATASET_NAME}'.")


if __name__ == "__main__":
    main()
