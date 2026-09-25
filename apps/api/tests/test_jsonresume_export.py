from parsing.jsonresume_export import facts_to_jsonresume


def _fact(category, achievement, proof=None, metric=None, tags=None):
    return {"category": category, "achievement": achievement, "proof": proof, "metric": metric, "tags": tags or []}


def test_export_has_jsonresume_top_level_shape():
    result = facts_to_jsonresume([])
    assert set(result.keys()) >= {"basics", "work", "education", "skills", "projects", "certificates"}


def test_export_maps_experience_facts_to_work():
    facts = [_fact("experience", "Led backend rewrite", proof="Staff Engineer, Acme Corp", metric="cut latency 40%")]
    result = facts_to_jsonresume(facts)
    assert result["work"] == [{
        "name": "Staff Engineer, Acme Corp",
        "summary": "Led backend rewrite",
        "highlights": ["cut latency 40%"],
    }]


def test_export_maps_skill_facts_grouped_by_tags():
    facts = [
        _fact("skill", "PostgreSQL tuning", tags=["postgresql", "sql"]),
        _fact("skill", "AWS infra", tags=["aws"]),
    ]
    result = facts_to_jsonresume(facts)
    assert result["skills"] == [
        {"name": "PostgreSQL tuning", "keywords": ["postgresql", "sql"]},
        {"name": "AWS infra", "keywords": ["aws"]},
    ]


def test_export_maps_project_and_certification_and_education():
    facts = [
        _fact("project", "Built CI/CD platform", proof="Acme platform team"),
        _fact("certification", "AWS Certified Solutions Architect", proof="AWS"),
        _fact("education", "B.S. Computer Science", proof="State University"),
    ]
    result = facts_to_jsonresume(facts)
    assert result["projects"] == [{"name": "Built CI/CD platform", "description": "Acme platform team"}]
    assert result["certificates"] == [{"name": "AWS Certified Solutions Architect", "issuer": "AWS"}]
    assert result["education"] == [{"institution": "State University", "area": "B.S. Computer Science"}]


def test_export_omits_empty_metric_highlights():
    facts = [_fact("experience", "Did a thing", proof="Some Co")]
    result = facts_to_jsonresume(facts)
    assert result["work"] == [{"name": "Some Co", "summary": "Did a thing", "highlights": []}]
