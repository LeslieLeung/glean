"""
Translation provider abstraction.

Supports Google Translate (free), DeepL, and OpenAI as configurable
translation backends. Users configure their preferred provider and
API key via user settings; no key falls back to Google free.
"""

from abc import ABC, abstractmethod
from typing import Any

from glean_core import get_logger

logger = get_logger(__name__)

# Google Translate has a ~5000 character limit per request
_CHUNK_SIZE = 4500
_SEPARATOR = " ||| "


class TranslationProvider(ABC):
    """Base class for translation providers."""

    @abstractmethod
    def translate(self, text: str, source: str, target: str) -> str:
        """Translate a single text string."""

    def translate_batch(self, texts: list[str], source: str, target: str) -> list[str]:
        """Translate a list of texts. Default: translate one by one."""
        return [self.translate(t, source, target) for t in texts]


class GoogleFreeProvider(TranslationProvider):
    """Free Google Translate via deep-translator."""

    def translate(self, text: str, source: str, target: str) -> str:
        from deep_translator import GoogleTranslator

        if not text or not text.strip():
            return text
        translator = GoogleTranslator(source=source, target=target)
        result: str = translator.translate(text[:_CHUNK_SIZE])
        return result

    def translate_batch(self, texts: list[str], source: str, target: str) -> list[str]:
        """Batch translate using ||| separator for efficiency."""
        from deep_translator import GoogleTranslator

        if not texts:
            return []

        translator = GoogleTranslator(source=source, target=target)
        results: list[str] = [""] * len(texts)

        batch_start = 0
        while batch_start < len(texts):
            batch_texts: list[str] = []
            batch_indices: list[int] = []
            current_length = 0

            for i in range(batch_start, len(texts)):
                text = texts[i]
                needed = len(text) + len(_SEPARATOR)
                if current_length + needed > _CHUNK_SIZE and batch_texts:
                    break
                batch_texts.append(text)
                batch_indices.append(i)
                current_length += needed

            if not batch_texts:
                break

            combined = _SEPARATOR.join(batch_texts)

            if len(combined) <= _CHUNK_SIZE:
                translated_combined: str = translator.translate(combined)
                translated_parts = translated_combined.split("|||")
                for j, idx in enumerate(batch_indices):
                    results[idx] = translated_parts[j].strip() if j < len(translated_parts) else ""
            else:
                for j, idx in enumerate(batch_indices):
                    result: str = translator.translate(batch_texts[j][:_CHUNK_SIZE])
                    results[idx] = result

            batch_start += len(batch_texts)

        return results


class DeepLProvider(TranslationProvider):
    """DeepL translation provider."""

    # DeepL uses different language codes than standard
    _LANG_MAP: dict[str, str] = {
        "zh-CN": "ZH-HANS",
        "zh-TW": "ZH-HANT",
        "en": "EN-US",
        "pt": "PT-BR",
    }

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def _map_lang(self, lang: str, *, is_source: bool = False) -> str | None:
        if is_source and lang == "auto":
            return None
        mapped = self._LANG_MAP.get(lang, lang.upper())
        return mapped

    def translate(self, text: str, source: str, target: str) -> str:
        import deepl

        if not text or not text.strip():
            return text

        translator = deepl.Translator(self.api_key)
        source_lang = self._map_lang(source, is_source=True)
        target_lang = self._map_lang(target)
        result = translator.translate_text(
            text,
            source_lang=source_lang,
            target_lang=target_lang,  # type: ignore[arg-type]
        )
        return str(result)

    def translate_batch(self, texts: list[str], source: str, target: str) -> list[str]:
        import deepl

        if not texts:
            return []

        translator = deepl.Translator(self.api_key)
        source_lang = self._map_lang(source, is_source=True)
        target_lang = self._map_lang(target)
        results = translator.translate_text(
            texts,
            source_lang=source_lang,
            target_lang=target_lang,  # type: ignore[arg-type]
        )
        if isinstance(results, list):
            return [str(r) for r in results]
        return [str(results)]


class OpenAIProvider(TranslationProvider):
    """OpenAI translation provider."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key
        self.model = model

    def translate(self, text: str, source: str, target: str) -> str:
        from openai import OpenAI

        if not text or not text.strip():
            return text

        client = OpenAI(api_key=self.api_key)
        source_desc = "the source language" if source == "auto" else source
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a translator. Translate the following text from "
                        f"{source_desc} to {target}. Output only the translation, "
                        f"nothing else."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content or ""

    def translate_batch(self, texts: list[str], source: str, target: str) -> list[str]:
        from openai import OpenAI

        if not texts:
            return []

        client = OpenAI(api_key=self.api_key)
        source_desc = "the source language" if source == "auto" else source
        numbered = "\n".join(f"[{i + 1}] {t}" for i, t in enumerate(texts))
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a translator. Translate each numbered line from "
                        f"{source_desc} to {target}. Keep the [N] numbering format. "
                        f"Output only the translations, one per line."
                    ),
                },
                {"role": "user", "content": numbered},
            ],
            temperature=0.3,
        )
        raw = response.choices[0].message.content or ""

        # Parse numbered results
        results: list[str] = [""] * len(texts)
        for line in raw.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # Match [N] prefix
            if line.startswith("["):
                bracket_end = line.find("]")
                if bracket_end > 0:
                    try:
                        idx = int(line[1:bracket_end]) - 1
                        if 0 <= idx < len(texts):
                            results[idx] = line[bracket_end + 1 :].strip()
                    except ValueError:
                        pass

        return results


def create_translation_provider(settings: dict[str, Any] | None) -> TranslationProvider:
    """
    Create a translation provider from user settings.

    Settings keys:
        - translation_provider: "google" | "deepl" | "openai"
        - translation_api_key: API key for non-Google providers
        - translation_model: Model name for OpenAI (default: "gpt-4o-mini")

    Falls back to GoogleFreeProvider when provider is google, no key is
    provided for non-google providers, or settings are empty.
    """
    if not settings:
        return GoogleFreeProvider()

    provider = settings.get("translation_provider", "google")
    api_key = settings.get("translation_api_key", "")
    model = settings.get("translation_model", "gpt-4o-mini")

    if provider == "deepl" and api_key:
        logger.info("Using DeepL translation provider")
        return DeepLProvider(api_key)

    if provider == "openai" and api_key:
        logger.info(
            "Using OpenAI translation provider",
            extra={"model": model},
        )
        return OpenAIProvider(api_key, model)

    return GoogleFreeProvider()
