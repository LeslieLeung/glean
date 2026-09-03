"""Embedding generation service."""

import contextlib
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, union, update
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import RedisKeys, get_logger
from glean_core.services.preference_dirty_service import mark_preferences_dirty
from glean_database.models import Bookmark, Entry, UserEntry
from glean_vector.clients.embedding_client import EmbeddingClient
from glean_vector.clients.vector_store import VectorStoreClient

logger = get_logger(__name__)


class StaleEmbeddingGenerationError(RuntimeError):
    """Raised when a worker belongs to an obsolete config/rebuild generation."""


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

    async def generate_embedding(self, entry_id: str) -> bool:
        """
        Generate embedding for a single entry.

        Args:
            entry_id: Entry UUID

        Returns:
            True if successful, False otherwise
        """
        # Get entry from database
        result = await self.db.execute(select(Entry).where(Entry.id == entry_id))
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

        # Update status to processing
        await self.db.execute(
            update(Entry)
            .where(Entry.id == entry_id)
            .values(embedding_status="processing", embedding_error=None)
        )
        await self.db.flush()

        # Extract text (content-level issue → return False, no exception)
        text = self._extract_text(entry)
        word_count = self._calculate_word_count(text)

        if not text:
            await self._mark_failed_fenced(entry_id, "No text content to embed")
            return False

        try:
            # Generate embedding via provider API
            embedding, _ = await self.embedding_client.generate_embedding(text)

            # Detect language (simple heuristic)
            language = self._detect_language(text)

            affected_user_ids = await self._store_embedding(
                entry=entry,
                embedding=embedding,
                language=language,
                word_count=word_count,
            )
            await self._mark_affected_preferences_pending(
                entry_id,
                affected_user_ids,
            )

            return True

        except StaleEmbeddingGenerationError:
            # Do not mark an entry failed when the job itself is obsolete.
            # Batch callers restore all unprocessed claims to pending.
            raise
        except Exception as e:
            # Infrastructure error (API / vector backend) – mark the entry
            # as failed but re-raise so the worker circuit breaker can react.
            logger.error(f"Failed to generate embedding for entry {entry_id}: {e}")
            await self._mark_failed_fenced(entry_id, str(e))
            raise

    async def _store_embedding(
        self,
        *,
        entry: Entry,
        embedding: list[float],
        language: str,
        word_count: int,
    ) -> list[str]:
        """Fence the vector write against collection recreation."""
        entry_id = entry.id
        feed_id = entry.feed_id
        published_at = entry.published_at
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
            affected_user_ids = await self._mark_affected_preferences_dirty_in_db(entry_id)
            await self.db.commit()
            return affected_user_ids
        finally:
            if lock is not None and acquired:
                with contextlib.suppress(Exception):
                    await lock.release()

    async def _mark_failed(self, entry_id: str, error: str) -> None:
        """Mark entry embedding as failed."""
        await self.db.execute(
            update(Entry)
            .where(Entry.id == entry_id)
            .values(embedding_status="failed", embedding_error=error)
        )
        await self.db.flush()

    async def _mark_affected_preferences_dirty_in_db(
        self,
        entry_id: str,
    ) -> list[str]:
        """Durably dirty users in the same transaction as the done marker."""
        result = await self.db.execute(
            union(
                select(UserEntry.user_id).where(
                    UserEntry.entry_id == entry_id,
                    UserEntry.is_liked.is_not(None),
                ),
                select(Bookmark.user_id).where(Bookmark.entry_id == entry_id),
            )
        )
        user_ids = [str(row[0]) for row in result.all()]
        await mark_preferences_dirty(self.db, user_ids)
        return user_ids

    async def _mark_affected_preferences_pending(
        self,
        entry_id: str,
        user_ids: list[str],
    ) -> None:
        """Accelerate delivery of users already dirtied in PostgreSQL."""
        if not user_ids or self.generation_lock is None:
            return
        try:
            await self.generation_lock.sadd(
                RedisKeys.PREFERENCE_PENDING_USERS_KEY,
                *user_ids,
            )
        except Exception:
            logger.warning(
                "Could not mark affected preference users pending",
                extra={"entry_id": entry_id, "user_count": len(user_ids)},
                exc_info=True,
            )

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

    async def batch_generate(self, limit: int = 100) -> dict[str, int]:
        """
        Generate embeddings for pending entries in batch.

        Uses SELECT FOR UPDATE SKIP LOCKED so that concurrent workers each
        claim disjoint sets of entries and no entry is processed twice (or
        left permanently pending because every job grabbed the same rows).

        Each entry is committed independently so that a single failure
        doesn't poison the session for remaining entries.

        Args:
            limit: Maximum number of entries to process

        Returns:
            Dictionary with processed and failed counts
        """
        # Atomically claim pending entries.  Rows locked by another concurrent
        # worker are skipped, ensuring each worker gets a unique slice.
        claim_result = await self.db.execute(
            select(Entry.id)
            .where(Entry.embedding_status == "pending")
            .order_by(Entry.created_at.desc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        entry_ids = [row[0] for row in claim_result.all()]

        if not entry_ids:
            return {"processed": 0, "failed": 0}

        # Mark all claimed entries as processing and commit to make the
        # claim durable.  This also releases the FOR UPDATE locks; since
        # the status is now 'processing', no other worker will pick them up.
        await self.db.execute(
            update(Entry)
            .where(Entry.id.in_(entry_ids))
            .values(embedding_status="processing", embedding_error=None)
        )
        await self.db.commit()

        processed = 0
        failed = 0

        for index, entry_id in enumerate(entry_ids):
            try:
                success = await self.generate_embedding(entry_id)
                await self.db.commit()
                if success:
                    processed += 1
                else:
                    failed += 1
            except StaleEmbeddingGenerationError:
                await self.db.rollback()
                await self.restore_claimed_entries(entry_ids[index:])
                break
            except Exception:
                # Infrastructure error.  generate_embedding already tried
                # _mark_failed_safe (which may have rolled back).  Ensure
                # any pending changes are either committed or rolled back
                # so the next iteration starts with a clean session.
                with contextlib.suppress(Exception):
                    await self.db.rollback()
                failed += 1

        return {"processed": processed, "failed": failed}

    async def retry_failed(self, limit: int = 50) -> dict[str, int]:
        """
        Retry failed embeddings.

        Uses SELECT FOR UPDATE SKIP LOCKED to avoid concurrent retriers
        picking up the same entries.  Each entry is committed independently.

        Args:
            limit: Maximum number of entries to retry

        Returns:
            Dictionary with processed and failed counts
        """
        claim_result = await self.db.execute(
            select(Entry.id)
            .where(Entry.embedding_status == "failed")
            .order_by(Entry.updated_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        entry_ids = [row[0] for row in claim_result.all()]

        if not entry_ids:
            return {"processed": 0, "failed": 0}

        await self.db.execute(
            update(Entry)
            .where(Entry.id.in_(entry_ids))
            .values(embedding_status="processing", embedding_error=None)
        )
        await self.db.commit()

        processed = 0
        failed = 0

        for index, entry_id in enumerate(entry_ids):
            try:
                success = await self.generate_embedding(entry_id)
                await self.db.commit()
                if success:
                    processed += 1
                else:
                    failed += 1
            except StaleEmbeddingGenerationError:
                await self.db.rollback()
                await self.restore_claimed_entries(entry_ids[index:])
                break
            except Exception:
                with contextlib.suppress(Exception):
                    await self.db.rollback()
                failed += 1

        return {"processed": processed, "failed": failed}

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
