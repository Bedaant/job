"""SSE stream (SPEC.md §2.6): replay every `events` row missed since
Last-Event-ID (bounded to the last 500), then subscribe live to the per-user
Redis channel events/relay.py publishes to.
"""
import json

import redis.asyncio as aioredis
from sqlalchemy.orm import Session

import models
from core.config import get_settings

REPLAY_LIMIT = 500


async def event_stream(db: Session, user_id: str, last_event_id: str | None):
    query = db.query(models.Event).filter(models.Event.user_id == user_id)
    if last_event_id:
        query = query.filter(models.Event.id > int(last_event_id))
    replay_rows = query.order_by(models.Event.id).limit(REPLAY_LIMIT).all()
    for row in replay_rows:
        yield {"id": str(row.id), "event": row.type, "data": json.dumps(row.payload)}

    redis = aioredis.from_url(get_settings().redis_url)
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"user:{user_id}")
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = json.loads(message["data"])
            yield {"id": str(data["id"]), "event": data["type"], "data": json.dumps(data["payload"])}
    finally:
        await pubsub.unsubscribe(f"user:{user_id}")
        await redis.aclose()
