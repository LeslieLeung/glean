"""Regression tests for smart-view pagination."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from glean_core.services.entry_service import EntryService


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ScalarResult:
    def __init__(self, value: int):
        self._value = value

    def scalar(self) -> int:
        return self._value


@pytest.mark.asyncio
async def test_smart_view_can_page_beyond_the_old_five_page_window() -> None:
    now = datetime.now(UTC)
    rows = []
    for index in range(120):
        entry = SimpleNamespace(
            id=f"entry-{index:03d}",
            feed_id="feed-1",
            url=f"https://example.com/{index}",
            title=f"Entry {index}",
            author=None,
            content=None,
            summary=None,
            published_at=now - timedelta(minutes=index),
            created_at=now,
        )
        rows.append((entry, None, None, "Example", None))

    session = AsyncMock()
    session.execute.side_effect = [
        _RowsResult([("feed-1",)]),
        _ScalarResult(120),
        _RowsResult(rows),
    ]
    score_service = AsyncMock()
    score_service.batch_calculate_scores.side_effect = lambda _user_id, entries: {
        entry.id: float(120 - int(entry.id.rsplit("-", 1)[1])) for entry in entries
    }

    result = await EntryService(session).get_entries(
        user_id="user-1",
        page=6,
        per_page=20,
        view="smart",
        score_service=score_service,
    )

    assert len(result.items) == 20
    assert result.items[0].id == "entry-100"
    assert result.items[-1].id == "entry-119"
    assert result.total_pages == 6
