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
    # 2026-09-26 extension, for matching/keyword_gap.py: the list above missed
    # most of what real JDs actually demand alongside the headline language.
    # Deliberately excludes terms that are also ordinary English verbs/nouns
    # ("Excel", "Segment", "Strategy", "Lambda") — a keyword-gap report that
    # tells someone they're missing "excel" because the JD said "excel at
    # communication" is worse than not mentioning it.
    "Airflow", "dbt", "Snowflake", "Databricks", "Spark", "Hadoop", "BigQuery", "Redshift",
    "Tableau", "Power BI", "Looker", "ETL", "Data Modeling", "Data Analysis",
    "Jenkins", "GitHub Actions", "GitLab CI", "Helm", "Prometheus", "Grafana", "Datadog",
    "RabbitMQ", "Celery", "Nginx", "Serverless", "Pulumi", "Observability", "SRE", "DevOps",
    "Pytest", "Playwright", "Cypress", "Jest", "Selenium", "Test Automation",
    "Scala", "Bash", "PowerShell", "MATLAB",
    "Webpack", "Vite", "Tailwind", "Sass", "Redux", "jQuery", "Flutter", "React Native",
    "Android", "iOS", "OAuth", "SAML", "SSO", "OpenAPI", "Swagger", "Postman", "WebSockets",
    "Stripe", "Twilio", "Shopify", "WordPress", "Salesforce Marketing Cloud",
    "GDPR", "SOC 2", "HIPAA", "PCI DSS", "Incident Response",
    "Amplitude", "Mixpanel", "Braze", "Klaviyo", "Mailchimp", "Zendesk", "Intercom",
    "Notion", "Confluence", "Asana", "Trello", "Miro",
    "Project Management", "Program Management", "Technical Writing", "Localization",
    "Accessibility", "Customer Success", "Forecasting", "SaaS", "B2B", "B2C",
]

_PATTERNS = [(name, re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.I)) for name in _SKILLS]
_BY_NAME = {name.lower(): pattern for name, pattern in _PATTERNS}


def skill_pattern(name: str) -> re.Pattern:
    """The same word-boundary pattern `extract_skills` uses, for one keyword.

    Exposed so matching/keyword_gap.py matches resume facts with exactly the
    regex semantics the job side was extracted with, rather than a second,
    subtly-different one.
    """
    return _BY_NAME.get(name.lower()) or re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.I)


def skill_occurrences(text: str | None) -> dict[str, int]:
    """Canonical skill name -> how many times it appears. Counts matter for the
    keyword-gap importance heuristic (a term repeated five times in a JD is a
    real requirement; one mention in boilerplate is not).
    """
    if not text:
        return {}
    return {name: len(pattern.findall(text)) for name, pattern in _PATTERNS if pattern.search(text)}


def extract_skills(text: str | None) -> list[str]:
    return sorted(skill_occurrences(text))
