from matching.skills import extract_skills


def test_extract_skills_finds_known_terms():
    text = "We need a backend engineer skilled in Python, PostgreSQL, and Docker."
    assert extract_skills(text) == ["Docker", "PostgreSQL", "Python"]


def test_extract_skills_is_case_insensitive():
    text = "Experience with react and TYPESCRIPT required."
    assert set(extract_skills(text)) == {"React", "TypeScript"}


def test_extract_skills_matches_special_char_terms_with_word_boundaries():
    text = "Proficient in C++ and CI/CD pipelines, Node.js a plus."
    assert set(extract_skills(text)) == {"C++", "CI/CD", "Node.js"}


def test_extract_skills_does_not_match_substrings():
    """'Java' must not match inside 'JavaScript'."""
    text = "We use JavaScript heavily, no Java here."
    assert set(extract_skills(text)) == {"JavaScript", "Java"}


def test_extract_skills_returns_empty_for_no_matches():
    assert extract_skills("A role about gardening and baking.") == []


def test_extract_skills_returns_sorted_unique_list():
    text = "Python, python, PYTHON — we really mean Python."
    assert extract_skills(text) == ["Python"]


def test_extract_skills_handles_none_and_empty():
    assert extract_skills(None) == []
    assert extract_skills("") == []


def test_extract_skills_finds_pm_terms():
    text = "Run Agile/Scrum ceremonies, own Roadmapping, run A/B Testing and manage OKRs."
    assert set(extract_skills(text)) == {"Agile", "Scrum", "Roadmapping", "A/B Testing", "OKRs"}


def test_extract_skills_finds_marketing_terms():
    text = "Own SEO and SEM strategy, run Google Analytics reporting and email marketing campaigns via HubSpot."
    assert set(extract_skills(text)) == {"SEO", "SEM", "Google Analytics", "Email Marketing", "HubSpot"}
