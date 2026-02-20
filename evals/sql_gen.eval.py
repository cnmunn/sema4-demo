"""
Braintrust Eval for the sema4-demo SQL gen agent.

Run locally:
    uv run braintrust eval evals/sql_gen.eval.py

Run from Playground (after registering Modal URL):
    Open Braintrust UI → Playground → Sema4 SQL Gen → Run
"""

import os
import sys
from pathlib import Path

import braintrust
from autoevals import Score
from braintrust import Eval
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.agent import run_sql_gen_task
from data.sql_tasks import DB_SCHEMA_DESC, setup_db
from evals.scorers import sql_correctness

# ---------------------------------------------------------------------------
# Database setup — shared across all tasks in this eval run
# ---------------------------------------------------------------------------

_DB_PATH = os.environ.get("SEMA4_DB_PATH", "/tmp/sema4_eval.db")
setup_db(_DB_PATH)


# ---------------------------------------------------------------------------
# Task wrapper
# ---------------------------------------------------------------------------


def sql_gen_task(input: dict, hooks=None) -> dict:
    """Run the SQL gen agent on a single eval task.

    When called from the Playground, hooks.parameters carries the user-selected
    prompt (system message + model).  Falls back to defaults when running locally.
    """
    model = None
    system_prompt_override = None

    if hooks is not None:
        params = hooks.parameters or {}
        prompt_param = params.get("system_prompt")
        if prompt_param is not None:
            schema = input.get("db_schema_desc", DB_SCHEMA_DESC)
            built = prompt_param.build(db_path=_DB_PATH, schema=schema)
            # Extract model from built kwargs
            model = built.get("model")
            # Extract the rendered system message content
            system_prompt_override = next(
                (m["content"] for m in built.get("messages", []) if m["role"] == "system"),
                None,
            )

    return run_sql_gen_task(
        task=input,
        db_path=_DB_PATH,
        model=model,
        system_prompt_override=system_prompt_override,
    )


# ---------------------------------------------------------------------------
# Scorers
# ---------------------------------------------------------------------------


def sql_correctness_scorer(output, expected, **kwargs) -> Score:
    """Structural SQL similarity score (0–1)."""
    return Score(name="sql_correctness", score=sql_correctness(output, expected, **kwargs))


def correct(output, expected, **kwargs) -> Score:
    """Binary pass/fail — 1.0 if sql_correctness >= 0.8, else 0.0."""
    score = sql_correctness(output, expected, **kwargs)
    return Score(name="correct", score=1.0 if score >= 0.8 else 0.0)


# ---------------------------------------------------------------------------
# Eval — pulls from the user-curated dataset (created from project logs).
# Input rows have shape: {question, db_schema_desc, ...} nested under "input".
# experiment_name can be overridden via EXPERIMENT_NAME env var.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Default system prompt template for the Playground prompt parameter.
# Uses {{db_path}} and {{schema}} as Braintrust template variables so users
# can see and edit the full prompt in the Playground before running.
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_PROMPT = """\
You are an expert SQL engineer working with a SQLite database. Your job is to write
correct SQL queries that answer natural language questions about customer data.

## Workflow

1. **Think** about the question and identify the relevant tables and joins.
2. **Write** your SQL query to a temp file: `/tmp/sema4_query.sql`
3. **Execute** it with bash: `sqlite3 {{db_path}} < /tmp/sema4_query.sql`
4. **Inspect** the results. If there's an error or the results look wrong, fix and retry.
5. **Return** your final answer once you have correct results.

## Database Schema

{{schema}}

## Guidelines

- Always use explicit JOINs (not implicit comma joins).
- Prefer `ROUND()` for monetary values.
- Use `ORDER BY` to make results deterministic.
- If a question is ambiguous, pick the most natural interpretation.
- After executing, show the query results in your final response.
- Output ONLY valid SQL — no markdown fences in the .sql file.\
"""

Eval(
    "sema4-demo",
    experiment_name=os.environ.get("EXPERIMENT_NAME"),
    data=lambda: [
        {
            "input": {
                "question": row["input"]["question"],
                "db_schema_desc": row["input"]["task"]["db_schema_desc"],
            },
            "expected": row["expected"],  # {expected_sql}
        }
        for row in braintrust.init_dataset(
            project="sema4-demo",
            name="Dataset-a4389fab",
        )
    ],
    task=sql_gen_task,
    scores=[sql_correctness_scorer, correct],
    metadata={
        "model": "gpt-4o",
        "description": "SQL gen agent: GPT-4o + bash/file tools on SQLite telecom DB",
    },
    parameters={
        "system_prompt": {
            "type": "prompt",
            "name": "System prompt",
            "description": "Agent system prompt. Change this or swap the model to compare eval runs side-by-side.",
            "default": {
                "prompt": {
                    "type": "chat",
                    "messages": [
                        {"role": "system", "content": _DEFAULT_SYSTEM_PROMPT},
                    ],
                },
                "options": {"model": "gpt-4o"},
            },
        },
    },
)
