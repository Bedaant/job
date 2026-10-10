from unittest.mock import patch

import pytest

import models
import observability
from core.config import get_settings
from tests.test_observability_ops import FakeRedis


@pytest.fixture(autouse=True)
def owner(monkeypatch):
    monkeypatch.setattr(get_settings(), "alert_email", "owner@example.com")


def test_canary_passes_through_the_real_pipeline_and_cleans_up(db_session):
    sent = []
    # Would fail loudly if the canary reached the embeddings provider.
    with patch("matching.embeddings.voyageai.Client", side_effect=AssertionError("network")):
        result = observability.run_canary(db_session, FakeRedis(), sender=lambda *a, **k: sent.append(a) or True)
    assert result["ok"] is True, result
    assert result["inserted"] == len(observability.CANARY_BOARD)
    assert result["updated_on_rerun"] == len(observability.CANARY_BOARD)
    assert db_session.query(models.Job).filter(models.Job.source == observability.CANARY_SOURCE).count() == 0
    assert sent == []


def test_canary_alerts_when_the_pipeline_returns_nothing(db_session):
    sent = []
    with patch("observability.upsert_jobs", return_value=(0, 0, 0)):
        result = observability.run_canary(
            db_session, FakeRedis(), sender=lambda to, subject, body, attachments=None: sent.append(subject) or True)
    assert result["ok"] is False
    assert len(sent) == 1 and "canary" in sent[0]
    assert db_session.query(models.Job).filter(models.Job.source == observability.CANARY_SOURCE).count() == 0
