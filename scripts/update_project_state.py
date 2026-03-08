#!/usr/bin/env python3
"""Small helper to update the PROJECT_STATE block inside AGENT_DELIVERY_PLAN.md.

Usage:
  python scripts/update_project_state.py [--commit]

If --commit is provided the script will run `git add` and commit the updated file.
"""

from __future__ import annotations
import re
import sys
from datetime import date
import subprocess

try:
    import yaml
except Exception:
    print("PyYAML is required. Install with: pip install PyYAML")
    sys.exit(1)

PLAN_PATH = "AGENT_DELIVERY_PLAN.md"

YAML_BLOCK_RE = re.compile(r"```yaml\n(.*?)\n```", re.DOTALL)


def load_plan_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_plan_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def find_project_state_yaml(text: str) -> tuple[int, int, str] | None:
    # Locate the PROJECT STATE section and return the YAML block
    idx = text.find("## PROJECT STATE")
    if idx == -1:
        return None
    # Search for the first fenced yaml block after this index
    m = YAML_BLOCK_RE.search(text[idx:])
    if not m:
        return None
    start = idx + m.start()
    end = idx + m.end()
    return start, end, m.group(1)


def update_last_updated(yaml_text: str) -> str:
    data = yaml.safe_load(yaml_text)
    if not isinstance(data, dict):
        raise RuntimeError("PROJECT_STATE YAML did not parse as a mapping")
    data["last_updated"] = date.today().isoformat()
    return yaml.safe_dump(data, sort_keys=False)


def main():
    text = load_plan_text(PLAN_PATH)
    found = find_project_state_yaml(text)
    if not found:
        print("Could not find PROJECT_STATE YAML block in AGENT_DELIVERY_PLAN.md")
        sys.exit(1)
    start, end, yaml_text = found
    new_yaml = update_last_updated(yaml_text)
    # Replace the fenced block content while preserving the triple backticks and surrounding spacing
    new_block = "```yaml\n" + new_yaml.strip() + "\n```"
    new_text = text[:start] + new_block + text[end:]
    write_plan_text(PLAN_PATH, new_text)
    print(f"Updated last_updated in {PLAN_PATH} to today's date.")

    if "--commit" in sys.argv:
        subprocess.run(["git", "add", PLAN_PATH], check=False)
        subprocess.run(["git", "commit", "-m", "chore: update PROJECT_STATE last_updated"], check=False)
        print("Committed changes (if git configured).")


if __name__ == "__main__":
    main()
