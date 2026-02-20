"""2026-style tools: bash, file I/O — each traced as a 'tool' span in Braintrust."""

import subprocess
from pathlib import Path

from braintrust import start_span

# ---------------------------------------------------------------------------
# Tool implementations — each uses start_span(type="tool") so BT renders
# them with the tool icon and shows input/output clearly
# ---------------------------------------------------------------------------


def bash_exec(cmd: str) -> str:
    """Run a shell command and return stdout + stderr."""
    with start_span(name="bash_exec", type="tool", input={"cmd": cmd}) as span:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = proc.stdout
        if proc.stderr:
            output += "\n[stderr]\n" + proc.stderr
        span.log(output=output)
        return output


def read_file(path: str) -> str:
    """Read a file and return its contents as a string."""
    with start_span(name="read_file", type="tool", input={"path": path}) as span:
        content = Path(path).read_text()
        span.log(output=content)
        return content


def write_file(path: str, content: str) -> str:
    """Write content to a file. Creates parent directories as needed."""
    with start_span(name="write_file", type="tool", input={"path": path, "content": content}) as span:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        msg = f"Wrote {len(content)} bytes to {path}"
        span.log(output=msg)
        return msg


def list_dir(path: str) -> list[str]:
    """List files and directories at the given path."""
    with start_span(name="list_dir", type="tool", input={"path": path}) as span:
        entries = [str(p) for p in sorted(Path(path).iterdir())]
        span.log(output=entries)
        return entries


# ---------------------------------------------------------------------------
# OpenAI tool schema definitions
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "bash_exec",
            "description": (
                "Execute a shell command and return its stdout + stderr. "
                "Use this to run sqlite3 queries, check files, or inspect results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    }
                },
                "required": ["cmd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file, creating parent directories as needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path where the file should be written.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories at a given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list.",
                    }
                },
                "required": ["path"],
            },
        },
    },
]

TOOL_MAP = {
    "bash_exec": bash_exec,
    "read_file": read_file,
    "write_file": write_file,
    "list_dir": list_dir,
}
