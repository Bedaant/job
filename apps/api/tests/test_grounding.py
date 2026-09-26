"""core/grounding.py: the single reusable check for "never trust an LLM to
reference an id it wasn't actually given." Extracted from two independent
instances of the same defensive pattern — tailoring/engine.py's
Bullet.source_fact_ids field_validator, and formfill/map_fields.py's
implicit dict-lookup-drop on mapping_by_id. See WORKLOG.md for the refactor.
"""
import pytest

from core.grounding import validate_ids_against_known_set


def test_returns_ids_unchanged_when_all_known():
    ids = ["f1", "f2"]
    result = validate_ids_against_known_set(ids, {"f1", "f2", "f3"}, field_name="source_fact_ids")
    assert result == ids


def test_returns_empty_list_unchanged():
    result = validate_ids_against_known_set([], {"f1"}, field_name="source_fact_ids")
    assert result == []


def test_raises_value_error_naming_the_invented_id():
    with pytest.raises(ValueError, match="not-a-real-id"):
        validate_ids_against_known_set(["not-a-real-id"], {"f1", "f2"}, field_name="source_fact_ids")


def test_raises_value_error_naming_all_invented_ids():
    with pytest.raises(ValueError) as exc_info:
        validate_ids_against_known_set(["bad1", "bad2"], {"f1"}, field_name="source_fact_ids")
    assert "bad1" in str(exc_info.value)
    assert "bad2" in str(exc_info.value)


def test_error_message_names_the_field():
    with pytest.raises(ValueError, match="field_id"):
        validate_ids_against_known_set(["ghost"], {"f1"}, field_name="field_id")


def test_partial_overlap_raises_naming_only_the_unknown_id():
    with pytest.raises(ValueError) as exc_info:
        validate_ids_against_known_set(["f1", "ghost"], {"f1", "f2"}, field_name="field_id")
    assert "ghost" in str(exc_info.value)
    assert "f1" not in str(exc_info.value)
