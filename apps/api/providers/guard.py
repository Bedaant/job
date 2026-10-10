"""One gate for every outside call: capped retries with jittered backoff (retryable errors only),
a per-provider rate limit, a circuit breaker and a daily USD cap, the last three shared across
processes through Redis.

    guard.call("voyage", lambda: client.embed(...), cost_usd=0.0004)

Redis trouble fails OPEN: the workers themselves run on Redis (RQ), so a guard that refused
whenever Redis blipped would stop all work to protect nothing.
Timeouts belong on the client (httpx `timeout=`, voyageai `timeout=`); `timeout(p)` supplies them.
"""
import logging
import random
import time
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

BREAKER_FAILURES = 5
BREAKER_OPEN_SECONDS = 300
MAX_RATE_WAIT_SECONDS = 60
# Redis is a network hop (~270 ms from a dev machine), so a healthy call must not pay for it:
# breaker state is re-read at most this often per process.
BREAKER_CACHE_SECONDS = 5.0
# Requests per minute, shared by every process. None = unlimited (ATS boards are paced
# per host in workers/jobs.py already).
RPM: dict[str, int | None] = {"voyage": 250, "apify": 30, "llm": 60}
TIMEOUTS = {"voyage": 60.0, "llm": 120.0}
DEFAULT_TIMEOUT = 30.0


class ProviderRefused(Exception):
    """The guard declined to call; the provider was not contacted."""


class CircuitOpen(ProviderRefused):
    pass


class SpendCapReached(ProviderRefused):
    pass


class RateLimitWaitExceeded(ProviderRefused):
    pass


def timeout(provider: str) -> float:
    return TIMEOUTS.get(provider, DEFAULT_TIMEOUT)


def _redis():
    from workers.jobs import get_redis_connection  # lazy: workers.jobs imports the connectors

    return get_redis_connection()


def _daily_cap(provider: str) -> float | None:
    from core.config import get_settings

    return getattr(get_settings(), f"daily_usd_cap_{provider}", None)


def _safe(op, default=None):
    try:
        return op(_redis())
    except Exception as exc:
        logger.warning("guard: redis unavailable (%s); proceeding unguarded", type(exc).__name__)
        return default


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    if isinstance(exc, httpx.TransportError):
        return True
    # anthropic / openai SDK errors carry status_code; their connection/timeout errors don't.
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    if type(exc).__name__ in ("APIConnectionError", "APITimeoutError"):
        return True
    try:
        import voyageai.error as ve

        return isinstance(exc, (ve.RateLimitError, ve.ServiceUnavailableError, ve.ServerError,
                                ve.Timeout, ve.APIConnectionError, ve.TryAgain))
    except ImportError:
        return False


_breaker_seen: dict[str, tuple[float, bool]] = {}  # provider -> (monotonic checked_at, open)
_failed_here: set[str] = set()  # providers this process recorded a failure for since a success


def _reset_local_state() -> None:
    _breaker_seen.clear()
    _failed_here.clear()


def _check_breaker(provider: str) -> None:
    now = time.monotonic()
    seen = _breaker_seen.get(provider)
    if seen is None or now - seen[0] > BREAKER_CACHE_SECONDS:
        seen = (now, bool(_safe(lambda r: r.exists(f"guard:{provider}:open"), 0)))
        _breaker_seen[provider] = seen
    if seen[1]:
        raise CircuitOpen(f"{provider} circuit open")


def _record_failure(provider: str) -> None:
    _failed_here.add(provider)

    def op(r):
        fails = r.incr(f"guard:{provider}:fails")
        r.expire(f"guard:{provider}:fails", BREAKER_OPEN_SECONDS)
        if fails >= BREAKER_FAILURES:
            r.set(f"guard:{provider}:open", 1, ex=BREAKER_OPEN_SECONDS)
            r.delete(f"guard:{provider}:fails")
            _breaker_seen[provider] = (time.monotonic(), True)
            logger.error("guard: %s circuit OPEN for %ss after %s failures",
                         provider, BREAKER_OPEN_SECONDS, fails)
    _safe(op)


def _spend_key(provider: str) -> str:
    return f"guard:{provider}:usd:{datetime.now(timezone.utc):%Y-%m-%d}"


def _check_spend(provider: str, cost_usd: float) -> None:
    cap = _daily_cap(provider)
    if cap is None or cost_usd <= 0:
        return
    spent = float(_safe(lambda r: r.get(_spend_key(provider)), None) or 0)
    if spent + cost_usd > cap:
        raise SpendCapReached(f"{provider} daily cap ${cap:.2f} reached (spent ${spent:.4f})")


def _record_spend(provider: str, cost_usd: float) -> None:
    if cost_usd <= 0:
        return

    def op(r):
        r.incrbyfloat(_spend_key(provider), cost_usd)
        r.expire(_spend_key(provider), 2 * 86400)
    _safe(op)


def _wait_for_rate(provider: str) -> None:
    limit = RPM.get(provider)
    if not limit:
        return
    waited = 0.0
    while True:
        window = int(time.time() // 60)
        key = f"guard:{provider}:rpm:{window}"

        def op(r):
            n = r.incr(key)
            r.expire(key, 120)
            return n
        if (_safe(op, 0) or 0) <= limit:
            return
        pause = 60 - time.time() % 60 + 0.05
        if waited + pause > MAX_RATE_WAIT_SECONDS:
            raise RateLimitWaitExceeded(f"{provider} over {limit}/min")
        time.sleep(pause)
        waited += pause


def call(provider: str, fn, *, cost_usd: float = 0.0, retries: int = 2):
    """Run fn() under the provider's guard. Raises ProviderRefused (provider not contacted)
    or fn's own exception after retries."""
    _check_breaker(provider)
    _check_spend(provider, cost_usd)
    for attempt in range(retries + 1):
        _wait_for_rate(provider)
        try:
            result = fn()
        except Exception as exc:
            if not _retryable(exc):
                raise
            _record_failure(provider)
            if attempt == retries:
                raise
            time.sleep(min(30.0, 2 ** attempt) * random.uniform(0.5, 1.5))
            _check_breaker(provider)
            continue
        if provider in _failed_here:
            _failed_here.discard(provider)
            _safe(lambda r: r.delete(f"guard:{provider}:fails"))
        _record_spend(provider, cost_usd)
        return result
