"""Export ResumeFact rows to the JSON Resume schema (jsonresume.org/schema,
MIT, DEPENDENCIES.md §3 — adopted as our canonical interchange format rather
than inventing our own shape). ResumeFact is coarser than JSON Resume's rich
per-section fields (one achievement/proof/metric/tags tuple per category, not
separate company/position/dates) — this mapping is necessarily best-effort,
not a lossless round-trip.
"""


def facts_to_jsonresume(facts: list[dict]) -> dict:
    result = {
        "basics": {},
        "work": [],
        "volunteer": [],
        "education": [],
        "awards": [],
        "certificates": [],
        "publications": [],
        "skills": [],
        "languages": [],
        "interests": [],
        "references": [],
        "projects": [],
    }

    for fact in facts:
        category = fact["category"]
        achievement = fact["achievement"]
        proof = fact.get("proof")
        metric = fact.get("metric")
        tags = fact.get("tags") or []

        if category == "experience":
            result["work"].append({
                "name": proof or "",
                "summary": achievement,
                "highlights": [metric] if metric else [],
            })
        elif category == "project":
            result["projects"].append({"name": achievement, "description": proof or ""})
        elif category == "skill":
            result["skills"].append({"name": achievement, "keywords": tags})
        elif category == "certification":
            result["certificates"].append({"name": achievement, "issuer": proof or ""})
        elif category == "education":
            result["education"].append({"institution": proof or "", "area": achievement})

    return result
