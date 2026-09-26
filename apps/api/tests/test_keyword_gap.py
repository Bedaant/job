"""Keyword-gap scorer (JD vocabulary vs the Facts KB).

The load-bearing test in this file is
`test_no_suggestion_ever_references_a_missing_keyword` — everything else is
plumbing. A `missing` keyword means "the user does not have this"; producing a
suggestion that puts it on the resume anyway is fabrication, which is the one
failure mode that gets a real applicant blacklisted.
"""
import models
from matching.keyword_gap import compute_keyword_gap


def _fact(achievement, proof=None, metric=None, tags=None):
    return models.ResumeFact(
        category="experience", achievement=achievement, proof=proof, metric=metric, tags=tags or []
    )


def _kw(entries):
    return {e["keyword"] for e in entries}


# ---------- match types ----------

def test_exact_match_is_reported_with_its_evidence_fact():
    jd = "Requirements: strong Python and PostgreSQL experience."
    facts = [_fact("Built a Python data pipeline"), _fact("Tuned PostgreSQL queries")]

    result = compute_keyword_gap(jd, facts)

    assert "Python" in _kw(result["matched"])
    python = next(m for m in result["matched"] if m["keyword"] == "Python")
    assert python["match_type"] == "exact"
    assert python["evidence_fact_id_or_index"] == 0


def test_fuzzy_match_catches_a_spelling_variant():
    """JD says 'Node.js', the resume says 'NodeJS' — same skill, no exact hit."""
    jd = "Requirements: Node.js in production."
    facts = [_fact("Shipped three NodeJS services")]

    result = compute_keyword_gap(jd, facts)

    node = next(m for m in result["matched"] if m["keyword"] == "Node.js")
    assert node["match_type"] == "fuzzy"
    assert "Node.js" not in _kw(result["missing"])


def test_synonym_match_catches_an_abbreviation_fuzzy_cannot():
    """'K8s' and 'Kubernetes' share almost no characters — needs the synonym map."""
    jd = "Requirements: deep K8s experience."
    facts = [_fact("Ran a Kubernetes cluster for 40 services")]

    result = compute_keyword_gap(jd, facts)

    k = next(m for m in result["matched"] if m["keyword"] == "Kubernetes")
    assert k["match_type"] == "synonym"


def test_keyword_with_no_support_anywhere_lands_in_missing():
    jd = "Requirements: Terraform and Ansible are required."
    facts = [_fact("Wrote Python scripts")]

    result = compute_keyword_gap(jd, facts)

    assert {"Terraform", "Ansible"} <= _kw(result["missing"])
    assert {"Terraform", "Ansible"} & _kw(result["matched"]) == set()
    assert all(m["importance"] in ("high", "medium", "low") for m in result["missing"])


# ---------- the invariant ----------

def test_no_suggestion_ever_references_a_missing_keyword():
    """ADR-009 / the anti-fraud rail. A missing keyword is never suggested.

    Deliberately adversarial input: a JD stuffed with keywords the facts do not
    support, plus a couple they do, so there is real pressure to produce a
    "just add Kubernetes" suggestion.
    """
    jd = """
    Senior Platform Engineer
    Requirements: Kubernetes, Terraform, Go, Rust, Kafka, Elasticsearch, gRPC,
    Ansible, Azure, TensorFlow. Kubernetes is essential. Terraform is essential.
    Nice to have: Python, PostgreSQL.
    """
    facts = [_fact("Built a Python reporting service"), _fact("Owned a PostgreSQL schema migration")]

    result = compute_keyword_gap(jd, facts, job_title="Senior Platform Engineer")

    missing = _kw(result["missing"])
    assert "Kubernetes" in missing  # the bait actually is missing
    assert missing, "test is vacuous if nothing is missing"
    for s in result["suggestions"]:
        assert s["keyword"] not in missing, f"fabrication: suggested missing keyword {s['keyword']}"
        assert s["action"] in ("surface", "reword")
        assert s["fact_id_or_index"] is not None


def test_every_suggestion_points_at_a_real_fact_the_user_has():
    jd = "Requirements: Node.js, K8s, Python."
    facts = [_fact("Shipped NodeJS services"), _fact("Automation work", tags=["Kubernetes", "Python"])]

    result = compute_keyword_gap(jd, facts)

    valid_indexes = set(range(len(facts)))
    assert result["suggestions"], "this JD should produce at least one reword/surface suggestion"
    for s in result["suggestions"]:
        assert s["fact_id_or_index"] in valid_indexes
        assert s["rationale"]


# ---------- weak / buried keywords ----------

def test_keyword_only_in_a_facts_tags_is_weak_not_strong():
    """Tags never reach the rendered bullet text — that is the surface opportunity."""
    jd = "Requirements: Kubernetes, Kubernetes orchestration at scale."
    facts = [_fact("Automated a deployment pipeline", tags=["Kubernetes"])]

    result = compute_keyword_gap(jd, facts)

    assert "Kubernetes" in _kw(result["matched"])
    assert "Kubernetes" in _kw(result["weak"])
    assert any(s["keyword"] == "Kubernetes" and s["action"] == "surface" for s in result["suggestions"])


# ---------- input handling ----------

def test_html_is_stripped_before_analysis():
    """Feeds deliver JDs as HTML; tags and entities must not break matching."""
    jd = "<div><h3>Requirements</h3><ul><li><strong>Python</strong>&nbsp;&amp; PostgreSQL</li></ul></div>"
    facts = [_fact("Built a Python service on PostgreSQL")]

    result = compute_keyword_gap(jd, facts)

    assert {"Python", "PostgreSQL"} <= _kw(result["matched"])
    assert result["coverage"] == 1.0


def test_html_tag_names_are_not_mistaken_for_keywords():
    jd = "<html><head><style>a{}</style></head><body><p>We bake bread.</p></body></html>"
    result = compute_keyword_gap(jd, [_fact("Baked bread")])
    assert _kw(result["missing"]) == set()


def test_empty_and_garbage_input_does_not_crash():
    for jd in (None, "", "   ", "!!! ??? <<<>>>", "\x00\x01"):
        result = compute_keyword_gap(jd, [])
        assert result["coverage"] == 0.0
        assert result["matched"] == [] and result["suggestions"] == []

    result = compute_keyword_gap("Requirements: Python.", [])
    assert result["coverage"] == 0.0
    assert "Python" in _kw(result["missing"])


def test_plain_strings_are_accepted_as_facts():
    result = compute_keyword_gap("Requirements: Python.", ["Built a Python service"])
    assert "Python" in _kw(result["matched"])


def test_job_skills_argument_contributes_keywords():
    result = compute_keyword_gap("A role about teamwork.", ["Wrote Terraform modules"], job_skills=["Terraform"])
    assert "Terraform" in _kw(result["matched"])


# ---------- importance ----------

def test_requirements_section_and_title_outrank_boilerplate():
    jd = """
    About us: we love Figma and ping pong.
    Requirements: Kubernetes is required.
    """
    result = compute_keyword_gap(jd, [], job_title="Kubernetes Platform Engineer")

    importance = {m["keyword"]: m["importance"] for m in result["missing"]}
    assert importance["Kubernetes"] == "high"
    assert importance["Figma"] in ("low", "medium")


def test_coverage_is_between_zero_and_one():
    jd = "Requirements: Python, Kubernetes, Terraform."
    result = compute_keyword_gap(jd, [_fact("Wrote Python")])
    assert 0.0 < result["coverage"] < 1.0
