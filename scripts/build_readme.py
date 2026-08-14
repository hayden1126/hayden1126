"""Refresh the auto-updating region of README.md from primary sources.

Pulls the latest GitHub Release of each public repo via the GraphQL API and rewrites
the block between the `releases` markers. Standard library only (no pip dependencies),
so nothing can break in CI. Deterministic: stable ordering, no run timestamps, and the
file is only rewritten when the rendered content actually changes.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
MARKER = "releases"
LOGIN = "hayden1126"
GRAPHQL_URL = "https://api.github.com/graphql"
MAX_ITEMS = 5

QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(first: 100, privacy: PUBLIC, isFork: false, ownerAffiliations: [OWNER]) {
      nodes {
        name
        url
        releases(first: 1, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes { tagName publishedAt url }
        }
      }
    }
  }
}
"""


def fetch_releases(token: str) -> list[dict]:
    """Return each public repo's latest release, newest first."""
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

    releases = []
    for repo in body["data"]["user"]["repositories"]["nodes"]:
        nodes = repo["releases"]["nodes"]
        if not nodes:
            continue
        release = nodes[0]
        releases.append(
            {
                "name": repo["name"],
                "repo_url": repo["url"],
                "tag": release["tagName"],
                "date": release["publishedAt"][:10],
                "release_url": release["url"],
            }
        )
    releases.sort(key=lambda r: (r["date"], r["name"]), reverse=True)
    return releases[:MAX_ITEMS]


def render(releases: list[dict]) -> str:
    """Render the releases as a markdown list."""
    lines = [
        f'- **[{r["name"]}]({r["repo_url"]})** '
        f'[`{r["tag"]}`]({r["release_url"]}) &middot; {r["date"]}'
        for r in releases
    ]
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

    releases = fetch_releases(token)
    if not releases:
        print("No releases found; leaving README unchanged.")
        return

    content = README.read_text()
    updated = replace_chunk(content, MARKER, render(releases))
    if updated == content:
        print("README already current; no change.")
        return

    README.write_text(updated)
    print(f"Updated README with {len(releases)} release(s).")


if __name__ == "__main__":
    main()
