import json
from unittest.mock import MagicMock, patch

import pytest

from parsing.llm_extract import extract_facts_from_text


def _mock_anthropic_response(payload_dict):
    block = MagicMock()
    block.type = "text"
    block.text = json.dumps(payload_dict)
    response = MagicMock()
    response.content = [block]
    return response


def test_extract_facts_parses_well_formed_response():
    payload = {
        "facts": [
            {
                "category": "experience",
                "achievement": "Cut checkout API p99 latency from 1.4s to 180ms",
                "proof": "Payments team, Acme Corp",
                "metric": "87% p99 reduction",
                "tags": ["backend", "performance"],
            }
        ]
    }
    with patch("parsing.llm_extract._client") as mock_client:
        mock_client.messages.create.return_value = _mock_anthropic_response(payload)
        facts = extract_facts_from_text("resume text here")

    assert len(facts) == 1
    assert facts[0]["achievement"] == "Cut checkout API p99 latency from 1.4s to 180ms"
    assert facts[0]["category"] == "experience"


def test_extract_facts_strips_markdown_code_fences():
    payload = {"facts": [{"category": "skill", "achievement": "Python", "proof": None, "metric": None, "tags": []}]}
    block = MagicMock()
    block.type = "text"
    block.text = f"```json\n{json.dumps(payload)}\n```"
    response = MagicMock()
    response.content = [block]

    with patch("parsing.llm_extract._client") as mock_client:
        mock_client.messages.create.return_value = response
        facts = extract_facts_from_text("resume text here")

    assert facts[0]["achievement"] == "Python"


def test_extract_facts_raises_clear_error_on_malformed_json():
    block = MagicMock()
    block.type = "text"
    block.text = "this is not json at all, sorry"
    response = MagicMock()
    response.content = [block]

    with patch("parsing.llm_extract._client") as mock_client:
        mock_client.messages.create.return_value = response
        with pytest.raises(ValueError, match="malformed"):
            extract_facts_from_text("resume text here")


def test_extract_facts_rejects_empty_resume_text():
    with pytest.raises(ValueError, match="empty"):
        extract_facts_from_text("")
