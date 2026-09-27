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


# ---------- nvidia_smoke provider branch ----------

def test_extract_facts_uses_nvidia_client_when_provider_is_nvidia_smoke():
    payload = {"facts": [{"category": "skill", "achievement": "Rust", "proof": None, "metric": None, "tags": []}]}
    choice = MagicMock()
    choice.message.content = json.dumps(payload)
    response = MagicMock()
    response.choices = [choice]

    with patch("parsing.llm_extract.get_settings") as mock_settings, \
         patch("parsing.llm_extract._get_nvidia_client") as mock_get_nvidia:
        mock_settings.return_value.llm_provider = "nvidia_smoke"
        mock_settings.return_value.nvidia_smoke_model = "some/model"
        nvidia_client = MagicMock()
        nvidia_client.chat.completions.create.return_value = response
        mock_get_nvidia.return_value = nvidia_client

        facts = extract_facts_from_text("resume text here")

    assert facts[0]["achievement"] == "Rust"
    nvidia_client.chat.completions.create.assert_called_once()
    assert nvidia_client.chat.completions.create.call_args.kwargs["model"] == "some/model"


def test_extract_facts_uses_the_nvidia_model_when_provider_is_nvidia():
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = 'Sure! {"facts": [{"category": "skill", "achievement": "Python"}]}'
    with patch("parsing.llm_extract.get_settings") as mock_settings, \
         patch("parsing.llm_extract._get_nvidia_client") as mock_get_nvidia:
        mock_settings.return_value.llm_provider = "nvidia"
        mock_settings.return_value.nvidia_model = "nvidia/nemotron-3-super-120b-a12b"
        nvidia_client = MagicMock()
        nvidia_client.chat.completions.create.return_value = response
        mock_get_nvidia.return_value = nvidia_client

        from parsing.llm_extract import extract_facts_from_text
        facts = extract_facts_from_text("Python developer")

    assert nvidia_client.chat.completions.create.call_args.kwargs["model"] == "nvidia/nemotron-3-super-120b-a12b"
    # Open models often wrap JSON in a sentence — the object must still be found.
    assert facts == [{"category": "skill", "achievement": "Python"}]


def test_nvidia_extra_body_turns_thinking_off_only_for_the_real_nvidia_provider():
    from core.config import Settings
    base = dict(database_url="sqlite://", jwt_secret="x", redis_url="redis://localhost")
    assert Settings(**base, llm_provider="nvidia").nvidia_extra_body() == {
        "chat_template_kwargs": {"enable_thinking": False}
    }
    assert Settings(**base, llm_provider="nvidia", nvidia_enable_thinking=True).nvidia_extra_body() == {
        "chat_template_kwargs": {"enable_thinking": True}
    }
    # The smoke model may not accept the kwarg; leave its requests untouched.
    assert Settings(**base, llm_provider="nvidia_smoke").nvidia_extra_body() == {}
