"""Events-relay loop (ARCHITECTURE.md §4.6): drains unpublished `events` rows
to Redis pub/sub, then stamps published_at in the same transaction as the
publish — `relay_once` is the unit the worker process calls in a loop.
"""
import json
from datetime import datetime

from redis import Redis
from sqlalchemy.orm import Session

import models

RELAY_BATCH_SIZE = 100


def relay_once(db: Session, redis: Redis) -> int:
    rows = (
        db.query(models.Event)
        .filter(models.Event.published_at.is_(None))
        .order_by(models.Event.id)
        .with_for_update(skip_locked=True)
        .limit(RELAY_BATCH_SIZE)
        .all()
    )
    if not rows:
        return 0

    for row in rows:
        redis.publish(
            f"user:{row.user_id}",
            json.dumps({"id": row.id, "type": row.type, "payload": row.payload}),
        )
        row.published_at = datetime.utcnow()

    db.commit()
    return len(rows)
