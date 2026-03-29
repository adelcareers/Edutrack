#!/usr/bin/env python3
"""
Script to:
1. Configure Status columns on the EduTrack GitHub Projects board
   (renames "Todo"→"Backlog", keeps "In Progress"/"Done", adds "In Analysis"/"In Review")
2. Add all 40 issues (#2 through #41) to the project
3. Set all issues to Backlog status
"""
import json
import os
import subprocess
import sys
import tempfile

REPO = "adelcareers/Edutrack"
PROJECT_ID = "PVT_kwHOC5bZZM4BRJDe"
PROJECT_NUM = 6
STATUS_FIELD_ID = "PVTSSF_lAHOC5bZZM4BRJDezg_Dkn4"

# Existing option IDs retrieved from gh project field-list 6:
#   f75ad846 → "Todo"   (will rename to "Backlog")
#   47fc9ee4 → "In Progress"
#   98236657 → "Done"
EXISTING_TODO_ID = "f75ad846"
EXISTING_IN_PROGRESS_ID = "47fc9ee4"
EXISTING_DONE_ID = "98236657"


def run_graphql(query, variables=None):
    """Execute a GraphQL query via gh, passing variables as typed JSON (supports int, bool, arrays)."""
    body = json.dumps({"query": query, "variables": variables or {}})
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(body)
        fname = f.name
    try:
        cmd = ["gh", "api", "graphql", "--input", fname]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  GraphQL error: {result.stderr[:300]}", file=sys.stderr)
            return None
        return json.loads(result.stdout)
    finally:
        os.unlink(fname)


def setup_status_field():
    """Replace/update the Status single-select field to have the 5 desired columns."""
    # projectId is NOT accepted by updateProjectV2Field — only fieldId is required.
    # Existing IDs make GitHub rename rather than delete; omitting ID creates a new option.
    query = """
mutation($fieldId: ID!, $opts: [ProjectV2SingleSelectFieldOptionInput!]!) {
  updateProjectV2Field(input: {
    fieldId: $fieldId
    singleSelectOptions: $opts
  }) {
    projectV2Field {
      ... on ProjectV2SingleSelectField {
        id
        options { id name color }
      }
    }
  }
}"""
    variables = {
        "fieldId": STATUS_FIELD_ID,
        "opts": [
            {"name": "Backlog", "color": "BLUE", "description": ""},
            {"name": "In Analysis", "color": "PURPLE", "description": ""},
            {"name": "In Progress", "color": "YELLOW", "description": ""},
            {"name": "In Review", "color": "ORANGE", "description": ""},
            {"name": "Done", "color": "GREEN", "description": ""},
        ],
    }
    data = run_graphql(query, variables)
    if data and "data" in data:
        field = data["data"]["updateProjectV2Field"]["projectV2Field"]
        options = field["options"]
        print("  Field options after update:")
        for opt in options:
            print(f"    {opt['id']}  {opt['color']:8s}  {opt['name']}")
        return {opt["name"]: opt["id"] for opt in options}
    return {}


def add_issue_to_project(issue_number):
    """Look up issue node ID by number, then add it to the project."""
    query = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) { id }
  }
}"""
    data = run_graphql(
        query, {"owner": "adelcareers", "repo": "Edutrack", "number": issue_number}
    )
    if not data:
        return None
    try:
        node_id = data["data"]["repository"]["issue"]["id"]
    except (KeyError, TypeError):
        print(f"  Issue #{issue_number} not found or parse error", file=sys.stderr)
        return None

    mutate = """
mutation($projectId: ID!, $contentId: ID!) {
  addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
    item { id }
  }
}"""
    result = run_graphql(mutate, {"projectId": PROJECT_ID, "contentId": node_id})
    if result and "data" in result:
        return result["data"]["addProjectV2ItemById"]["item"]["id"]
    return None


def set_status(item_id, option_id):
    mutate = """
mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $projectId
    itemId: $itemId
    fieldId: $fieldId
    value: { singleSelectOptionId: $optionId }
  }) {
    projectV2Item { id }
  }
}"""
    result = run_graphql(
        mutate,
        {
            "projectId": PROJECT_ID,
            "itemId": item_id,
            "fieldId": STATUS_FIELD_ID,
            "optionId": option_id,
        },
    )
    return result is not None


def list_project_items():
    """Return list of {id, content_number} for all items in the project (paginates)."""
    query = """
query($projectId: ID!, $cursor: String) {
  node(id: $projectId) {
    ... on ProjectV2 {
      items(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          content { ... on Issue { number } }
        }
      }
    }
  }
}"""
    items = []
    cursor = None
    while True:
        variables = {"projectId": PROJECT_ID}
        if cursor:
            variables["cursor"] = cursor
        data = run_graphql(query, variables)
        if not data:
            break
        page = data["data"]["node"]["items"]
        for node in page["nodes"]:
            content = node.get("content") or {}
            items.append({"id": node["id"], "number": content.get("number")})
        if page["pageInfo"]["hasNextPage"]:
            cursor = page["pageInfo"]["endCursor"]
        else:
            break
    return items


def main():
    # Step 1: Configure status columns
    print("Step 1: Configuring Status columns...")
    option_map = setup_status_field()
    backlog_id = option_map.get("Backlog")
    if backlog_id:
        print(f"  Backlog option ID: {backlog_id}")
    else:
        print("ERROR: Backlog option not found — cannot set statuses")
        return

    # Step 2: Set all 40 project items to Backlog
    print("\nStep 2: Setting all project items to 'Backlog' status...")
    items = list_project_items()
    print(f"  Found {len(items)} items in project")
    success = 0
    failed = []
    for item in items:
        ok = set_status(item["id"], backlog_id)
        num = item.get("number", "?")
        if ok:
            print(f"  #{num}: ✓ Backlog")
            success += 1
        else:
            print(f"  #{num}: FAILED to set status")
            failed.append(num)

    print(f"\nDone! {success}/{len(items)} items set to Backlog.")
    if failed:
        print(f"Failed: {failed}")


if __name__ == "__main__":
    main()
