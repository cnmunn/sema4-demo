"""
Push the SQL gen agent system prompt to Braintrust as a named Prompt.

After running this, go to:
  braintrust.dev/app → sema4-demo → Prompts → "SQL Gen Agent"
  Then open Playground → select the prompt → iterate on it live.

Run:
    uv run python scripts/push_prompt.py
"""

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent.system_prompt import SYSTEM_PROMPT

BRAINTRUST_API_URL = "https://api.braintrust.dev/v1"
PROJECT_NAME = "sema4-demo"
PROMPT_NAME = "SQL Gen Agent"


def push_prompt() -> None:
    api_key = os.environ.get("BRAINTRUST_API_KEY")
    if not api_key:
        print("Error: BRAINTRUST_API_KEY not set")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Look up the project ID
    resp = requests.get(
        f"{BRAINTRUST_API_URL}/project",
        headers=headers,
        params={"project_name": PROJECT_NAME},
    )
    resp.raise_for_status()
    projects = resp.json().get("objects", [])
    if not projects:
        print(f"Project '{PROJECT_NAME}' not found. Run upload_traces.py first.")
        sys.exit(1)
    project_id = projects[0]["id"]
    print(f"Project: {PROJECT_NAME} ({project_id})")

    # Build the prompt payload — system message + user message placeholder
    prompt_data = {
        "name": PROMPT_NAME,
        "project_id": project_id,
        "prompt_data": {
            "prompt": {
                "type": "chat",
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": "{{question}}",
                    },
                ],
            },
            "options": {
                "model": "gpt-4o",
                "params": {
                    "max_tokens": 4096,
                },
            },
        },
        "description": "System prompt for the SQL gen agent. Edit in Playground to iterate.",
        "tags": ["sql-gen", "agent", "demo"],
    }

    # Upsert (create or update) the prompt
    resp = requests.post(
        f"{BRAINTRUST_API_URL}/prompt",
        headers=headers,
        json=prompt_data,
    )

    if resp.status_code in (200, 201):
        prompt = resp.json()
        print(f"Prompt '{PROMPT_NAME}' pushed successfully.")
        print(f"  Prompt ID: {prompt.get('id')}")
        print(f"\nOpen Playground:")
        print(f"  https://www.braintrust.dev/app/p/{PROJECT_NAME}/prompts/{PROMPT_NAME}")
    else:
        print(f"Error {resp.status_code}: {resp.text}")
        sys.exit(1)


if __name__ == "__main__":
    push_prompt()
