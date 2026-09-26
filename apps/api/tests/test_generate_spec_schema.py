"""apps/api/scripts/generate_spec_schema.py — dev tool, lean test.

Covers: (1) the generator reflects real model columns/types for a few tables,
(2) --check's diff logic actually detects drift on a synthetic mismatch.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from scripts import generate_spec_schema as gen  # noqa: E402


def test_generated_block_reflects_real_models():
    block = gen.generate_schema_block()
    # users: real column, real type, real FK-free PK
    assert "users:" in block
    assert "email  VARCHAR  NOT NULL  UNIQUE" in block
    # profiles: the exact column that drifted from SPEC.md before this script existed
    assert "profiles:" in block
    assert "work_auth  JSON" in block
    # resume_facts: period_from/period_to were missing from hand-written SPEC.md
    assert "resume_facts:" in block
    assert "period_from  DATE  NULL" in block
    assert "period_to  DATE  NULL" in block
    # never fabricate a SQL DEFAULT for a Python callable default
    assert "app-level callable gen_uuid()" in block
    assert "DEFAULT gen_random_uuid()" not in block


def test_check_mode_detects_synthetic_mismatch(tmp_path):
    spec = tmp_path / "SPEC.md"
    spec.write_text(
        f"# doc\n\nprose before\n\n{gen.BEGIN_MARKER}\n\nstale content, not the real schema\n\n"
        f"{gen.END_MARKER}\n\nprose after\n",
        encoding="utf-8",
    )
    text = spec.read_text(encoding="utf-8")
    existing = gen.current_block_in_spec(text)
    generated = gen.generate_schema_block()
    generated_inner = generated[len(gen.BEGIN_MARKER):-len(gen.END_MARKER)].strip("\n")
    assert existing != generated_inner  # the mismatch --check must catch

    # and once written, it matches (round-trip through the real write path)
    new_text = gen.write_generated_block(text, generated)
    assert gen.current_block_in_spec(new_text) == generated_inner
    # prose outside the markers is untouched
    assert "prose before" in new_text
    assert "prose after" in new_text
