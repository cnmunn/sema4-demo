# sema4-demo

Demo for Sema4.ai showing how Braintrust closes the loop on agent iteration.
Three acts:

1. **Tau bench trace ingestion** → Braintrust experiments (model comparison)
2. **"2026-style" SQL gen agent** — Claude + bash/file tools, fully traced
3. **Remote eval**: Braintrust Playground → Modal → results back to Braintrust

---

## Setup

### 1. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Install dependencies

```bash
cd sema4-demo
uv sync
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in:
#   BRAINTRUST_API_KEY=  (from braintrust.dev → Settings → API Keys)
#   OPENAI_API_KEY=      (from platform.openai.com)
```

---

## Demo Flow

### Act 1: Tau bench traces → Braintrust

```bash
uv run python scripts/upload_traces.py
```

Opens two experiments side-by-side in Braintrust:
- `gpt-5-medium` — 114 tasks, 456 simulations
- `gpt-5.1-codex-max-medium` — 114 tasks, 456 simulations

Each row shows `reward`, `pass_exp_k`, and `pass_at_k` scores.
Filter, sort, and compare which tasks regressed or improved between models.

**Narrative**: *"Everything you're tracking in Excel, now in Braintrust. Every task is tagged,
you can see which ones regressed, filter by domain, and compare models over time."*

---

### Act 2: "2026-style" agent — file system + code execution

```bash
uv run python agent/agent.py "Which customers exceeded their plan's data limit last month?"
```

Then open the Braintrust project logs URL printed by the script. You'll see:

```
run_sql_gen_task                   ← parent span
  ├── write_file /tmp/query.sql    ← child span (SQL written to disk)
  ├── bash_exec sqlite3 ...        ← child span (command + stdout)
  └── bash_exec (retry, if needed) ← child span
```

**Narrative**: *"The agent writes code to disk and runs terminal commands. Every file write,
every bash command, every output is a span you can inspect."*

---

### Act 3: Remote eval on Modal (customer VPC)

**Step 1**: Deploy the eval server to Modal:

```bash
# One-time: authenticate
uv run modal token new

# Create Modal secret with your API keys:
# modal.com → Secrets → Create → name it "sema4-demo-secrets"
# Add: BRAINTRUST_API_KEY and OPENAI_API_KEY

# Serve (ephemeral):
uv run modal serve modal_app.py
# → prints: https://your-org--sema4-braintrust-eval-eval-server.modal.run
```

**Step 2**: Register in Braintrust Playground:
- Open Braintrust UI → Playground → select project `sema4-demo`
- Settings → Remote Eval URL → paste the Modal HTTPS URL
- Select eval `Sema4 SQL Gen`

**Step 3**: Run from UI:
- Swap the model in the dropdown
- Click **Run**
- Watch results stream in from Modal

**Narrative**: *"The agent runs in your infra — or a customer's VPC. Braintrust orchestrates
and collects results. You iterate on prompts and scoring here; the agent stays in your environment."*

---

## Run eval locally

```bash
uv run braintrust eval evals/sql_gen.eval.py
```

Runs all 12 SQL gen tasks, scores with `sql_correctness` and `pass_exp_k`.

---

## Project structure

```
sema4-demo/
├── pyproject.toml              # uv-managed dependencies
├── .env.example                # API key template
├── example-traces/             # Tau bench JSON traces (provided)
│   ├── gpt5_medium.json
│   └── gpt51cm_azure_medium.json
├── scripts/
│   └── upload_traces.py        # Ingest traces → BT dataset + experiments
├── agent/
│   ├── agent.py                # Claude agentic loop (run_sql_gen_task)
│   ├── tools.py                # bash_exec, read_file, write_file, list_dir
│   └── system_prompt.py        # System prompt for the SQL gen agent
├── evals/
│   ├── sql_gen.eval.py         # Braintrust Eval()
│   └── scorers.py              # pass_at_k, pass_exp_k, sql_correctness
├── data/
│   └── sql_tasks.py            # 12 Bird-Bench-style NL→SQL tasks + DB setup
└── modal_app.py                # Modal web server for remote eval
```
