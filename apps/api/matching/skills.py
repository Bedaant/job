"""F6 skill extraction for `Job.skills` (SPEC.md §1: `skills text[]`, "extracted,
for coverage scoring"). Keyword phrase-matching against a curated vocabulary,
same style as matching/filters.py's seniority inference.

Studied `KonstantinosPetrakis/esco-skill-extractor` (docs/DEPENDENCIES.md §3,
MIT, "study only, not adopted") before building this: it matches job text
against the full ESCO taxonomy (~13k skills) via sentence-transformers/torch
embeddings, returning ESCO URIs. Not adopted — a new heavy ML dependency
(this project already declined one once, for garak/CI, docs/WORKLOG.md
2026-08-15) for output that's a URI, not the human-readable string
SPEC.md's `matched_skills`/`missing_skills` need for the UI ("Missing:
Kubernetes, Terraform", PRD.md matching section). We already pay for
semantic understanding via Voyage embeddings (matching/embeddings.py) —
this is deliberately the cheap, explicit, explainable other half.

ponytail: fixed vocabulary means recall is bounded by this list, not any
job's actual skill set; upgrade path is a bigger curated list or an LLM
extraction pass, not this file's design changing.
"""
import re

_SKILLS = [
    # Developer
    "Python", "JavaScript", "TypeScript", "Java", "Go", "Rust", "C++", "C#", "Ruby", "PHP",
    "Swift", "Kotlin", "SQL", "HTML", "CSS",
    "React", "Next.js", "Vue", "Angular", "Svelte", "Django", "FastAPI", "Flask", "Spring",
    "Node.js", "Express", "Rails", ".NET",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "Kafka",
    "Docker", "Kubernetes", "Terraform", "Ansible", "AWS", "GCP", "Azure", "CI/CD",
    "GraphQL", "REST", "gRPC", "Microservices",
    "Git", "Linux", "Machine Learning", "TensorFlow", "PyTorch", "pandas", "NumPy",
    # Product Manager
    "Agile", "Scrum", "Kanban", "Roadmapping", "A/B Testing", "Stakeholder Management",
    "JIRA", "Product Strategy", "User Research", "OKRs", "Product Analytics", "Figma",
    "Wireframing", "Go-to-Market", "Competitive Analysis", "Prioritization",
    # Marketing
    "SEO", "SEM", "Content Marketing", "Email Marketing", "Google Analytics", "HubSpot",
    "Paid Social", "Copywriting", "Brand Strategy", "CRM", "Salesforce", "Marketo",
    "Growth Marketing", "Social Media Marketing", "PPC", "Marketing Automation",
]

_PATTERNS = [(name, re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.I)) for name in _SKILLS]


def extract_skills(text: str | None) -> list[str]:
    if not text:
        return []
    matched = {name for name, pattern in _PATTERNS if pattern.search(text)}
    return sorted(matched)
