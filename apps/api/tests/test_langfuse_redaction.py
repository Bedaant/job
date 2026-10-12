"""NEXT-WORK-PLAN P1 #13: what reaches Langfuse carries no raw email or phone.

Mocked at the network boundary: the real Langfuse client and the real `@observe` hook
run, and only `OTLPSpanExporter.export` (the call that would POST the spans) is
captured instead of sent. The LLM itself is stubbed.
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

from langfuse._client.resource_manager import LangfuseResourceManager
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import SpanExportResult

from tailoring import engine

EMAIL, PHONE = "priya.sharma@gmail.com", "+91 98765 43210"
PROMPT = f"CANDIDATE: reach me at {EMAIL} or {PHONE}. Facts: shipped an inventory tracker."


def _exported(monkeypatch, call):
    sent = []

    def capture(self, spans):
        sent.extend(spans)
        return SpanExportResult.SUCCESS

    # One key for the whole suite: a second key makes @observe skip tracing as "multi-project".
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-suite")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-suite")
    monkeypatch.setenv("LANGFUSE_HOST", "http://langfuse.invalid")
    with patch.object(OTLPSpanExporter, "export", capture):
        client = engine._tracing_client()
        monkeypatch.setattr(engine, "_langfuse", client)
        try:
            call()
            client.flush()
        finally:
            # Shut the client down while export is still captured, so no later test traces for real.
            LangfuseResourceManager.reset()
    assert sent, "nothing was exported — the test would pass vacuously"
    return json.dumps([dict(s.attributes) for s in sent], default=str)


def test_plain_llm_call_trace_has_no_raw_email_or_phone(monkeypatch):
    reply = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=f"Dear team, contact {EMAIL}.")],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    monkeypatch.setattr(engine, "_llm_request", lambda model, attempt: (reply, "m"))
    payload = _exported(monkeypatch, lambda: engine.call_llm("system", PROMPT))
    assert EMAIL not in payload and "98765" not in payload
    assert "inventory tracker" in payload  # redacted, not dropped wholesale


def test_structured_llm_call_trace_has_no_raw_email_or_phone(monkeypatch):
    result = engine.TruthCheckResult(unsupported_claims=[f"call {PHONE}"])
    monkeypatch.setattr(engine, "_llm_request", lambda model, attempt: (result, "m"))
    monkeypatch.setattr(engine, "_cache_get", lambda *a: None)
    monkeypatch.setattr(engine, "_cache_set", lambda *a: None)
    payload = _exported(
        monkeypatch, lambda: engine._call_claude_structured("system", PROMPT, engine.TruthCheckResult)
    )
    assert EMAIL not in payload and "98765" not in payload
