"""Generate docs/SPEC.md §1's schema block from the real SQLAlchemy models.

Why this exists: SPEC.md §1 used to be hand-written DDL prose that drifted from
apps/api/models.py three separate times in one session (missing columns, a
CHECK constraint that disagreed with the API, a type claimed in prose that
wasn't what the code actually used). This script is the fix: it introspects
models.py directly (no DB connection, ever) and produces the block that goes
between the markers in SPEC.md, so drift becomes a failing `--check` instead
of something an agent stumbles into later.

Usage:
    python scripts/generate_spec_schema.py            # regenerate SPEC.md in place
    python scripts/generate_spec_schema.py --check     # exit 1 if SPEC.md is stale, write nothing
"""
import argparse
import sys
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[1]  # apps/api — models.py/database.py live here
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from sqlalchemy import Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.schema import ColumnDefault, ForeignKeyConstraint, PrimaryKeyConstraint, UniqueConstraint

import models  # noqa: F401 -- import registers every model on Base.metadata
from database import Base

BEGIN_MARKER = "<!-- BEGIN GENERATED SCHEMA (apps/api/scripts/generate_spec_schema.py) -->"
END_MARKER = "<!-- END GENERATED SCHEMA -->"
SPEC_PATH = Path(__file__).resolve().parents[3] / "docs" / "SPEC.md"

_DIALECT = postgresql.dialect()


def _column_type(column) -> str:
    try:
        return column.type.compile(dialect=_DIALECT)
    except Exception:
        return str(column.type)


def _default_comment(column) -> str | None:
    """Never fabricate a DDL DEFAULT. Only render one for a literal scalar;
    anything else (a Python callable like gen_uuid/dict/list/datetime.utcnow)
    is described honestly as app-level, not translated into fake SQL."""
    d = column.default
    if d is None:
        return None
    if isinstance(d, ColumnDefault) and d.is_scalar:
        return f"default {d.arg!r} (app-level, not a DB DEFAULT)"
    if isinstance(d, ColumnDefault) and d.is_callable:
        fn = getattr(d.arg, "__name__", repr(d.arg))
        return f"default: app-level callable {fn}() — not a DB DEFAULT, set by the ORM on insert"
    return "has a default (unrecognized default type, see models.py)"


def _foreign_key_note(column) -> str | None:
    fks = list(column.foreign_keys)
    if not fks:
        return None
    fk = fks[0]
    note = f"FK -> {fk.target_fullname}"
    if fk.ondelete:
        note += f" ON DELETE {fk.ondelete}"
    return note


def _table_level_constraints(table: Table) -> list[str]:
    lines = []
    for c in table.constraints:
        if isinstance(c, PrimaryKeyConstraint):
            continue  # already shown per-column
        if isinstance(c, ForeignKeyConstraint):
            continue  # already shown per-column
        if isinstance(c, UniqueConstraint):
            cols = ", ".join(col.name for col in c.columns)
            if len(c.columns) > 1:
                lines.append(f"  UNIQUE ({cols})")
    return lines


def render_table(table: Table) -> str:
    out = [f"{table.name}:"]
    for column in table.columns:
        parts = [f"  {column.name}", _column_type(column)]
        parts.append("NOT NULL" if not column.nullable else "NULL")
        if column.primary_key:
            parts.append("PRIMARY KEY")
        if column.unique and not column.primary_key:
            parts.append("UNIQUE")
        line = "  ".join(parts)
        annotations = [n for n in (_foreign_key_note(column), _default_comment(column)) if n]
        if annotations:
            line += "  -- " + "; ".join(annotations)
        out.append(line)
    out.extend(_table_level_constraints(table))
    return "\n".join(out)


def generate_schema_block() -> str:
    """The full text that goes between BEGIN/END markers, markers included."""
    tables = Base.metadata.tables  # insertion order == declaration order in models.py
    body = "\n\n".join(render_table(t) for t in tables.values())
    header = (
        "This block is generated from `apps/api/models.py` by "
        "`apps/api/scripts/generate_spec_schema.py` — do not hand-edit it, "
        "run the script instead (`--check` verifies it's current, no args regenerates).\n"
        "Types are compiled against the real Postgres dialect (Neon). Enum columns "
        "(`persona`, `applicationstatus`) become native Postgres ENUM types, not "
        "VARCHAR+CHECK. Comments after `--` describe app-level (ORM) defaults honestly "
        "instead of inventing a SQL DEFAULT that doesn't exist."
    )
    return f"{BEGIN_MARKER}\n\n{header}\n\n```text\n{body}\n```\n\n{END_MARKER}"


def _split_spec(text: str) -> tuple[str, str, str]:
    """Return (before, between, after) split on the marker lines. `between`
    excludes the marker lines themselves. Raises if markers are missing/out
    of order — this script only ever replaces what's between them."""
    try:
        begin_idx = text.index(BEGIN_MARKER)
        end_idx = text.index(END_MARKER, begin_idx)
    except ValueError as e:
        raise SystemExit(
            f"SPEC.md is missing {BEGIN_MARKER!r} / {END_MARKER!r} markers — "
            "cannot safely regenerate. Add them around §1 first."
        ) from e
    before = text[:begin_idx]
    after = text[end_idx + len(END_MARKER):]
    between = text[begin_idx + len(BEGIN_MARKER):end_idx]
    return before, between, after


def current_block_in_spec(spec_text: str) -> str:
    before, between, after = _split_spec(spec_text)
    return between.strip("\n")


def write_generated_block(spec_text: str, new_block: str) -> str:
    before, _between, after = _split_spec(spec_text)
    # new_block already includes the markers; strip our own copies from before/after boundary.
    inner = new_block[len(BEGIN_MARKER):-len(END_MARKER)].strip("\n")
    return f"{before}{BEGIN_MARKER}\n\n{inner}\n\n{END_MARKER}{after}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify SPEC.md is up to date; write nothing")
    args = parser.parse_args()

    generated = generate_schema_block()
    generated_inner = generated[len(BEGIN_MARKER):-len(END_MARKER)].strip("\n")

    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    existing_inner = current_block_in_spec(spec_text)

    if args.check:
        if existing_inner == generated_inner:
            print(f"OK: {SPEC_PATH} schema block is up to date with models.py")
            return 0
        print(f"STALE: {SPEC_PATH}'s generated schema block does not match models.py.")
        print("Run `python scripts/generate_spec_schema.py` (no args) to regenerate.")
        print("--- current SPEC.md block ---")
        print(existing_inner)
        print("--- would generate ---")
        print(generated_inner)
        return 1

    new_text = write_generated_block(spec_text, generated)
    if new_text == spec_text:
        print(f"No change: {SPEC_PATH} already up to date.")
        return 0
    SPEC_PATH.write_text(new_text, encoding="utf-8")
    print(f"Wrote generated schema block to {SPEC_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
