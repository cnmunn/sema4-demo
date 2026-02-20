# sema4-demo: Architecture Reference

## Purpose

Demo for Aaron Yim (Sema4.ai CPO) showing three Braintrust capabilities:
1. Tau bench trace ingestion → experiments (model comparison UI)
2. "2026-style" agent (GPT-4o + bash/file tools) with full Braintrust tracing
3. Remote eval: Braintrust Playground → Modal → results back to BT

## Key files

| File | Purpose |
|---|---|
| `scripts/upload_traces.py` | Parses `example-traces/*.json`, upserts Dataset + two Experiments |
| `scripts/push_dataset.py` | Pushes 12 SQL tasks as "SQL Gen Tasks" dataset to Braintrust |
| `scripts/push_prompt.py` | Upserts system prompt to Braintrust Prompts |
| `agent/agent.py` | GPT-4o agentic loop; entry: `run_sql_gen_task(task, db_path, max_retries=3)` |
| `agent/tools.py` | `bash_exec`, `read_file`, `write_file`, `list_dir` — each `@traced` |
| `agent/system_prompt.py` | System prompt template (injected with db_path + schema) |
| `data/sql_tasks.py` | 12 NL→SQL tasks + `setup_db(path)` for SQLite seeding |
| `evals/scorers.py` | `pass_at_k`, `pass_exp_k`, `sql_correctness` |
| `evals/sql_gen.eval.py` | `Eval("sema4-demo", ...)` — pulls from "SQL Gen Tasks" dataset |
| `modal_app.py` | Modal app: `eval_server` runs `braintrust eval --dev` on port 8300 |

## Braintrust objects created

- **Project**: `sema4-demo`
- **Dataset**: `Tau Bench Telecom Tasks` (114 tasks from tau bench trace files)
- **Dataset**: `SQL Gen Tasks` (12 NL→SQL tasks for the agent eval)
- **Experiments**: `gpt-5-medium`, `gpt-5.1-codex-max-medium` (one per trace file)
- **Eval**: runs against `sema4-demo` project, experiment name auto-generated per run
- **Project logs**: traces from `agent/agent.py` runs

## Trace schema (tau bench)

```
simulations[i]:
  task_id, trial, reward_info.reward (0.0/1.0),
  messages, duration, agent_cost,
  termination_reason, start_time, end_time

tasks[i]:
  id, description, user_scenario, ticket,
  initial_state, evaluation_criteria.{actions, env_assertions, ...}
```

## Metrics

- `reward`: raw pass/fail from tau bench (0.0 or 1.0)
- `pass_at_k`: mean reward across K trials per task
- `pass_exp_k`: 1.0 only if ALL K trials pass (Sierra consistency metric)

## SQLite demo schema

```sql
plans(id, name, data_limit_gb, price)
customers(id, name, plan_id, monthly_spend, status, data_used_gb)
transactions(id, customer_id, amount, date, type)
```

Seeded via `data/sql_tasks.setup_db(path)`.

## Commands

```bash
uv sync                                         # install deps

# Act 1: ingest tau bench traces → BT experiments
uv run python scripts/upload_traces.py

# Act 1b: push SQL eval dataset + prompt to BT
uv run python scripts/push_dataset.py
uv run python scripts/push_prompt.py

# Act 2: run agent directly (traces to BT project logs)
uv run python agent/agent.py "<question>"

# Act 3: eval locally
uv run braintrust eval evals/sql_gen.eval.py

# Act 3: eval remotely via Modal
uv run modal token new                          # one-time auth
uv run modal serve modal_app.py                 # ephemeral (stops on Ctrl+C)
uv run modal deploy modal_app.py                # persistent deployment
```

## Modal + Braintrust remote eval setup

1. Create Modal secret named **`sema4-demo-secrets`** with:
   - `BRAINTRUST_API_KEY`
   - `OPENAI_API_KEY`
2. Run `uv run modal serve modal_app.py` → copy the printed HTTPS URL
3. In Braintrust UI: Playground → connect remote evaluator → paste URL
4. The Modal container runs `braintrust eval --dev` on port 8300; BT proxies requests to it

## Environment variables

```
BRAINTRUST_API_KEY   # braintrust.dev → Settings → API Keys
OPENAI_API_KEY       # platform.openai.com
SEMA4_DB_PATH        # optional override for SQLite path (default: /tmp/sema4_eval.db)
```
