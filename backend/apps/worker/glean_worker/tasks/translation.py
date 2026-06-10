"""Translation worker task.

Translates entry content using a user-configured translation provider
(Google Translate, DeepL, or OpenAI). Produces bilingual HTML where
each block element is followed by its translated counterpart, enabling
side-by-side reading.
"""

from typing import Any

from bs4 import BeautifulSoup, Tag
from sqlalchemy import select

from glean_core import get_logger
from glean_core.services.translation_providers import (
    TranslationProvider,
    create_translation_provider,
)
from glean_database.models import Entry
from glean_database.models.entry_translation import EntryTranslation
from glean_database.models.user import User
from glean_database.session import get_session_context

logger = get_logger(__name__)

# Google Translate has a ~5000 character limit per request
CHUNK_SIZE = 4500

# Block-level elements that get bilingual treatment
_BLOCK_TAGS = frozenset(
    {
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "blockquote",
        "figcaption",
        "dt",
        "dd",
    }
)

# Elements whose children should not be translated
_SKIP_ANCESTORS = frozenset({"code", "pre", "script", "style"})


def _translate_text(text: str, source: str, target: str, provider: TranslationProvider) -> str:
    """Translate a single text string, handling chunking for long text."""
    if not text or not text.strip():
        return text

    # For short text, translate directly
    if len(text) <= CHUNK_SIZE:
        return provider.translate(text, source, target)

    # For long text, split into chunks at sentence boundaries
    chunks: list[str] = []
    current = ""
    for sentence in text.replace("\n", "\n ").split(". "):
        if len(current) + len(sentence) + 2 > CHUNK_SIZE:
            if current:
                chunks.append(current)
            current = sentence
        else:
            current = current + ". " + sentence if current else sentence
    if current:
        chunks.append(current)

    translated_chunks: list[str] = []
    for chunk in chunks:
        result = provider.translate(chunk, source, target)
        translated_chunks.append(result)

    return " ".join(translated_chunks)


def _has_skip_ancestor(element: Tag) -> bool:
    """Check if an element is nested inside code/pre/script/style."""
    return any(parent.name in _SKIP_ANCESTORS for parent in element.parents)


def _translate_html_bilingual(
    html_content: str, source: str, target: str, provider: TranslationProvider
) -> str:
    """
    Translate HTML content in bilingual mode.

    For each block-level element, inserts a translated copy immediately
    after the original, marked with class ``glean-translation``.
    Non-block content (images, code blocks, etc.) is left untouched.

    Args:
        html_content: Original HTML string.
        source: Source language code (or "auto").
        target: Target language code (e.g. "zh-CN", "en").
        provider: Translation provider instance.

    Returns:
        HTML string with interleaved original and translated blocks.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Collect block elements with translatable text
    blocks: list[tuple[Tag, str]] = []
    for el in soup.find_all(list(_BLOCK_TAGS)):
        if _has_skip_ancestor(el):
            continue
        text = el.get_text(strip=True)
        if text:
            blocks.append((el, text))

    if not blocks:
        return html_content

    # Batch-translate all block texts at once
    all_texts = [t for _, t in blocks]
    translated_texts = provider.translate_batch(all_texts, source, target)

    for i, (el, _) in enumerate(blocks):
        translated_text = translated_texts[i].strip() if i < len(translated_texts) else ""
        if translated_text:
            new_tag = soup.new_tag(el.name)
            new_tag.string = translated_text
            new_tag["class"] = "glean-translation"
            el.insert_after(new_tag)

    return str(soup)


async def translate_entry_task(
    _ctx: dict[str, Any],
    entry_id: str,
    target_language: str,
    user_id: str | None = None,
) -> dict[str, Any]:
    """
    Translate an entry's title and content.

    Args:
        _ctx: Worker context.
        entry_id: Entry UUID.
        target_language: Target language code (e.g. "zh-CN", "en").
        user_id: Optional user ID to look up translation provider settings.

    Returns:
        Result dictionary with status.
    """
    logger.info(
        "Starting translation task",
        extra={"entry_id": entry_id, "target_language": target_language, "user_id": user_id},
    )

    async with get_session_context() as session:
        # Look up user settings for translation provider
        user_settings: dict[str, Any] | None = None
        if user_id:
            user_result = await session.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            if user:
                user_settings = user.settings

        provider = create_translation_provider(user_settings)

        # Get the translation record
        stmt = select(EntryTranslation).where(
            EntryTranslation.entry_id == entry_id,
            EntryTranslation.target_language == target_language,
        )
        result = await session.execute(stmt)
        translation = result.scalar_one_or_none()

        if not translation:
            logger.error("Translation record not found", extra={"entry_id": entry_id})
            return {"status": "error", "message": "Translation record not found"}

        # Mark as processing
        translation.status = "processing"
        await session.commit()

        # Get the entry
        entry_stmt = select(Entry).where(Entry.id == entry_id)
        entry_result = await session.execute(entry_stmt)
        entry = entry_result.scalar_one_or_none()

        if not entry:
            translation.status = "failed"
            translation.error = "Entry not found"
            await session.commit()
            return {"status": "error", "message": "Entry not found"}

        try:
            source = "auto"

            # Translate title
            translated_title = None
            if entry.title:
                translated_title = _translate_text(entry.title, source, target_language, provider)
                logger.info(
                    "Title translated",
                    extra={"entry_id": entry_id, "original": entry.title[:50]},
                )

            # Translate content (HTML) — bilingual mode
            translated_content = None
            content = entry.content or entry.summary
            if content:
                translated_content = _translate_html_bilingual(
                    content, source, target_language, provider
                )
                logger.info(
                    "Content translated",
                    extra={
                        "entry_id": entry_id,
                        "content_length": len(content),
                        "translated_length": len(translated_content),
                    },
                )

            # Update translation record
            translation.translated_title = translated_title
            translation.translated_content = translated_content
            translation.status = "done"
            translation.error = None
            await session.commit()

            logger.info(
                "Translation completed successfully",
                extra={"entry_id": entry_id, "target_language": target_language},
            )
            return {"status": "success", "entry_id": entry_id}

        except Exception as e:
            error_msg = str(e)
            logger.exception(
                "Translation failed",
                extra={"entry_id": entry_id, "error": error_msg},
            )
            translation.status = "failed"
            translation.error = error_msg
            await session.commit()
            return {"status": "error", "entry_id": entry_id, "error": error_msg}
