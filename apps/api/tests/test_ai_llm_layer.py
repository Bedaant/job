"""LLM choke-point: content-addressed cache, per-call timeout, one fallback model."""
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from tailoring import engine


class Answer(BaseModel):
    text: str


class FakeRedis:
    def __init__(self):
        self.store, self.ttls = {}, {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        self.ttls[key] = ex


def _nvidia_settings(fallback=None):
    s = MagicMock()
    s.llm_provider = "nvidia"
    s.nvidia_model = "primary-model"
    s.llm_fallback_model = fallback
    s.llm_cache_ttl_seconds = 3600
    s.nvidia_extra_body.return_value = {}
    return s


def _client_returning(*outcomes):
    """Instructor client whose create() yields each outcome in turn (exceptions raised)."""
    client = MagicMock()
    client.chat.completions.create.side_effect = list(outcomes)
    return client


def _models_called(client):
    return [c.kwargs["model"] for c in client.chat.completions.create.call_args_list]


def test_same_request_twice_is_one_paid_call(monkeypatch):
    cache = FakeRedis()
    client = _client_returning(Answer(text="hi"))
    with patch.object(engine, "_settings", _nvidia_settings()), \
         patch.object(engine, "_cache_client", lambda: cache), \
         patch.object(engine, "_get_nvidia_instructor_client", lambda: client):
        first = engine._call_claude_structured("sys", "user", Answer)
        second = engine._call_claude_structured("sys", "user", Answer)
    assert first == second == Answer(text="hi")
    assert client.chat.completions.create.call_count == 1
    assert list(cache.ttls.values()) == [3600]


def test_a_different_prompt_or_schema_is_a_different_key():
    class Other(BaseModel):
        text: str
        extra: int = 0

    cache = FakeRedis()
    client = _client_returning(Answer(text="a"), Answer(text="b"), Other(text="c"))
    with patch.object(engine, "_settings", _nvidia_settings()), \
         patch.object(engine, "_cache_client", lambda: cache), \
         patch.object(engine, "_get_nvidia_instructor_client", lambda: client):
        engine._call_claude_structured("sys", "user one", Answer)
        engine._call_claude_structured("sys", "user two", Answer)
        engine._call_claude_structured("sys", "user one", Other)
    assert client.chat.completions.create.call_count == 3
    assert len(cache.store) == 3


def test_a_failed_call_is_never_cached():
    cache = FakeRedis()
    client = _client_returning(RuntimeError("provider down"), Answer(text="ok"))
    with patch.object(engine, "_settings", _nvidia_settings()), \
         patch.object(engine, "_cache_client", lambda: cache), \
         patch.object(engine, "_get_nvidia_instructor_client", lambda: client):
        with pytest.raises(RuntimeError):
            engine._call_claude_structured("sys", "user", Answer)
        assert cache.store == {}
        assert engine._call_claude_structured("sys", "user", Answer) == Answer(text="ok")
    assert client.chat.completions.create.call_count == 2


def test_a_cached_value_that_no_longer_validates_is_a_miss():
    cache = FakeRedis()
    client = _client_returning(Answer(text="fresh"))
    with patch.object(engine, "_settings", _nvidia_settings()), \
         patch.object(engine, "_cache_client", lambda: cache), \
         patch.object(engine, "_get_nvidia_instructor_client", lambda: client):
        key = engine._cache_key("sys", "user", Answer, None, None, engine.NVIDIA_STRUCTURED_MAX_TOKENS)
        cache.store[key] = '{"not_text": 1}'
        assert engine._call_claude_structured("sys", "user", Answer) == Answer(text="fresh")


def test_redis_being_down_never_stops_the_call():
    def broken():
        raise ConnectionError("redis down")

    client = _client_returning(Answer(text="ok"))
    with patch.object(engine, "_settings", _nvidia_settings()), \
         patch.object(engine, "_cache_client", broken), \
         patch.object(engine, "_get_nvidia_instructor_client", lambda: client):
        assert engine._call_claude_structured("sys", "user", Answer) == Answer(text="ok")


def test_primary_failure_falls_back_once_to_the_configured_model():
    client = _client_returning(TimeoutError("primary timed out"), Answer(text="from fallback"))
    with patch.object(engine, "_settings", _nvidia_settings(fallback="fallback-model")), \
         patch.object(engine, "_cache_client", FakeRedis), \
         patch.object(engine, "_get_nvidia_instructor_client", lambda: client):
        assert engine._call_claude_structured("sys", "user", Answer) == Answer(text="from fallback")
    assert _models_called(client) == ["primary-model", "fallback-model"]
    # The fallback goes through the same validated path: same response_model.
    assert client.chat.completions.create.call_args.kwargs["response_model"] is Answer


def test_no_fallback_configured_fails_as_before():
    client = _client_returning(TimeoutError("primary timed out"))
    with patch.object(engine, "_settings", _nvidia_settings(fallback=None)), \
         patch.object(engine, "_cache_client", FakeRedis), \
         patch.object(engine, "_get_nvidia_instructor_client", lambda: client):
        with pytest.raises(TimeoutError):
            engine._call_claude_structured("sys", "user", Answer)
    assert _models_called(client) == ["primary-model"]


def test_both_models_failing_raises_and_tries_each_once():
    client = _client_returning(TimeoutError("primary"), ValueError("fallback"))
    with patch.object(engine, "_settings", _nvidia_settings(fallback="fallback-model")), \
         patch.object(engine, "_cache_client", FakeRedis), \
         patch.object(engine, "_get_nvidia_instructor_client", lambda: client):
        with pytest.raises(ValueError):
            engine._call_claude_structured("sys", "user", Answer)
    assert _models_called(client) == ["primary-model", "fallback-model"]


def test_raw_call_llm_also_falls_back():
    reply = MagicMock()
    reply.choices[0].message.content = "raw text"
    reply.usage = None
    raw = MagicMock()
    raw.chat.completions.create.side_effect = [TimeoutError("primary"), reply]
    with patch.object(engine, "_settings", _nvidia_settings(fallback="fallback-model")), \
         patch.object(engine, "_get_nvidia_client", lambda: raw):
        assert engine.call_llm("sys", "user") == "raw text"
    assert [c.kwargs["model"] for c in raw.chat.completions.create.call_args_list] == [
        "primary-model", "fallback-model"]


def test_provider_clients_carry_the_configured_timeout(monkeypatch):
    monkeypatch.setattr(engine, "_nvidia_client", None)
    built = MagicMock()
    with patch.object(engine.openai, "OpenAI", built):
        engine._get_nvidia_client()
    assert built.call_args.kwargs["timeout"] == engine._settings.llm_timeout_seconds
    assert engine._client.timeout == engine._settings.llm_timeout_seconds
    assert 0 < engine._settings.llm_timeout_seconds <= 300


def test_every_llm_request_passes_the_provider_guard(monkeypatch):
    from providers import guard
    from tailoring import engine

    seen = []
    monkeypatch.setattr(guard, "call", lambda provider, fn, **kw: seen.append(provider) or fn())
    result, model = engine._llm_request("m1", lambda model: f"ok:{model}")
    assert (result, model) == ("ok:m1", "m1")
    assert seen == ["llm"]


def test_a_spend_cap_refusal_is_raised_not_swallowed(monkeypatch):
    import pytest
    from providers import guard
    from tailoring import engine

    def refuse(provider, fn, **kw):
        raise guard.SpendCapReached("llm")

    monkeypatch.setattr(guard, "call", refuse)
    with pytest.raises(guard.SpendCapReached):
        engine._llm_request("m1", lambda model: "never")
