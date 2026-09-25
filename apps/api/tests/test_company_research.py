from unittest.mock import MagicMock, patch


@patch("research.company_research.subprocess.run")
def test_research_company_combines_github_and_web(mock_run):
    gh_result = MagicMock(returncode=0, stdout='[{"full_name": "acme/backend", "description": "Acme backend"}]')
    web_result = MagicMock(returncode=0, stdout="Acme Corp builds developer tools.")
    mock_run.side_effect = [gh_result, web_result]

    from research.company_research import research_company
    dossier = research_company("Acme Corp", website="https://acme.example.com")

    assert dossier["github_repos"] == [{"full_name": "acme/backend", "description": "Acme backend"}]
    assert dossier["web_summary"] == "Acme Corp builds developer tools."


@patch("research.company_research.subprocess.run")
def test_research_company_handles_github_failure_gracefully(mock_run):
    gh_result = MagicMock(returncode=1, stdout="")
    web_result = MagicMock(returncode=0, stdout="some text")
    mock_run.side_effect = [gh_result, web_result]

    from research.company_research import research_company
    dossier = research_company("Unknown Co", website="https://unknown.example.com")

    assert dossier["github_repos"] == []
    assert dossier["web_summary"] == "some text"


@patch("research.company_research.subprocess.run")
def test_research_company_no_website_skips_web_fetch(mock_run):
    gh_result = MagicMock(returncode=0, stdout="[]")
    mock_run.return_value = gh_result

    from research.company_research import research_company
    dossier = research_company("Acme Corp")

    assert dossier["web_summary"] is None
    mock_run.assert_called_once()
