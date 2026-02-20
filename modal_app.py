"""
Modal app: serves the Braintrust remote eval dev server as a public HTTPS endpoint.

This is the "customer VPC" analog — the SQL gen agent runs here (inside Modal),
while Braintrust orchestrates and collects results.

Deploy:
    uv run modal serve modal_app.py   # ephemeral (stops when terminal closes)
    uv run modal deploy modal_app.py  # persistent

Query the live DB from your laptop:
    uv run modal run modal_app.py --sql "SELECT * FROM customers"

Then register the printed HTTPS URL in Braintrust Playground.

Prerequisites:
    uv run modal token new   # one-time: authenticate with Modal
    # Create a Modal secret named "sema4-demo-secrets" with:
    #   BRAINTRUST_API_KEY=...
    #   OPENAI_API_KEY=...
"""

import sys

import modal

app = modal.App("sema4-braintrust-eval")

# Persistent volume — DB lives here across container restarts.
# Both eval_server and query mount it at /data so they share state.
db_volume = modal.Volume.from_name("sema4-demo-db", create_if_missing=True)
DB_PATH = "/data/sema4_demo.db"

# Image layer: only apt + pip — never changes with code edits, stays cached.
# add_local_dir without copy=True mounts code at container startup instead of
# baking it into the image, so redeploys are fast.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .run_commands("apt-get install -y sqlite3")
    .pip_install(
        "braintrust[cli]>=0.0.172",
        "autoevals",
        "openai>=1.0",
        "python-dotenv",
    )
    .add_local_dir(".", remote_path="/app")
)

DEV_HOST = "0.0.0.0"
DEV_PORT = 8300


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("sema4-demo-secrets")],
    volumes={"/data": db_volume},
    timeout=600,
    cpu=2,
    min_containers=1,
)
@modal.web_server(DEV_PORT, startup_timeout=120)
def eval_server():
    """
    Run `braintrust eval --dev` inside Modal.

    Braintrust connects to this endpoint from the Playground UI to execute
    eval tasks remotely — the agent stays in this environment (the "VPC"),
    results flow back to Braintrust.
    """
    import subprocess

    # Seed the DB on the shared volume so query() can also read it.
    sys.path.insert(0, "/app")
    from data.sql_tasks import setup_db
    print(f"[eval_server] seeding database at {DB_PATH}", flush=True)
    setup_db(DB_PATH)
    print("[eval_server] database ready — starting braintrust dev server", flush=True)

    subprocess.Popen(
        [
            "braintrust", "eval",
            "evals/sql_gen.eval.py",
            "--dev",
            f"--dev-host={DEV_HOST}",
            f"--dev-port={DEV_PORT}",
        ],
        env={**__import__("os").environ, "SEMA4_DB_PATH": DB_PATH},
        cwd="/app",
    )


@app.function(
    image=image,
    volumes={"/data": db_volume},
)
def query(sql: str) -> str:
    """Run a SQL query against the shared telecom demo database and return results."""
    import sqlite3
    import os

    sys.path.insert(0, "/app")
    from data.sql_tasks import setup_db

    # Seed if the volume is fresh (first run before eval_server has fired).
    if not os.path.exists(DB_PATH):
        print(f"[query] DB not found — seeding at {DB_PATH}", flush=True)
        setup_db(DB_PATH)

    print(f"[query] running: {sql}", flush=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql).fetchall()
        lines = ["\t".join(str(v) for v in row) for row in rows]
        result = "\n".join(lines) if lines else "(no rows)"
        print(f"[query] returned {len(rows)} row(s)", flush=True)
        return result
    except Exception as e:
        print(f"[query] error: {e}", flush=True)
        return f"Error: {e}"
    finally:
        conn.close()


@app.local_entrypoint()
def run_query(sql: str = "SELECT id, name, status, data_used_gb FROM customers ORDER BY data_used_gb DESC"):
    """
    Query the live Modal database from your laptop.

    Usage:
        uv run modal run modal_app.py --sql "SELECT * FROM plans"
    """
    print(f"\nQuerying remote DB: {sql}\n")
    result = query.remote(sql)
    print(result)
