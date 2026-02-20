"""
2026-style SQL generation agent.

GPT-4o + bash/file tools, fully traced in Braintrust.

Trace structure visible in BT:
  run_sql_gen_task                ← root span: input=question, output={sql, result}
    ├── gpt-4o [LLM]             ← wrap_openai: shows messages, tool calls, tokens
    ├── write_file [tool]        ← @traced: input=path+content, output=confirmation
    ├── bash_exec [tool]         ← @traced: input=cmd, output=stdout
    ├── gpt-4o [LLM]             ← next iteration: evaluates result
    └── ...

Entry point: run_sql_gen_task(task, db_path, max_retries=3) -> dict
CLI:         uv run python agent/agent.py "Which customers exceeded their plan's data limit?"
"""

import json
import os
import sys
from pathlib import Path

from braintrust import current_span, traced, wrap_openai
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Add project root to path for relative imports when run as script
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.system_prompt import get_system_prompt
from agent.tools import TOOL_DEFINITIONS, TOOL_MAP
from data.sql_tasks import DB_SCHEMA_DESC

MODEL = "gpt-4o"
MAX_TOKENS = 4096


@traced
def run_sql_gen_task(
    task: dict,
    db_path: str = "/tmp/sema4_demo.db",
    max_retries: int = 3,
    expected: dict = None,
    model: str = None,
    system_prompt_override: str = None,
) -> dict:
    """
    Run the SQL generation agent on a single task.

    Args:
        task: Dict with keys: id, question, db_schema_desc
        db_path: Path to the SQLite database
        max_retries: Maximum agentic iterations
        expected: Optional dict with expected_sql; if provided, scores are logged to the span

    Returns:
        Dict with: sql, result, iterations, error (optional)
    """
    # wrap_openai makes every client.chat.completions.create() call
    # show up as an LLM child span with model, messages, token counts
    client = wrap_openai(OpenAI(api_key=os.environ["OPENAI_API_KEY"]))

    question = task.get("question", task) if isinstance(task, dict) else str(task)
    schema = task.get("db_schema_desc", DB_SCHEMA_DESC) if isinstance(task, dict) else DB_SCHEMA_DESC

    # Log the question as input on the root span so it's visible in BT
    _model = model or MODEL
    current_span().log(input={"question": question, "db_path": db_path})

    system = system_prompt_override if system_prompt_override else get_system_prompt(db_path=db_path, schema=schema)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]

    last_sql = ""
    last_result = ""
    iterations = 0

    for iteration in range(max_retries + 1):
        iterations = iteration + 1

        # This call is now automatically traced as an LLM span by wrap_openai
        response = client.chat.completions.create(
            model=_model,
            max_tokens=MAX_TOKENS,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        message = response.choices[0].message
        tool_calls = message.tool_calls or []

        # Append assistant turn (serialize tool_calls for message history)
        assistant_msg = {"role": "assistant", "content": message.content}
        if tool_calls:
            assistant_msg["tool_calls"] = [tc.model_dump() for tc in tool_calls]
        messages.append(assistant_msg)

        # If no tool calls, agent is done — log final output to root span
        if not tool_calls:
            result = {
                "sql": last_sql,
                "result": last_result,
                "final_response": message.content or "",
                "iterations": iterations,
            }
            span_kwargs = {"output": result, "metadata": {"iterations": iterations, "model": _model}}
            if expected is not None:
                from evals.scorers import sql_correctness
                score = sql_correctness(result, expected)
                span_kwargs["expected"] = expected
                span_kwargs["scores"] = {
                    "sql_correctness": score,
                    "pass_exp_k": 1.0 if score >= 0.8 else 0.0,
                }
            current_span().log(**span_kwargs)
            return result

        # Dispatch each tool call and append results
        for tc in tool_calls:
            tool_name = tc.function.name
            tool_input = json.loads(tc.function.arguments)
            tool_fn = TOOL_MAP.get(tool_name)

            if tool_fn is None:
                result = f"Error: unknown tool {tool_name}"
            else:
                try:
                    raw = tool_fn(**tool_input)
                    result = str(raw) if not isinstance(raw, str) else raw
                except Exception as e:
                    result = f"Error: {e}"

            # Track the SQL written and the sqlite3 output
            if tool_name == "write_file" and tool_input.get("path", "").endswith(".sql"):
                last_sql = tool_input.get("content", "")
            elif tool_name == "bash_exec" and "sqlite3" in tool_input.get("cmd", ""):
                last_result = result

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    # Hit max iterations
    result = {
        "sql": last_sql,
        "result": last_result,
        "final_response": "Max iterations reached",
        "iterations": iterations,
        "error": "max_iterations_exceeded",
    }
    span_kwargs = {"output": result, "metadata": {"iterations": iterations, "model": MODEL}}
    if expected is not None:
        from evals.scorers import sql_correctness
        score = sql_correctness(result, expected)
        span_kwargs["expected"] = expected
        span_kwargs["scores"] = {
            "sql_correctness": score,
            "pass_exp_k": 1.0 if score >= 0.8 else 0.0,
        }
    current_span().log(**span_kwargs)
    return result


if __name__ == "__main__":
    import tempfile

    import braintrust

    from data.sql_tasks import setup_db

    if len(sys.argv) < 2:
        print("Usage: uv run python agent/agent.py '<question>'")
        sys.exit(1)

    question = " ".join(sys.argv[1:])

    # Set up a temp DB with demo data
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    setup_db(db_path)
    print(f"Demo DB: {db_path}")
    print(f"Question: {question}\n")

    # init_logger routes @traced spans to the project Logs tab
    braintrust.init_logger(project="sema4-demo")

    result = run_sql_gen_task(
        task={"question": question, "db_schema_desc": DB_SCHEMA_DESC},
        db_path=db_path,
    )

    print("=" * 60)
    print("SQL:")
    print(result.get("sql", "(none)"))
    print("\nResult:")
    print(result.get("result", "(none)"))
    print(f"\nIterations: {result.get('iterations')}")
    if result.get("error"):
        print(f"Error: {result['error']}")
