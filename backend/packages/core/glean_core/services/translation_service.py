"""
Translation service.

Handles translation request management and caching via the EntryTranslation table.
"""

import re
from typing import Any

from arq.connections import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import get_logger
from glean_core.schemas.entry import TranslationResponse
from glean_database.models import Entry
from glean_database.models.entry_translation import EntryTranslation

logger = get_logger(__name__)

# Regex to detect whether text is primarily Chinese characters
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")


def detect_target_language(text: str) -> str:
    """
    Auto-detect target language based on content.

    If the text contains a significant proportion of Chinese characters,
    translate to English; otherwise translate to Chinese.

    Args:
        text: Sample text from the entry (title or first part of content).

    Returns:
        Target language code ("en" or "zh-CN").
    """
    if not text:
        return "zh-CN"
    # Count Chinese characters in the first 200 chars
    sample = text[:200]
    chinese_count = len(_CHINESE_RE.findall(sample))
    alpha_count = sum(1 for c in sample if c.isalpha())
    if alpha_count == 0:
        return "zh-CN"
    ratio = chinese_count / alpha_count
    return "en" if ratio > 0.3 else "zh-CN"


class TranslationService:
    """Translation management service."""

    def __init__(self, session: AsyncSession, redis_pool: ArqRedis | None = None):
        self.session = session
        self.redis_pool = redis_pool

    async def request_translation(
        self, entry_id: str, user_id: str, target_language: str | None = None
    ) -> TranslationResponse:
        """
        Request translation of an entry.

        If a translation already exists and is done, return the cached version.
        Otherwise, create a record and queue a worker task.

        Args:
            entry_id: Entry UUID.
            user_id: Current user ID (for authorization check).
            target_language: Target language code. None = auto-detect.

        Returns:
            TranslationResponse with current status and content.

        Raises:
            ValueError: If entry not found.
        """
        # Verify entry exists
        stmt = select(Entry).where(Entry.id == entry_id)
        result = await self.session.execute(stmt)
        entry = result.scalar_one_or_none()
        if not entry:
            raise ValueError(f"Entry {entry_id} not found")

        # Auto-detect target language if not specified
        if not target_language:
            sample = entry.title or ""
            if entry.content:
                sample += " " + entry.content[:500]
            target_language = detect_target_language(sample)

        # Check for existing translation
        existing = await self._get_existing(entry_id, target_language)
        if existing and existing.status == "done":
            return self._to_response(existing)

        if existing and existing.status in ("pending", "processing"):
            return self._to_response(existing)

        # Create new translation record (or reset a failed one)
        if existing and existing.status == "failed":
            existing.status = "pending"
            existing.error = None
            existing.translated_title = None
            existing.translated_content = None
            translation = existing
        else:
            translation = EntryTranslation(
                entry_id=entry_id,
                target_language=target_language,
                status="pending",
            )
            self.session.add(translation)

        await self.session.commit()
        await self.session.refresh(translation)

        # Queue worker task
        if self.redis_pool:
            try:
                await self.redis_pool.enqueue_job(
                    "translate_entry_task",
                    entry_id=entry_id,
                    target_language=target_language,
                    user_id=user_id,
                )
                logger.info(
                    "Queued translation task",
                    extra={
                        "entry_id": entry_id,
                        "target_language": target_language,
                    },
                )
            except Exception:
                logger.exception(
                    "Failed to queue translation task",
                    extra={"entry_id": entry_id},
                )

        return self._to_response(translation)

    async def get_translation(
        self, entry_id: str, target_language: str
    ) -> TranslationResponse | None:
        """
        Get translation for an entry.

        Args:
            entry_id: Entry UUID.
            target_language: Target language code.

        Returns:
            TranslationResponse or None if not found.
        """
        existing = await self._get_existing(entry_id, target_language)
        if not existing:
            return None
        return self._to_response(existing)

    async def _get_existing(self, entry_id: str, target_language: str) -> EntryTranslation | None:
        stmt = select(EntryTranslation).where(
            EntryTranslation.entry_id == entry_id,
            EntryTranslation.target_language == target_language,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_paragraph_translations(
        self, entry_id: str, target_language: str
    ) -> dict[str, str] | None:
        """
        Get cached paragraph-level translations for an entry.

        Args:
            entry_id: Entry UUID.
            target_language: Target language code.

        Returns:
            Mapping of original sentence to translated sentence, or None.
        """
        existing = await self._get_existing(entry_id, target_language)
        if not existing or not existing.paragraph_translations:
            return None
        return existing.paragraph_translations

    async def save_paragraph_translations(
        self, entry_id: str, target_language: str, translations: dict[str, str]
    ) -> None:
        """
        Persist paragraph-level translations, merging into existing data.

        Creates a new EntryTranslation row if one doesn't exist yet,
        otherwise merges into the existing paragraph_translations JSONB.

        Args:
            entry_id: Entry UUID.
            target_language: Target language code.
            translations: Mapping of original sentence to translated sentence.
        """
        existing = await self._get_existing(entry_id, target_language)
        if existing:
            merged = dict(existing.paragraph_translations or {})
            merged.update(translations)
            existing.paragraph_translations = merged
        else:
            row = EntryTranslation(
                entry_id=entry_id,
                target_language=target_language,
                status="done",
                paragraph_translations=translations,
            )
            self.session.add(row)
        await self.session.commit()

    @staticmethod
    def _to_response(t: EntryTranslation) -> TranslationResponse:
        return TranslationResponse(
            entry_id=t.entry_id,
            target_language=t.target_language,
            translated_title=t.translated_title,
            translated_content=t.translated_content,
            status=t.status,
            error=t.error,
        )


__all__: list[Any] = ["TranslationService"]
