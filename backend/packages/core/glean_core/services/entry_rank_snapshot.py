"""Short-lived ordered snapshots for the Smart reader."""

import json
from dataclasses import dataclass
from uuid import UUID, uuid4

from arq.connections import ArqRedis
from pydantic import BaseModel

from glean_core.schemas.entry import RecommendationReason

from .entry_ranker import RankedEntry

SNAPSHOT_TTL_SECONDS = 1800


class SmartCursorExpiredError(ValueError):
    """The cursor cannot be used to continue this Smart list."""


SnapshotEntry = tuple[str, float, RecommendationReason]


class _Snapshot(BaseModel):
    scope: str
    entries: list[SnapshotEntry]


@dataclass(frozen=True)
class SmartSnapshot:
    id: str
    entries: list[SnapshotEntry]
    offset: int = 0

    def cursor(self, offset: int) -> str | None:
        return f"{self.id}.{offset}" if offset < len(self.entries) else None

    @classmethod
    async def create(
        cls, redis: ArqRedis, scope: str, ranked: list[RankedEntry]
    ) -> "SmartSnapshot":
        snapshot = cls(uuid4().hex, [(entry.id, entry.score, entry.reason) for entry in ranked])
        payload = _Snapshot(scope=scope, entries=snapshot.entries).model_dump_json()
        await redis.setex(f"glean:smart:{snapshot.id}", SNAPSHOT_TTL_SECONDS, payload)
        return snapshot

    @classmethod
    async def load(cls, redis: ArqRedis, scope: str, cursor: str) -> "SmartSnapshot":
        raw_id, _, raw_offset = cursor.partition(".")
        try:
            snapshot_id = UUID(hex=raw_id).hex
            offset = int(raw_offset)
        except ValueError as exc:
            raise SmartCursorExpiredError from exc
        payload = await redis.get(f"glean:smart:{snapshot_id}")
        if payload is None:
            raise SmartCursorExpiredError
        try:
            snapshot = _Snapshot.model_validate_json(payload)
        except (ValueError, TypeError) as exc:
            raise SmartCursorExpiredError from exc
        if snapshot.scope != scope or not 0 <= offset < len(snapshot.entries):
            raise SmartCursorExpiredError
        return cls(snapshot_id, snapshot.entries, offset)


def smart_scope(
    user_id: str,
    feed_id: str | None,
    folder_id: str | None,
    is_read: bool | None,
    is_liked: bool | None,
    read_later: bool | None,
    global_smart: bool,
    content_category_ids: list[str] | None = None,
) -> str:
    scope = [user_id, feed_id, folder_id, is_read, is_liked, read_later, global_smart]
    if content_category_ids is not None:
        return json.dumps([*scope, content_category_ids])
    return json.dumps(scope)
