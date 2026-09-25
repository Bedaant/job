"""Company research for dossiers (F7, DEPENDENCIES.md §3 — Panniantong/agent-reach).
agent-reach itself is a channel installer/orchestrator (installed as a CLI in
its own isolated venv, tools/.venv-agent-reach/ — kept separate from this
app's numpy/pydantic-sensitive dependency pins). Of its channels, only two
work with zero extra credentials on this machine (confirmed via
`agent-reach doctor`): GitHub (already-authenticated `gh` CLI) and arbitrary
web pages (Jina Reader, a free public endpoint, no key needed). Twitter,
Reddit, and the rest need real per-service credentials not available here —
same reasoning as not building unverifiable connector code elsewhere in this
project; wire those channels in once real tokens exist.
"""
import json
import subprocess

_JINA_READER_BASE = "https://r.jina.ai/"


def research_company(name: str, website: str | None = None) -> dict:
    gh_result = subprocess.run(
        ["gh", "search", "repos", name, "--limit", "5", "--json", "fullName,description"],
        capture_output=True, text=True,
    )
    repos = []
    if gh_result.returncode == 0 and gh_result.stdout.strip():
        raw = json.loads(gh_result.stdout)
        repos = [{"full_name": r.get("fullName") or r.get("full_name"), "description": r.get("description")} for r in raw]

    web_summary = None
    if website:
        # text=True alone decodes with the OS default codepage (cp1252 on
        # Windows), which raises UnicodeDecodeError on real UTF-8 web
        # content and silently leaves stdout=None — explicit encoding
        # needed, found only by running this against a real page.
        web_result = subprocess.run(
            ["curl", "-s", f"{_JINA_READER_BASE}{website}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if web_result.returncode == 0 and web_result.stdout:
            web_summary = web_result.stdout.strip()

    return {"company": name, "github_repos": repos, "web_summary": web_summary}
