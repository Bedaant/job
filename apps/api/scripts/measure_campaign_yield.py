"""NEXT-WORK-PLAN P0 #6: does one campaign search for a non-PM role find >= 20 relevant Indian jobs?

Runs the same searches campaign_search_task runs for a campaign with this one role and city
(LinkedIn jobs, LinkedIn hiring posts, JobSpy/Glassdoor), then asks the role judge which titles
are the role. Saves NOTHING: no campaign, no jobs, no verdicts.

SPENDS MONEY (Apify rows + LLM calls, roughly $0.10 a run) and needs owner approval:
    python scripts/measure_campaign_yield.py "Data Analyst" "Bengaluru" --yes
"""
import argparse
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

_API_ROOT = Path(__file__).resolve().parents[1]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from connectors.normalize import canonical_hash  # noqa: E402
from matching import role_judge  # noqa: E402
from matching.filters import CITY_COUNTRY  # noqa: E402
from workers import jobs as wj  # noqa: E402

BAR = 20  # the plan's "at least 20 relevant Indian matches in one run"
_INDIA = re.compile(r"\b(" + "|".join(map(re.escape, ["india", *CITY_COUNTRY])) + r")\b")


def measure(role: str, city: str) -> dict:
    parts = wj._search_plan_parts(SimpleNamespace(roles=[role], locations=[city], sources=[]))
    found, per_source = {}, {}
    for source, fetch in wj._search_fetches(parts).items():
        if not parts[source]:
            continue
        rows, _, run = wj._isolate(source, fetch)
        per_source[source] = {"fetched": run["fetched"], "error": run["error"]}
        for j in rows:
            found.setdefault(canonical_hash(j["company"], j["title"], j.get("location")), j)

    indian = [j for j in found.values() if _INDIA.search((j.get("location") or "").lower())]
    titles = list(dict.fromkeys(j["title"] for j in indian if j.get("title")))
    verdicts: dict[str, str] = {}
    for start in range(0, len(titles), role_judge.BATCH_SIZE):
        verdicts.update(role_judge._ask(role, titles[start:start + role_judge.BATCH_SIZE]))
    relevant = [j for j in indian if verdicts.get(j.get("title")) == "match"]
    return {"role": role, "city": city, "sources": per_source, "unique": len(found),
            "indian": len(indian), "relevant_indian": len(relevant), "bar": BAR,
            "meets_bar": len(relevant) >= BAR, "relevant_titles": sorted({j["title"] for j in relevant})}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python scripts/measure_campaign_yield.py")
    p.add_argument("role")
    p.add_argument("city")
    p.add_argument("--yes", action="store_true", help="confirm: this spends Apify and LLM credit")
    a = p.parse_args(argv)
    if not a.yes:
        print("This calls paid services (Apify rows + LLM, ~$0.10). Re-run with --yes once approved.")
        return 2
    print(json.dumps(measure(a.role, a.city), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
