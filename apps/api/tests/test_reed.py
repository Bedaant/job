from unittest.mock import MagicMock, patch


def test_fetch_reed_jobs_returns_empty_without_api_key():
    with patch("connectors.reed.get_settings") as mock_settings:
        mock_settings.return_value.reed_api_key = None
        from connectors.reed import fetch_reed_jobs
        assert fetch_reed_jobs("backend engineer") == []


@patch("connectors.reed.httpx.get")
@patch("connectors.reed.get_settings")
def test_fetch_reed_jobs_normalizes_response(mock_settings, mock_get):
    mock_settings.return_value.reed_api_key = "fake-key"
    resp = MagicMock()
    resp.json.return_value = {
        "results": [
            {
                "jobId": 123,
                "jobTitle": "Backend Engineer",
                "employerName": "Acme Ltd",
                "locationName": "London",
                "minimumSalary": 50000.0,
                "maximumSalary": 60000.0,
                "currency": "GBP",
                "jobDescription": "Build things",
                "jobUrl": "https://reed.co.uk/jobs/123",
                "date": "06/08/2026",
            }
        ]
    }
    mock_get.return_value = resp

    from connectors.reed import fetch_reed_jobs
    jobs = fetch_reed_jobs("backend engineer")

    assert len(jobs) == 1
    j = jobs[0]
    assert j["source"] == "reed"
    assert j["external_id"] == "123"
    assert j["title"] == "Backend Engineer"
    assert j["company"] == "Acme Ltd"
    assert j["salary"] == "50000-60000 GBP"
    assert j["remote"] is False


@patch("connectors.reed.httpx.get")
@patch("connectors.reed.get_settings")
def test_fetch_reed_jobs_detects_remote_location(mock_settings, mock_get):
    mock_settings.return_value.reed_api_key = "fake-key"
    resp = MagicMock()
    resp.json.return_value = {
        "results": [{
            "jobId": 1, "jobTitle": "X", "employerName": "Y",
            "locationName": "Remote - UK", "jobUrl": "u", "date": None,
        }]
    }
    mock_get.return_value = resp

    from connectors.reed import fetch_reed_jobs
    jobs = fetch_reed_jobs("x")
    assert jobs[0]["remote"] is True
    assert jobs[0]["salary"] is None
    assert jobs[0]["posted_at"] is None
