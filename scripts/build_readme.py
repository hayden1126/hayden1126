"""Refresh the auto-updating region of README.md from primary sources.

Pulls the user's most recently pushed public repos via the GitHub GraphQL API and
rewrites the `active` marker block. Repos already featured in the curated sections
are excluded so nothing appears twice on the page. Standard library only (no pip
dependencies), so nothing can break in CI. Deterministic: stable ordering, no run
timestamps, and the file is only rewritten when the rendered content actually changes.
"""

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
LOGIN = "hayden1126"
GRAPHQL_URL = "https://api.github.com/graphql"
MAX_ACTIVE = 6
# Kept out of the live list: the profile repo itself, repos already curated above
# (DocAgent, sourced), a redundant submission snapshot (PaperRec-submission duplicates
# PaperRec), and puzzle/coursework throwaways.
EXCLUDE = {
    LOGIN,
    "DocAgent",
    "sourced",
    "PaperRec-submission",
    "adventofcode2022",
    "adventofcode2023",
    "adventofcode2025",
    "AdventOfCodeSchool",
    "hackathonproblems",
}

QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(first: 100, privacy: PUBLIC, isFork: false,
                 ownerAffiliations: [OWNER],
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        name
        url
        description
        pushedAt
        primaryLanguage { name }
      }
    }
  }
}
"""


def fetch_repos(token: str) -> list[dict]:
    """Return the user's public source repos, most recently pushed first."""
    payload = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{LOGIN}-readme-bot",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    if "errors" in body:
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    return body["data"]["user"]["repositories"]["nodes"]


def render_active(repos: list[dict]) -> str:
    """Recently pushed repos, excluding those curated elsewhere on the page."""
    lines = []
    for repo in repos:
        # A repo earns a spot only if it is not excluded and carries a description;
        # bare repos stay hidden until they get one.
        if repo["name"] in EXCLUDE or not repo["description"]:
            continue
        parts = [f"**[{repo['name']}]({repo['url']})**"]
        if repo["primaryLanguage"]:
            parts.append(f"`{repo['primaryLanguage']['name']}`")
        parts.append(repo["description"].strip().replace("\n", " "))
        parts.append(repo["pushedAt"][:10])
        lines.append("- " + " &middot; ".join(parts))
        if len(lines) == MAX_ACTIVE:
            break
    return "\n".join(lines)


def replace_chunk(content: str, marker: str, chunk: str) -> str:
    """Swap the text between the marker comments, leaving the rest untouched."""
    pattern = re.compile(
        rf"(<!-- {marker}:start -->)(.*)(<!-- {marker}:end -->)", re.DOTALL
    )
    return pattern.sub(lambda m: f"{m.group(1)}\n{chunk}\n{m.group(3)}", content)


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")

    repos = fetch_repos(token)
    if not repos:
        print("No repositories returned; leaving README unchanged.")
        return

    content = README.read_text()
    updated = replace_chunk(content, "active", render_active(repos))
    if updated == content:
        print("README already current; no change.")
        return

    README.write_text(updated)
    print("Updated README live region.")


if __name__ == "__main__":
    main()
