"""Resume parsing must go through tailoring.engine._llm_request like every other LLM call, so the
provider guard (timeout, breaker, spend cap) and the fallback model cover it too."""
import json
from unittest.mock import MagicMock, patch

import pytest

from parsing import llm_extract
from providers import guard
from schemas import ApplicantBasics


@pytest.fixture
def guarded(monkeypatch):
    seen = []
    monkeypatch.setattr(guard, "call", lambda provider, fn, **kw: seen.append(provider) or fn())
    return seen


def _anthropic_reply(payload):
    block = MagicMock(type="text", text=json.dumps(payload))
    return MagicMock(content=[block])


def test_fact_extraction_passes_the_llm_guard(guarded):
    with patch("parsing.llm_extract._client") as client:
        client.messages.create.return_value = _anthropic_reply({"facts": []})
        assert llm_extract.extract_facts_from_text("Built a thing at Acme.") == []
    assert guarded == ["llm"]


def test_basics_extraction_passes_the_llm_guard(guarded):
    instructor_client = MagicMock()
    instructor_client.messages.create.return_value = ApplicantBasics(full_name="Ada Lovelace")
    with patch("parsing.llm_extract._get_instructor_client", return_value=instructor_client):
        assert llm_extract.extract_basics("Ada Lovelace, ada@example.com").full_name == "Ada Lovelace"
    assert guarded == ["llm"]


def test_a_spend_cap_refusal_reaches_the_caller(monkeypatch):
    def refuse(provider, fn, **kw):
        raise guard.SpendCapReached("llm")

    monkeypatch.setattr(guard, "call", refuse)
    with patch("parsing.llm_extract._client") as client, pytest.raises(guard.SpendCapReached):
        llm_extract.extract_facts_from_text("Built a thing at Acme.")
    client.messages.create.assert_not_called()
