"""RLS tenant context must survive a commit.

Found live on Neon: `SET LOCAL app.current_user_id` is transaction-scoped, so
after `db.commit()` the next statement ran with no tenant id and RLS hid the
row just written — `POST /profiles` 500'd on `db.refresh()`. SQLite has no RLS,
so these tests pin the mechanism rather than the database behaviour.
"""
from types import SimpleNamespace

from sqlalchemy import event
from sqlalchemy.orm import Session

from core.deps import _reapply_tenant


class _FakeConn:
    def __init__(self, dialect):
        self.dialect = SimpleNamespace(name=dialect)
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))


def test_every_new_transaction_gets_the_tenant_id_again():
    assert event.contains(Session, "after_begin", _reapply_tenant)
    conn = _FakeConn("postgresql")
    _reapply_tenant(SimpleNamespace(info={"current_user_id": "u1"}), None, conn)
    assert len(conn.calls) == 1
    sql, params = conn.calls[0]
    assert "app.current_user_id" in sql and params == {"uid": "u1"}


def test_no_tenant_id_on_sessions_without_a_user_or_off_postgres():
    conn = _FakeConn("postgresql")
    _reapply_tenant(SimpleNamespace(info={}), None, conn)  # workers, relay, signup
    sqlite = _FakeConn("sqlite")
    _reapply_tenant(SimpleNamespace(info={"current_user_id": "u1"}), None, sqlite)
    assert conn.calls == [] and sqlite.calls == []
