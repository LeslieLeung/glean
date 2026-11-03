"""Tests for feed-triggered vector client recovery."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from glean_worker.tasks.feed_fetcher import _should_embed_entries


@pytest.mark.asyncio
async def test_should_embed_recovers_vector_client_on_demand() -> None:
    ctx: dict[str, object] = {"vector_client": None}
    session = AsyncMock()
    vector_client = MagicMock()

    with (
        patch(
            "glean_worker.tasks.feed_fetcher._is_vectorization_enabled",
            AsyncMock(return_value=True),
        ),
        patch(
            "glean_worker.tasks.feed_fetcher.ensure_vector_client",
            return_value=(vector_client, None),
        ) as ensure_client,
    ):
        should_embed = await _should_embed_entries(ctx, session)

    assert should_embed is True
    ensure_client.assert_called_once_with(ctx)


@pytest.mark.asyncio
async def test_should_embed_does_not_connect_while_vectorization_disabled() -> None:
    ctx: dict[str, object] = {"vector_client": None}
    session = AsyncMock()

    with (
        patch(
            "glean_worker.tasks.feed_fetcher._is_vectorization_enabled",
            AsyncMock(return_value=False),
        ),
        patch("glean_worker.tasks.feed_fetcher.ensure_vector_client") as ensure_client,
    ):
        should_embed = await _should_embed_entries(ctx, session)

    assert should_embed is False
    ensure_client.assert_not_called()
