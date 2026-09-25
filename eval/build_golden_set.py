"""Generates eval/golden.csv — the >=30 JD/facts golden set PRD.md §11's
Phase 3 exit criterion calls for. Generated, not hand-duplicated (ponytail:
30 near-identical rows by hand is exactly the kind of repetition a script
should own) from two facts profiles crossed with a spread of real-shaped JDs.

FACTS_SPARSE is deliberately thin against senior/specialized JDs — that
mismatch is what actually exercises the pass-2 truth-checker (ADR-006);
an eval set where every JD comfortably matches the candidate never tests
the one invariant this system can't silently get wrong.

Run manually: `python build_golden_set.py` from this directory. Output is
committed (golden.csv), same pattern as other fixture files in this repo —
this script isn't invoked by the eval run itself.
"""
import csv
import json

FACTS_RICH = [
    {"category": "experience", "achievement": "Led backend rewrite from Flask monolith to FastAPI microservices", "proof": "Staff Engineer, Acme Corp", "metric": "cut p95 latency 40%", "tags": ["python", "fastapi", "microservices", "backend"]},
    {"category": "experience", "achievement": "Designed and shipped a real-time event pipeline", "proof": "Staff Engineer, Acme Corp", "metric": "processes 50M events/day", "tags": ["kafka", "python", "data-engineering"]},
    {"category": "project", "achievement": "Built internal CI/CD platform adopted org-wide", "proof": "Acme Corp platform team", "metric": "cut deploy time from 40min to 4min", "tags": ["ci/cd", "docker", "kubernetes", "devops"]},
    {"category": "skill", "achievement": "Deep experience with PostgreSQL performance tuning and query optimization", "proof": None, "metric": None, "tags": ["postgresql", "sql", "database"]},
    {"category": "skill", "achievement": "Production experience with AWS (ECS, RDS, Lambda) and Terraform-managed infra", "proof": None, "metric": None, "tags": ["aws", "terraform", "cloud"]},
    {"category": "experience", "achievement": "Mentored 4 junior engineers, two promoted to mid-level within a year", "proof": "Staff Engineer, Acme Corp", "metric": None, "tags": ["mentoring", "leadership"]},
    {"category": "certification", "achievement": "AWS Certified Solutions Architect – Associate", "proof": "AWS", "metric": None, "tags": ["aws", "certification"]},
]

FACTS_SPARSE = [
    {"category": "experience", "achievement": "Built and maintained a Django web app for internal inventory tracking", "proof": "Junior Developer, Startup Co", "metric": "used by 30 warehouse staff daily", "tags": ["python", "django", "backend"]},
    {"category": "project", "achievement": "Built a personal portfolio site with a small Node.js API backend", "proof": "Side project", "metric": None, "tags": ["javascript", "node.js"]},
    {"category": "education", "achievement": "B.S. Computer Science", "proof": "State University", "metric": None, "tags": ["education"]},
]

# (title, company, description, facts_profile)
JOBS = [
    ("Senior Backend Engineer", "Nimbus Cloud", "Own our core Python/FastAPI services handling millions of requests daily. Deep PostgreSQL and AWS experience required.", "rich"),
    ("Staff Platform Engineer", "Ridgeline Systems", "Lead our CI/CD and Kubernetes platform team. You'll design deploy pipelines used by 200+ engineers.", "rich"),
    ("Backend Engineer, Data Pipelines", "Fathom Analytics", "Build and scale our Kafka-based event pipeline processing tens of millions of events daily.", "rich"),
    ("Cloud Infrastructure Engineer", "Delta Forge", "Own AWS infra (ECS, RDS, Lambda) provisioned via Terraform. AWS certification a strong plus.", "rich"),
    ("Engineering Manager, Backend", "Pinecrest Labs", "Lead a team of backend engineers; prior mentoring experience and a track record of promoting juniors preferred.", "rich"),
    ("Database Performance Engineer", "Quartzline", "Specialist role tuning PostgreSQL at scale — query plans, indexing strategy, replication.", "rich"),
    ("Senior FastAPI Developer", "Solace Health", "Migrate legacy services to FastAPI microservices. Latency-sensitive healthcare workloads.", "rich"),
    ("DevOps Lead", "Ironvale", "Own the internal deploy platform; Docker/Kubernetes/CI-CD ownership end to end.", "rich"),
    ("Principal Backend Engineer", "Northwind Robotics", "Highly senior IC role. Deep systems design, mentorship, and cloud infra ownership expected.", "rich"),
    ("Site Reliability Engineer", "Cobalt Systems", "SRE role focused on AWS reliability, infra-as-code with Terraform, and on-call rotation.", "rich"),
    ("Junior Backend Developer", "Fernway Apps", "Entry-level role maintaining a Django inventory app. Good fit for early-career engineers.", "sparse"),
    ("Frontend/Node.js Developer", "Brightpath", "Build small internal tools with Node.js APIs and simple frontends. New grads welcome.", "sparse"),
    ("Full-Stack Engineer (Entry Level)", "Loomwork", "Junior full-stack role. Django backend, light React frontend. Mentorship provided.", "sparse"),
    ("Machine Learning Engineer", "Vantage AI", "Own our ML training infra: distributed PyTorch jobs, feature pipelines, and model serving at scale.", "sparse"),
    ("Staff iOS Engineer", "Harborlight", "Own our Swift/SwiftUI codebase for a 5M-user consumer app.", "sparse"),
    ("Principal Security Engineer", "Redgate Security", "Lead application security reviews, threat modeling, and incident response for a fintech platform.", "sparse"),
    ("Senior Data Scientist", "Meridian Insights", "Own causal inference models for pricing. Deep statistics and experimentation background required.", "sparse"),
    ("Rust Systems Engineer", "Corewave", "Build low-latency trading infrastructure in Rust. Prior HFT experience strongly preferred.", "sparse"),
    ("Staff Product Designer", "Lumen Studio", "Own end-to-end product design for our core app, from research to high-fidelity prototypes.", "sparse"),
    ("Growth Marketing Manager", "Ferngrove", "Own paid acquisition, SEO, and lifecycle email programs for a DTC brand.", "sparse"),
    ("Backend Engineer, Payments", "Ledgerline", "Build our payments ledger service in Python. PCI-adjacent, high correctness bar.", "rich"),
    ("Software Engineer, Internal Tools", "Cascade Robotics", "Build internal dashboards and tooling in Django/React for a robotics team.", "sparse"),
    ("Senior Kubernetes Platform Engineer", "Stonebridge Cloud", "Own our multi-tenant Kubernetes platform. Deep Docker/K8s/CI-CD expertise required.", "rich"),
    ("Backend Engineer (Mid-Level)", "Wavecrest", "Build FastAPI services for our marketplace product. 2-4 years backend experience.", "rich"),
    ("Analytics Engineer", "Basecamp Data", "Own our event pipeline and warehouse models. Kafka and SQL fluency required.", "rich"),
    ("Solutions Architect", "Trailmark Cloud", "Customer-facing AWS architecture role. AWS certification required, Terraform a plus.", "rich"),
    ("Junior QA Engineer", "Pathwell", "Entry-level QA role, manual + light automation testing for a Django app.", "sparse"),
    ("Senior Site Reliability Engineer", "Glasswing", "Own reliability for a fleet of Kubernetes clusters; CI/CD pipeline ownership included.", "rich"),
    ("Technical Lead, Backend Platform", "Aldergate Systems", "Lead technical direction for our backend platform team; mentoring and Postgres depth expected.", "rich"),
    ("Associate Software Engineer", "Millrace Apps", "New-grad-friendly role building small Node.js services and a portfolio-style internal app.", "sparse"),
]


def main():
    with open("golden.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["jd_title", "jd_company", "jd_description", "facts_json", "__expected"])
        for title, company, description, profile in JOBS:
            facts = FACTS_RICH if profile == "rich" else FACTS_SPARSE
            rubric = (
                "llm-rubric: The JSON output's summary and bullets are specifically relevant to "
                f'the "{title}" role at "{company}" (not generic filler), and the cover letter is '
                "roughly 150-200 words in a professional tone."
            )
            writer.writerow([title, company, description, json.dumps(facts), rubric])

    print(f"wrote {len(JOBS)} rows to golden.csv")


if __name__ == "__main__":
    main()
