import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from lxml import etree

API_URL = "https://api.github.com"
USER_NAME = os.environ.get("USER_NAME", "DisturbedCrow")
CONTRIBUTIONS_YEAR = os.environ.get("PROFILE_CONTRIBUTIONS_YEAR") or str(datetime.now(timezone.utc).year)
CONTRIBUTIONS_FALLBACK = int(os.environ.get("PROFILE_CONTRIBUTIONS", "0"))

SESSION = requests.Session()
SESSION.headers.update(
    {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"{USER_NAME}-profile-readme",
    }
)
TOKEN = os.environ.get("GITHUB_TOKEN")
if TOKEN:
    SESSION.headers["Authorization"] = f"Bearer {TOKEN}"


def api_get(path, **params):
    response = SESSION.get(f"{API_URL}/{path}", params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def search_total(query, endpoint="issues"):
    data = api_get(f"search/{endpoint}", q=query, per_page=1)
    return int(data["total_count"])


def owned_repository_stats():
    page = 1
    repositories = []
    while True:
        batch = api_get(
            f"users/{USER_NAME}/repos",
            type="owner",
            sort="updated",
            per_page=100,
            page=page,
        )
        repositories.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return len(repositories), sum(repo["stargazers_count"] for repo in repositories)


def contributions_for_year(year):
    """Total contributions in a calendar year via GraphQL; falls back to PROFILE_CONTRIBUTIONS."""
    if not TOKEN:
        return CONTRIBUTIONS_FALLBACK
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar { totalContributions }
        }
      }
    }"""
    variables = {"login": USER_NAME, "from": f"{year}-01-01T00:00:00Z", "to": f"{year}-12-31T23:59:59Z"}
    try:
        response = SESSION.post(f"{API_URL}/graphql", json={"query": query, "variables": variables}, timeout=30)
        response.raise_for_status()
        return int(response.json()["data"]["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"])
    except Exception as error:  # noqa: BLE001 - keep the README build alive on API hiccups
        print(f"contributions lookup failed ({error}); using fallback {CONTRIBUTIONS_FALLBACK}")
        return CONTRIBUTIONS_FALLBACK


def update_svg(filename, values):
    tree = etree.parse(str(filename))
    root = tree.getroot()
    for element_id, value in values.items():
        element = root.find(f".//*[@id='{element_id}']")
        if element is None:
            raise ValueError(f"Missing SVG element: {element_id}")
        element.text = f"{value:,}" if isinstance(value, int) else str(value)
    tree.write(str(filename), encoding="utf-8", xml_declaration=True)


def main():
    user = api_get(f"users/{USER_NAME}")
    repo_count, star_count = owned_repository_stats()
    values = {
        "repo_data": repo_count,
        "star_data": star_count,
        "follower_data": int(user["followers"]),
        "contributions_year": CONTRIBUTIONS_YEAR,
        "contributions_data": contributions_for_year(CONTRIBUTIONS_YEAR),
        "commit_data": search_total(f"author:{USER_NAME}", endpoint="commits"),
        "pr_data": search_total(f"author:{USER_NAME} type:pr"),
        "merged_pr_data": search_total(f"author:{USER_NAME} type:pr is:merged"),
    }
    for filename in (Path("dark_mode.svg"), Path("light_mode.svg")):
        update_svg(filename, values)
    for key, value in values.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
