"""scripts/measure_campaign_yield.py with every paid call faked: nothing here touches Apify or an LLM."""
from unittest.mock import MagicMock, patch

from scripts import measure_campaign_yield as m


def _row(n, title, location, source="linkedin_external"):
    return {"source": source, "external_id": str(n), "company": f"Co{n}", "title": title,
            "location": location, "apply_url": f"https://co{n}.example/apply"}


def test_counts_only_relevant_indian_matches_once():
    linkedin = MagicMock(return_value=[
        _row(1, "Data Analyst", "Bengaluru, Karnataka, India"),
        _row(2, "Senior Data Analyst", "Bangalore"),       # alias of the city
        _row(3, "Data Analyst", "Austin, TX"),              # not India
        _row(4, "Data Scientist", "Bengaluru, India"),      # the judge says no
    ])
    jobspy = MagicMock(return_value=[_row(1, "Data Analyst", "Bengaluru, Karnataka, India")])  # duplicate
    verdicts = {"Data Analyst": "match", "Senior Data Analyst": "match", "Data Scientist": "no"}
    ask = MagicMock(side_effect=lambda role, titles: {t: verdicts[t] for t in titles})
    with patch("workers.jobs.fetch_linkedin_jobs", linkedin), patch("workers.jobs.fetch_jobspy_jobs", jobspy), \
            patch("workers.jobs.fetch_linkedin_posts", MagicMock(return_value=[])), \
            patch("workers.jobs.time.sleep"), patch("matching.role_judge._ask", ask):
        result = m.measure("Data Analyst", "Bengaluru")

    assert linkedin.call_args.args[:2] == ("Data Analyst", "Bengaluru")
    assert result["unique"] == 4 and result["indian"] == 3
    assert result["relevant_indian"] == 2
    assert result["meets_bar"] is False  # the plan's bar is 20


def test_refuses_to_spend_without_yes(capsys):
    with patch.object(m, "measure") as measure:
        assert m.main(["Data Analyst", "Bengaluru"]) == 2
    measure.assert_not_called()
    assert "--yes" in capsys.readouterr().out
