"""Embedding generation service."""

import re
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import get_logger
from glean_database.models import Entry
from glean_vector.clients.embedding_client import EmbeddingClient
from glean_vector.clients.milvus_client import MilvusClient

logger = get_logger(__name__)


class EmbeddingService:
    """
    Service for generating and managing entry embeddings.

    Handles the complete embedding lifecycle:
    1. Extract text from entry
    2. Generate embedding via API
    3. Store in Milvus
    4. Update entry status in PostgreSQL
    """

    def __init__(
        self,
        db_session: AsyncSession,
        embedding_client: EmbeddingClient,
        milvus_client: MilvusClient,
    ) -> None:
        """
        Initialize embedding service.

        Args:
            db_session: Database session
            embedding_client: Embedding API client
            milvus_client: Milvus vector database client
        """
        self.db = db_session
        self.embedding_client = embedding_client
        self.milvus = milvus_client

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
        await self.db.commit()

        try:
            # Extract text
            text = self._extract_text(entry)
            word_count = self._calculate_word_count(text)

            if not text:
                await self._mark_failed(entry_id, "No text content to embed")
                return False

            # Generate embedding
            embedding, metadata = await self.embedding_client.generate_embedding(text)

            # Detect language (simple heuristic)
            language = self._detect_language(text)

            # Store in Milvus
            await self.milvus.insert_entry_embedding(
                entry_id=entry_id,
                embedding=embedding,
                feed_id=entry.feed_id,
                published_at=entry.published_at,
                language=language,
                word_count=word_count,
                author=entry.author or "",
            )

            # Update entry status
            await self.db.execute(
                update(Entry)
                .where(Entry.id == entry_id)
                .values(
                    embedding_status="done",
                    embedding_at=datetime.now(),
                    word_count=word_count,
                    embedding_error=None,
                )
            )
            await self.db.commit()

            return True

        except Exception as e:
            logger.error(f"Failed to generate embedding for entry {entry_id}: {e}")
            await self._mark_failed(entry_id, str(e))
            return False

    async def _mark_failed(self, entry_id: str, error: str) -> None:
        """Mark entry embedding as failed."""
        await self.db.execute(
            update(Entry)
            .where(Entry.id == entry_id)
            .values(embedding_status="failed", embedding_error=error)
        )
        await self.db.commit()

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

        Args:
            limit: Maximum number of entries to process

        Returns:
            Dictionary with processed and failed counts
        """
        # Get pending entries
        result = await self.db.execute(
            select(Entry)
            .where(Entry.embedding_status == "pending")
            .order_by(Entry.created_at.desc())
            .limit(limit)
        )
        entries = result.scalars().all()

        processed = 0
        failed = 0

        for entry in entries:
            success = await self.generate_embedding(entry.id)
            if success:
                processed += 1
            else:
                failed += 1

        return {"processed": processed, "failed": failed}

    async def retry_failed(self, limit: int = 50) -> dict[str, int]:
        """
        Retry failed embeddings.

        Args:
            limit: Maximum number of entries to retry

        Returns:
            Dictionary with processed and failed counts
        """
        # Get failed entries (not recently failed)
        result = await self.db.execute(
            select(Entry)
            .where(Entry.embedding_status == "failed")
            .order_by(Entry.updated_at.asc())
            .limit(limit)
        )
        entries = result.scalars().all()

        processed = 0
        failed = 0

        for entry in entries:
            success = await self.generate_embedding(entry.id)
            if success:
                processed += 1
            else:
                failed += 1

        return {"processed": processed, "failed": failed}

    async def delete_embedding(self, entry_id: str) -> None:
        """
        Delete embedding for an entry.

        Args:
            entry_id: Entry UUID
        """
        # Delete from Milvus
        await self.milvus.delete_entry_embedding(entry_id)

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
        await self.db.commit()
