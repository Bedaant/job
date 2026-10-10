"""Reusable guard: fail a test if an outside call runs while a session holds a transaction.

Every outside call goes through providers.guard.call, so wrapping it covers Voyage, Apify, the
ATS boards and the LLM. Neon kills a transaction idle for 5 min; SQLite never does, so without
this the bug only shows up in production (it cost three full discovery saves on 2026-10-10)."""
from contextlib import contextmanager
from unittest.mock import patch

from providers import guard


@contextmanager
def no_network_in_transaction(session):
    real = guard.call
    calls, violations = [], []

    def checked(provider, fn, **kwargs):
        calls.append(provider)
        if session.in_transaction():
            violations.append(provider)
            raise AssertionError(
                f"{provider} was called with a database transaction open; commit or roll back first")
        return real(provider, fn, **kwargs)

    with patch.object(guard, "call", checked):
        yield calls
    # Re-checked here because callers that tolerate failures (backfill) swallow the raise.
    assert not violations, f"outside call(s) inside a transaction: {violations}"
