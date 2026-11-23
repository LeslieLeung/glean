"""Durable, bounded Jev classification independent of vectorization."""

from datetime import UTC, datetime
from typing import Any

import httpx
from arq import Retry
from pydantic import ValidationError
from sqlalchemy import select

from glean_core.schemas.jev import JevConfig
from glean_core.services import TypedConfigService
from glean_core.services.jev_service import article_text, classify_text
from glean_database.models import Entry, SystemConfig
from glean_database.session import get_session_context


async def enqueue_jev_classifications(ctx: dict[str, Any]) -> dict[str, int]:
    """Recover pending articles, including old articles and missed feed enqueues."""
    async with get_session_context() as session:
        config = await TypedConfigService(session).get(JevConfig)
        if not config.enabled or not config.api_key:
            return {"queued": 0}
        ids = list(
            (
                await session.scalars(
                    select(Entry.id)
                    .where(Entry.classification_status == "pending")
                    .order_by(Entry.created_at.desc(), Entry.id)
                    .limit(100)
                )
            ).all()
        )
    queued = 0
    for entry_id in ids:
        job = await ctx["redis"].enqueue_job(
            "classify_entry",
            entry_id,
            _job_id=f"jev:{entry_id}",
            _expires=600,
        )
        queued += job is not None
    return {"queued": queued}


async def classify_entry(ctx: dict[str, Any], entry_id: str) -> dict[str, str]:
    async with get_session_context() as session:
        config = await TypedConfigService(session).get(JevConfig)
        entry = await session.get(Entry, entry_id)
        if not config.enabled or not config.api_key or not entry:
            return {"status": "disabled"}
        if entry.classification_status != "pending":
            return {"status": entry.classification_status}
        text = article_text(entry.content or entry.summary or "")
        title, url = entry.title, entry.url

    result = None
    error = None
    status = "skipped"
    retry = False
    if len(text) >= config.min_text_length:
        try:
            result = await classify_text(config, text, title, url)
            status = "done"
        except (httpx.RequestError, ValueError) as exc:
            if isinstance(exc, httpx.RequestError):
                error = "Could not connect to the Jev server"
            elif isinstance(exc, ValidationError):
                error = "Jev returned an invalid classification result"
            else:
                error = str(exc)[:300]
            retry = ctx.get("job_try", 1) < 3
            status = "pending" if retry else "failed"

    async with get_session_context() as session:
        # Serialize completion with settings changes; discard stale responses.
        row = await session.scalar(
            select(SystemConfig).where(SystemConfig.key == JevConfig.NAMESPACE).with_for_update()
        )
        current = JevConfig.model_validate(row.value) if row else JevConfig()
        if not current.enabled or current.version != config.version:
            return {"status": "stale"}
        entry = await session.get(Entry, entry_id)
        if not entry:
            return {"status": "missing"}
        entry.classification_status = status
        entry.classification_error = error
        entry.classified_at = datetime.now(UTC)
        if result is not None:
            entry.classification_result = result.model_dump(mode="json")
        elif status == "skipped":
            entry.classification_result = None
    if retry:
        raise Retry(defer=60 * ctx.get("job_try", 1))
    return {"status": status}
