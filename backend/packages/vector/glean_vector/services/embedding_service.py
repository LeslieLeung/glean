"""Embedding generation service."""

import asyncio
import contextlib
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import RedisKeys, get_logger
from glean_core.published_at import effective_published_at
from glean_database.models import Entry
from glean_vector.clients.embedding_client import EmbeddingClient
from glean_vector.clients.rate_limiter import RateLimitDeadlineError
from glean_vector.clients.vector_store import VectorStoreClient

logger = get_logger(__name__)


class StaleEmbeddingGenerationError(RuntimeError):
    """Raised when a worker belongs to an obsolete config/rebuild generation."""


@dataclass(frozen=True)
class _EmbeddingInput:
    """Batch input that survives session commits, rollbacks and generation checks."""

    id: str
    feed_id: str
    published_at: datetime | None
    created_at: datetime | None
    author: str | None
    embedding_status: str
    text: str


def _vector_published_at(entry: Entry | _EmbeddingInput) -> datetime | None:
    """Feed date, or the fetch time when that date is missing or still far ahead."""
    created_at = entry.created_at
    if isinstance(created_at, datetime):
        return effective_published_at(entry.published_at, created_at)
    return entry.published_at


class EmbeddingService:
    """
    Service for generating and managing entry embeddings.

    Handles the complete embedding lifecycle:
    1. Extract text from entry
    2. Generate embedding via API
    3. Store in vector backend
    4. Update entry status in PostgreSQL
    """

    def __init__(
        self,
        db_session: AsyncSession,
        embedding_client: EmbeddingClient,
        vector_client: VectorStoreClient,
        generation_guard: Callable[[], Awaitable[bool]] | None = None,
        generation_lock: Any | None = None,
    ) -> None:
        """
        Initialize embedding service.

        Args:
            db_session: Database session
            embedding_client: Embedding API client
            vector_client: Vector database client
            generation_guard: Async check executed immediately before a vector write.
            generation_lock: Redis-compatible client used to serialize writes
                against collection recreation.
        """
        self.db = db_session
        self.embedding_client = embedding_client
        self.vector_client = vector_client
        self.generation_guard = generation_guard
        self.generation_lock = generation_lock

    def _extract_text(self, entry: Entry) -> str:
        """
        Extract text content from entry for embedding.

        Args:
            entry: Entry model

        Returns:
            Cleaned text content
        """
        # Combine title and content/summary
        parts = [entry.title]

        if entry.content:
            # Strip HTML tags from content
            text = re.sub(r"<[^>]+>", "", entry.content)
            parts.append(text)
        elif entry.summary:
            text = re.sub(r"<[^>]+>", "", entry.summary)
            parts.append(text)

        full_text = " ".join(parts)

        # Clean whitespace
        full_text = re.sub(r"\s+", " ", full_text).strip()

        # Truncate if too long (OpenAI has ~8k token limit for embeddings)
        # Rough estimate: 1 token ≈ 4 chars
        max_chars = 30000
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars]

        return full_text

    def _calculate_word_count(self, text: str) -> int:
        """
        Calculate word count from text.

        Args:
            text: Input text

        Returns:
            Word count
        """
        words = re.findall(r"\w+", text)
        return len(words)

    async def generate_embedding(
        self,
        entry_id: str,
        *,
        deadline: float | None = None,
    ) -> bool:
        """
        Generate embedding for a single entry.

        Args:
            entry_id: Entry UUID
            deadline: Optional monotonic timestamp to stop waiting on rate limits

        Returns:
            True if successful, False otherwise
        """
        # Get entry from database
        result = await self.db.execute(
            select(Entry).where(Entry.id == entry_id).with_for_update(skip_locked=True)
        )
        entry = result.scalar_one_or_none()

        if not entry:
            logger.warning(
                "Entry not found for embedding generation",
                extra={"entry_id": entry_id},
            )
            return False

        # Skip if already processed
        if entry.embedding_status == "done":
            return True
        if entry.embedding_status == "processing":
            return False

        # Update status to processing
        await self.db.execute(
            update(Entry)
            .where(Entry.id == entry_id)
            .values(embedding_status="processing", embedding_error=None)
        )
        await self.db.flush()
        # Release the entry row before waiting on the provider or Redis fence.
        # Rebuilds acquire that fence before updating entries; retaining this
        # row lock would invert the lock order and stall both jobs.
        await self.db.commit()

        # Extract text (content-level issue → return False, no exception)
        text = self._extract_text(entry)
        word_count = self._calculate_word_count(text)

        if not text:
            await self._mark_failed_fenced(entry_id, "No text content to embed")
            return False

        try:
            # Generate embedding via provider API
            embedding, _ = await self.embedding_client.generate_embedding(
                text,
                deadline=deadline,
            )

            # Detect language (simple heuristic)
            language = self._detect_language(text)

            await self._store_embedding(
                entry=entry,
                embedding=embedding,
                language=language,
                word_count=word_count,
            )
            return True

        except StaleEmbeddingGenerationError:
            # Do not mark an entry failed when the job itself is obsolete.
            # Batch callers restore all unprocessed claims to pending.
            raise
        except RateLimitDeadlineError:
            raise
        except Exception as e:
            # Persist the entry error and let the single-entry job retry.
            logger.error(f"Failed to generate embedding for entry {entry_id}: {e}")
            await self._mark_failed_fenced(entry_id, str(e))
            raise

    async def _store_embedding(
        self,
        *,
        entry: Entry | _EmbeddingInput,
        embedding: list[float],
        language: str,
        word_count: int,
    ) -> None:
        """Fence the vector write against collection recreation."""
        entry_id = entry.id
        feed_id = entry.feed_id
        published_at = _vector_published_at(entry)
        author = entry.author or ""
        lock = None
        acquired = False
        if self.generation_lock is not None:
            lock = self.generation_lock.lock(
                RedisKeys.REBUILD_LOCK_KEY,
                timeout=RedisKeys.REBUILD_LOCK_TIMEOUT,
                blocking_timeout=RedisKeys.REBUILD_LOCK_TIMEOUT,
            )
            acquired = await lock.acquire()
            if not acquired:
                raise StaleEmbeddingGenerationError("Could not acquire embedding generation fence")

        try:
            if self.generation_guard is not None and not await self.generation_guard():
                raise StaleEmbeddingGenerationError("Embedding generation is stale")
            await self.vector_client.insert_entry_embedding(
                entry_id=entry_id,
                embedding=embedding,
                feed_id=feed_id,
                published_at=published_at,
                language=language,
                word_count=word_count,
                author=author,
            )
            # Commit vector presence and the relational done marker under the
            # same rebuild fence. Otherwise a rebuild can clear the vector and
            # mark the row pending, then an old job can flip it back to done.
            if self.generation_guard is not None and not await self.generation_guard():
                raise StaleEmbeddingGenerationError(
                    "Embedding generation changed after vector write"
                )
            await self.db.execute(
                update(Entry)
                .where(Entry.id == entry_id)
                .values(
                    embedding_status="done",
                    embedding_at=datetime.now(UTC),
                    word_count=word_count,
                    embedding_error=None,
                )
            )
            await self.db.commit()
        finally:
            if lock is not None and acquired:
                with contextlib.suppress(Exception):
                    await lock.release()

    async def _mark_failed(self, entry_id: str, error: str) -> None:
        """Mark entry embedding as failed."""
        await self.db.execute(
            update(Entry)
            .where(Entry.id == entry_id, Entry.embedding_status == "processing")
            .values(embedding_status="failed", embedding_error=error)
        )
        await self.db.flush()

    async def _mark_failed_fenced(self, entry_id: str, error: str) -> None:
        """Persist a failure only while this config generation still owns it."""
        lock = None
        acquired = False
        if self.generation_lock is not None:
            lock = self.generation_lock.lock(
                RedisKeys.REBUILD_LOCK_KEY,
                timeout=RedisKeys.REBUILD_LOCK_TIMEOUT,
                blocking_timeout=RedisKeys.REBUILD_LOCK_TIMEOUT,
            )
            acquired = await lock.acquire()
            if not acquired:
                raise StaleEmbeddingGenerationError(
                    "Could not acquire embedding failure generation fence"
                )
        try:
            if self.generation_guard is not None and not await self.generation_guard():
                raise StaleEmbeddingGenerationError(
                    "Embedding generation changed while handling a failure"
                )
            await self._mark_failed_safe(entry_id, error)
        finally:
            if lock is not None and acquired:
                with contextlib.suppress(Exception):
                    await lock.release()

    async def _mark_failed_safe(self, entry_id: str, error: str) -> None:
        """Durably mark entry as failed, recovering a poisoned session if needed.

        When a prior flush/execute fails, asyncpg puts the connection into a
        failed-transaction state where all subsequent SQL is rejected.  This
        helper rolls back the aborted transaction before writing and committing
        the UPDATE so later worker error handling cannot discard the status.

        Side-effect: a rollback discards any unflushed changes on the session
        (the caller should commit per-entry to minimise data loss).
        """
        for attempt in range(2):
            try:
                await self.db.rollback()
                await self._mark_failed(entry_id, error)
                await self.db.commit()
                return
            except Exception:
                if attempt == 0:
                    continue
                logger.warning(
                    "Could not mark entry as failed after session recovery",
                    extra={"entry_id": entry_id},
                    exc_info=True,
                )

    def _detect_language(self, text: str) -> str:
        """
        Simple language detection.

        Args:
            text: Input text

        Returns:
            Language code (en, zh, ja, etc.)
        """
        # Simple heuristic: check for CJK characters
        cjk_pattern = re.compile(r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]")
        cjk_matches = len(cjk_pattern.findall(text))

        if cjk_matches > 10:
            # Distinguish between Chinese and Japanese
            hiragana_pattern = re.compile(r"[\u3040-\u309f]")
            if hiragana_pattern.search(text):
                return "ja"
            return "zh"

        return "en"

    async def batch_generate(
        self,
        limit: int = 100,
        *,
        chunk_size: int | None = None,
        deadline: float | None = None,
    ) -> dict[str, int]:
        """
        Generate embeddings for pending entries in batch.

        Claims are incremental (one provider request at a time) so a job
        timeout cannot leave a large processing pile behind. Provider calls
        use the configured embedding batch size.

        Args:
            limit: Maximum number of entries to process
            chunk_size: Max texts per provider request (defaults to client batch_size)
            deadline: Monotonic timestamp to stop claiming more work

        Returns:
            Dictionary with processed and failed counts
        """
        remaining_quota = max(0, limit)
        request_chunk = (
            chunk_size
            if chunk_size is not None
            else getattr(self.embedding_client, "batch_size", 20)
        )
        if not isinstance(request_chunk, int) or request_chunk <= 0:
            request_chunk = 20
        processed = 0
        failed = 0

        while remaining_quota > 0:
            if deadline is not None and time.monotonic() >= deadline:
                break
            try:
                await self.embedding_client.acquire_rate_limit(deadline=deadline)
            except RateLimitDeadlineError:
                break

            take = min(remaining_quota, request_chunk)
            entry_ids = await self._claim_entries(take)
            if not entry_ids:
                break

            try:
                chunk_processed, chunk_failed = await self._embed_claimed_entries(
                    entry_ids,
                    already_acquired=True,
                    deadline=deadline,
                )
            except StaleEmbeddingGenerationError:
                with contextlib.suppress(Exception):
                    await self.db.rollback()
                await self.restore_claimed_entries(entry_ids)
                break
            except RateLimitDeadlineError:
                with contextlib.suppress(Exception):
                    await self.db.rollback()
                await self.restore_claimed_entries(entry_ids)
                break
            except asyncio.CancelledError:
                with contextlib.suppress(Exception):
                    await self.db.rollback()
                with contextlib.suppress(Exception):
                    await self.restore_claimed_entries(entry_ids)
                raise
            except Exception:
                logger.error(
                    "Unexpected error while embedding claimed entries",
                    extra={"entry_count": len(entry_ids)},
                    exc_info=True,
                )
                with contextlib.suppress(Exception):
                    await self.db.rollback()
                await self.restore_claimed_entries(entry_ids)
                remaining_quota -= len(entry_ids)
                continue

            processed += chunk_processed
            failed += chunk_failed
            remaining_quota -= len(entry_ids)

        return {"processed": processed, "failed": failed}

    async def _claim_entries(self, limit: int) -> list[str]:
        """Atomically claim a small disjoint slice of the embedding queue."""
        claim_result = await self.db.execute(
            select(Entry.id)
            .where(Entry.embedding_status == "pending")
            .order_by(Entry.created_at.desc(), Entry.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        entry_ids = [row[0] for row in claim_result.all()]
        if not entry_ids:
            return []

        await self.db.execute(
            update(Entry)
            .where(Entry.id.in_(entry_ids))
            .values(embedding_status="processing", embedding_error=None)
        )
        await self.db.commit()
        return entry_ids

    async def _embed_claimed_entries(
        self,
        entry_ids: Sequence[str],
        *,
        already_acquired: bool,
        deadline: float | None,
    ) -> tuple[int, int]:
        """Embed a claimed chunk with one provider request, then store each vector."""
        result = await self.db.execute(select(Entry).where(Entry.id.in_(entry_ids)))
        # Snapshot every input before processing any item. A failure rollback
        # expires all ORM instances, including the untouched remainder of this
        # chunk; later synchronous attribute access would raise MissingGreenlet.
        entries_by_id = {
            entry.id: _EmbeddingInput(
                id=entry.id,
                feed_id=entry.feed_id,
                published_at=entry.published_at,
                created_at=entry.created_at,
                author=entry.author,
                embedding_status=entry.embedding_status,
                text=self._extract_text(entry),
            )
            for entry in result.scalars().all()
        }

        processed = 0
        failed = 0
        embeddable: list[tuple[_EmbeddingInput, str, int]] = []

        for entry_id in entry_ids:
            entry = entries_by_id.get(entry_id)
            if not entry:
                failed += 1
                continue
            if entry.embedding_status == "done":
                processed += 1
                continue
            text = entry.text
            if not text:
                await self._mark_failed_fenced(entry_id, "No text content to embed")
                failed += 1
                continue
            embeddable.append((entry, text, self._calculate_word_count(text)))

        if not embeddable:
            return processed, failed

        texts = [text for _, text, _ in embeddable]
        try:
            if already_acquired:
                embeddings, _ = await self.embedding_client.generate_embeddings_batch_acquired(
                    texts
                )
            else:
                embeddings, _ = await self.embedding_client.generate_embeddings_batch(
                    texts, deadline=deadline
                )
            if len(embeddings) != len(embeddable):
                raise RuntimeError(
                    f"Embedding batch size mismatch: expected {len(embeddable)}, got {len(embeddings)}"
                )
        except (StaleEmbeddingGenerationError, RateLimitDeadlineError, asyncio.CancelledError):
            raise
        except Exception as error:
            # Some providers reject the entire input array for one bad article.
            # Give each article two individual calls after the failed batch.
            logger.warning(
                "Embedding batch rejected; retrying articles individually",
                extra={"entry_count": len(texts), "error": str(error)},
            )
            embeddings = [None] * len(embeddable)

        for (entry, text, word_count), embedding in zip(embeddable, embeddings, strict=True):
            try:
                if embedding is None:
                    embedding = await self._retry_single_input(text, deadline)
                await self._store_with_retry(entry, embedding, text, word_count)
                processed += 1
            except (StaleEmbeddingGenerationError, RateLimitDeadlineError, asyncio.CancelledError):
                raise
            except Exception as error:
                logger.warning(
                    "Article embedding failed after retries",
                    extra={"entry_id": entry.id, "error": str(error)},
                )
                await self._mark_failed_fenced(entry.id, str(error))
                failed += 1

        return processed, failed

    async def _retry_single_input(self, text: str, deadline: float | None) -> list[float]:
        for attempt in range(2):
            try:
                embedding, _ = await self.embedding_client.generate_embedding(
                    text, deadline=deadline
                )
                return embedding
            except (StaleEmbeddingGenerationError, RateLimitDeadlineError, asyncio.CancelledError):
                raise
            except Exception:
                if attempt == 1:
                    raise
        raise AssertionError("Unreachable retry state")

    async def _store_with_retry(
        self, entry: _EmbeddingInput, embedding: list[float], text: str, word_count: int
    ) -> None:
        language = self._detect_language(text)
        for attempt in range(3):
            try:
                await self._store_embedding(
                    entry=entry, embedding=embedding, language=language, word_count=word_count
                )
                return
            except (StaleEmbeddingGenerationError, asyncio.CancelledError):
                raise
            except Exception:
                await self.db.rollback()
                if attempt == 2:
                    raise

    async def restore_claimed_entries(self, entry_ids: list[str]) -> None:
        """Return stale generation claims to the pending queue."""
        if not entry_ids:
            return
        await self.db.execute(
            update(Entry)
            .where(
                Entry.id.in_(entry_ids),
                Entry.embedding_status == "processing",
            )
            .values(
                embedding_status="pending",
                embedding_error=None,
            )
        )
        await self.db.commit()

    async def delete_embedding(self, entry_id: str) -> None:
        """
        Delete embedding for an entry.

        Args:
            entry_id: Entry UUID
        """
        # Delete from vector backend
        await self.vector_client.delete_entry_embedding(entry_id)

        # Update entry status
        await self.db.execute(
            update(Entry)
            .where(Entry.id == entry_id)
            .values(
                embedding_status="pending",
                embedding_at=None,
                embedding_error=None,
            )
        )
        await self.db.flush()
