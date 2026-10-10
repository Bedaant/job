"""providers/guard.py: every outside call gets capped retries, a shared breaker, a rate limit
and (for paid providers) a daily spend cap. Redis is faked here; conftest blocks the real one."""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from providers import guard


class FakeRedis:
    def __init__(self):
        self.d = {}

    def incr(self, k):
        self.d[k] = int(self.d.get(k, 0)) + 1
        return self.d[k]

    def incrbyfloat(self, k, v):
        self.d[k] = float(self.d.get(k, 0)) + v
        return self.d[k]

    def get(self, k):
        v = self.d.get(k)
        return None if v is None else str(v).encode()

    def set(self, k, v, ex=None):
        self.d[k] = v

    def exists(self, k):
        return int(k in self.d)

    def delete(self, k):
        self.d.pop(k, None)

    def expire(self, k, s):
        pass


@pytest.fixture
def fake(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(guard, "_redis", lambda: r)
    getattr(guard, "_reset_local_state", lambda: None)()
    monkeypatch.setattr(guard.time, "sleep", lambda s: None)
    return r


def _transport_error():
    return httpx.ConnectError("down")


def test_retries_a_retryable_error_then_succeeds(fake):
    fn = MagicMock(side_effect=[_transport_error(), "ok"])
    assert guard.call("greenhouse", fn) == "ok"
    assert fn.call_count == 2


def test_does_not_retry_a_non_retryable_error(fake):
    fn = MagicMock(side_effect=ValueError("bad input"))
    with pytest.raises(ValueError):
        guard.call("greenhouse", fn)
    assert fn.call_count == 1


def test_a_4xx_does_not_retry_but_a_503_does(fake):
    req = httpx.Request("GET", "https://x")

    def status(code):
        return httpx.HTTPStatusError("e", request=req, response=httpx.Response(code, request=req))

    fn = MagicMock(side_effect=status(404))
    with pytest.raises(httpx.HTTPStatusError):
        guard.call("workday", fn)
    assert fn.call_count == 1
    fn = MagicMock(side_effect=[status(503), "ok"])
    assert guard.call("workday", fn) == "ok"


def test_breaker_opens_after_consecutive_failures_and_fails_fast(fake):
    fn = MagicMock(side_effect=_transport_error())
    for _ in range(guard.BREAKER_FAILURES):
        with pytest.raises(httpx.ConnectError):
            guard.call("lever", fn, retries=0)
    calls = fn.call_count
    with pytest.raises(guard.CircuitOpen):
        guard.call("lever", fn)
    assert fn.call_count == calls
    # Other providers are unaffected.
    assert guard.call("ashby", lambda: "ok") == "ok"


def test_a_success_resets_the_failure_count(fake):
    bad = MagicMock(side_effect=_transport_error())
    for _ in range(guard.BREAKER_FAILURES - 1):
        with pytest.raises(httpx.ConnectError):
            guard.call("lever", bad, retries=0)
    guard.call("lever", lambda: "ok")
    with pytest.raises(httpx.ConnectError):
        guard.call("lever", bad, retries=0)
    assert guard.call("lever", lambda: "still closed") == "still closed"


def test_spend_cap_refuses_before_calling_and_records_after(fake, monkeypatch):
    monkeypatch.setattr(guard, "_daily_cap", lambda p: 1.0)
    assert guard.call("apify", lambda: "ok", cost_usd=0.6) == "ok"
    fn = MagicMock()
    with pytest.raises(guard.SpendCapReached):
        guard.call("apify", fn, cost_usd=0.6)
    fn.assert_not_called()


def test_rate_limit_waits_for_the_next_window(fake, monkeypatch):
    monkeypatch.setitem(guard.RPM, "voyage", 2)
    slept, clock = [], [1000.0]
    monkeypatch.setattr(guard.time, "time", lambda: clock[0])

    def sleep(s):
        slept.append(s)
        clock[0] += s
    monkeypatch.setattr(guard.time, "sleep", sleep)
    for _ in range(3):
        guard.call("voyage", lambda: "ok")
    assert slept, "the third call in one minute must wait"


def test_redis_down_fails_open_rather_than_stopping_work(monkeypatch):
    def down():
        raise RuntimeError("redis unreachable")

    monkeypatch.setattr(guard, "_redis", down)
    assert guard.call("voyage", lambda: "ok", cost_usd=0.01) == "ok"


def test_voyage_client_has_a_timeout_and_goes_through_the_guard(fake, monkeypatch):
    from matching import embeddings

    monkeypatch.setattr(embeddings, "get_settings", lambda: MagicMock(voyage_api_key="k"))
    with patch.object(embeddings.voyageai, "Client") as client:
        client.return_value.embed.return_value = MagicMock(embeddings=[[0.1]])
        assert embeddings.embed_texts(["t"], input_type="document") == [[0.1]]
    assert client.call_args.kwargs.get("timeout")


def test_apify_refusal_is_logged_by_type_not_silent(fake, monkeypatch, caplog):
    from connectors import linkedin_posts

    monkeypatch.setattr(linkedin_posts, "_token", lambda: "t")
    monkeypatch.setattr(guard, "_daily_cap", lambda p: 0.0)
    with caplog.at_level("WARNING"):
        assert linkedin_posts.fetch_linkedin_posts(["#hiring"], rows=10) == []
    assert "SpendCapReached" in caplog.text


def test_llm_sdk_errors_are_classified_by_status_code(fake):
    class SDKError(Exception):
        def __init__(self, status_code):
            self.status_code = status_code

    fn = MagicMock(side_effect=[SDKError(529), "ok"])
    assert guard.call("llm", fn) == "ok"
    fn = MagicMock(side_effect=SDKError(400))
    with pytest.raises(SDKError):
        guard.call("llm", fn)
    assert fn.call_count == 1


def test_a_healthy_free_provider_costs_almost_no_redis_round_trips(fake, monkeypatch):
    """Redis is remote (~270 ms a round trip from a dev machine) and Workday makes one request
    per posting. Two round trips per successful call stretched a discovery run by minutes."""
    ops = []
    monkeypatch.setattr(guard, "_redis", lambda: ops.append(1) or fake)
    for _ in range(50):
        assert guard.call("workday:acme.wd1", lambda: "ok") == "ok"
    assert len(ops) <= 1


def test_a_breaker_opened_by_another_process_is_seen_within_the_cache_window(fake, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(guard.time, "monotonic", lambda: clock[0])
    assert guard.call("lever", lambda: "ok") == "ok"
    fake.set("guard:lever:open", 1)
    clock[0] += guard.BREAKER_CACHE_SECONDS + 0.1
    with pytest.raises(guard.CircuitOpen):
        guard.call("lever", lambda: "ok")
