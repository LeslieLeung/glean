"""Integration tests for entries API endpoints."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.schemas.systemone import ContentCategory, SystemOneConfig
from glean_core.services import TypedConfigService


@pytest.fixture
async def test_entries(db_session: AsyncSession, test_subscription, test_feed):
    """Create test entries."""
    from glean_database.models.entry import Entry

    entries = []
    for i in range(3):
        entry = Entry(
            feed_id=test_feed.id,
            title=f"Test Entry {i + 1}",
            url=f"https://example.com/entry/{i + 1}",
            content=f"Content of entry {i + 1}",
            published_at=datetime.now(UTC),
        )
        db_session.add(entry)
        entries.append(entry)

    await db_session.commit()
    for entry in entries:
        await db_session.refresh(entry)

    return entries


@pytest.fixture
async def test_user_entry(db_session: AsyncSession, test_user, test_entries):
    """Create a user entry (read state)."""
    from glean_database.models.user_entry import UserEntry

    user_entry = UserEntry(
        user_id=test_user.id,
        entry_id=test_entries[0].id,
        is_read=True,
        is_liked=False,
        read_later=False,
    )
    db_session.add(user_entry)
    await db_session.commit()
    await db_session.refresh(user_entry)
    return user_entry


class TestListEntries:
    """Test listing entries."""

    @pytest.mark.asyncio
    async def test_list_entries_empty(self, client: AsyncClient, auth_headers):
        """Test listing entries when there are none."""
        response = await client.get("/api/entries", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "page" in data
        assert "per_page" in data
        assert "total" in data
        assert len(data["items"]) == 0

    @pytest.mark.asyncio
    async def test_list_entries(self, client: AsyncClient, auth_headers, test_entries):
        """Test listing entries."""
        response = await client.get("/api/entries", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert len(data["items"]) == 3
        assert all("title" in entry for entry in data["items"])

    @pytest.mark.asyncio
    async def test_list_entries_pagination(self, client: AsyncClient, auth_headers, test_entries):
        """Test entry pagination."""
        response = await client.get("/api/entries?page=1&per_page=2", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["per_page"] == 2
        assert data["total"] == 3

    @pytest.mark.asyncio
    async def test_list_entries_filter_by_feed(
        self, client: AsyncClient, auth_headers, test_entries, test_feed
    ):
        """Test filtering entries by feed."""
        response = await client.get(f"/api/entries?feed_id={test_feed.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) == 3
        assert all(entry["feed_id"] == str(test_feed.id) for entry in data["items"])

    @pytest.mark.asyncio
    async def test_list_entries_filter_by_read_status(
        self, client: AsyncClient, auth_headers, test_user_entry, test_entries
    ):
        """Test filtering entries by read status."""
        # Filter for read entries
        response = await client.get("/api/entries?is_read=true", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) >= 1
        assert all(entry.get("is_read", False) for entry in data["items"])

        # Filter for unread entries
        response = await client.get("/api/entries?is_read=false", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) >= 2

    @pytest.mark.asyncio
    async def test_list_entries_unauthorized(self, client: AsyncClient):
        """Test listing entries without authentication."""
        response = await client.get("/api/entries")

        assert response.status_code == 401


async def test_smart_content_category_filter(client, auth_headers, db_session, test_entries):
    categories = [
        ContentCategory(id="custom", label="Custom", description="Classify as custom"),
        ContentCategory(id="news", label="News"),
    ]
    config_service = TypedConfigService(db_session)
    options_path = "/api/entries/content-categories"
    assert (await client.get(options_path)).status_code == 401
    assert (await client.get(options_path, headers=auth_headers)).json() == []
    await config_service.set(
        SystemOneConfig, SystemOneConfig(enabled=True, provider="clef", categories=categories)
    )
    options = await client.get(options_path, headers=auth_headers)
    assert options.json() == [{"id": option.id, "label": option.label} for option in categories]

    for entry, provider, category in zip(
        test_entries[:2], ("jev", "clef"), categories, strict=True
    ):
        entry.classification_result = {
            "provider": provider,
            "model_id": f"{provider}-test",
            "label": "human",
            "score": 0.9,
            "content": {"label": category.id, "name": category.label, "confidence": 0.9},
        }
    test_entries[2].classification_result = {"model_id": "jev-test", "label": "ai", "score": 0.9}
    await db_session.commit()

    async def list_entries(**params):
        return await client.get("/api/entries", headers=auth_headers, params=params)

    smart = {"view": "smart", "global_smart": True, "use_cursor": True, "per_page": 1}
    first = (await list_entries(**smart, content_category_ids="custom,news")).json()
    assert first["total"] == 2
    assert first["next_cursor"]
    second = await list_entries(
        **smart, content_category_ids="news,custom", cursor=first["next_cursor"]
    )
    assert second.status_code == 200
    assert second.json()["next_cursor"] is None
    assert {first["items"][0]["id"], second.json()["items"][0]["id"]} == {
        str(entry.id) for entry in test_entries[:2]
    }
    assert (
        await list_entries(**smart, content_category_ids="custom", cursor=first["next_cursor"])
    ).status_code == 410
    assert (await list_entries(**smart, content_category_ids="")).json()["total"] == 0
    assert (await list_entries(**smart, content_category_ids="ai,human")).json()["total"] == 0
    assert (await list_entries(**smart)).json()["total"] == 3
    assert (await list_entries(content_category_ids="custom")).json()["total"] == 3

    await config_service.update(SystemOneConfig, classify_content=False)
    assert (await client.get(options_path, headers=auth_headers)).json() == []


class TestGetEntry:
    """Test getting a specific entry."""

    @pytest.mark.asyncio
    async def test_get_entry_success(self, client: AsyncClient, auth_headers, test_entries):
        """Test getting a specific entry."""
        entry_id = test_entries[0].id
        response = await client.get(f"/api/entries/{entry_id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == str(entry_id)
        assert data["title"] == test_entries[0].title

    @pytest.mark.asyncio
    async def test_get_nonexistent_entry(self, client: AsyncClient, auth_headers):
        """Test getting a non-existent entry."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/entries/{fake_id}", headers=auth_headers)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_entry_unauthorized(self, client: AsyncClient, test_entries):
        """Test getting entry without authentication."""
        response = await client.get(f"/api/entries/{test_entries[0].id}")

        assert response.status_code == 401


class TestUpdateEntryState:
    """Test updating entry state."""

    @pytest.mark.asyncio
    async def test_mark_entry_as_read(self, client: AsyncClient, auth_headers, test_entries):
        """Test marking an entry as read."""
        entry_id = test_entries[0].id
        response = await client.patch(
            f"/api/entries/{entry_id}", headers=auth_headers, json={"is_read": True}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == str(entry_id)
        assert data["is_read"] is True

    @pytest.mark.asyncio
    async def test_mark_entry_as_liked(self, client: AsyncClient, auth_headers, test_entries):
        """Test marking an entry as liked."""
        entry_id = test_entries[0].id
        response = await client.patch(
            f"/api/entries/{entry_id}", headers=auth_headers, json={"is_liked": True}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["is_liked"] is True

    @pytest.mark.asyncio
    async def test_mark_entry_for_read_later(self, client: AsyncClient, auth_headers, test_entries):
        """Test marking an entry for read later."""
        entry_id = test_entries[0].id
        response = await client.patch(
            f"/api/entries/{entry_id}", headers=auth_headers, json={"read_later": True}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["read_later"] is True

    @pytest.mark.asyncio
    async def test_update_multiple_states(self, client: AsyncClient, auth_headers, test_entries):
        """Test updating multiple states at once."""
        entry_id = test_entries[0].id
        response = await client.patch(
            f"/api/entries/{entry_id}",
            headers=auth_headers,
            json={"is_read": True, "is_liked": True, "read_later": False},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["is_read"] is True
        assert data["is_liked"] is True
        assert data["read_later"] is False

    @pytest.mark.asyncio
    async def test_update_nonexistent_entry(self, client: AsyncClient, auth_headers):
        """Test updating a non-existent entry."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.patch(
            f"/api/entries/{fake_id}", headers=auth_headers, json={"is_read": True}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_entry_unauthorized(self, client: AsyncClient, test_entries):
        """Test updating entry without authentication."""
        response = await client.patch(f"/api/entries/{test_entries[0].id}", json={"is_read": True})

        assert response.status_code == 401


class TestMarkAllRead:
    """Test marking all entries as read."""

    @pytest.mark.asyncio
    async def test_mark_all_read_success(self, client: AsyncClient, auth_headers, test_entries):
        """Test marking all entries as read."""
        response = await client.post("/api/entries/mark-all-read", headers=auth_headers, json={})

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

        # Verify all entries are read
        list_response = await client.get("/api/entries", headers=auth_headers)
        entries = list_response.json()["items"]
        assert all(entry.get("is_read", False) for entry in entries)

    @pytest.mark.asyncio
    async def test_mark_all_read_by_feed(
        self, client: AsyncClient, auth_headers, test_entries, test_feed
    ):
        """Test marking all entries in a specific feed as read."""
        response = await client.post(
            "/api/entries/mark-all-read", headers=auth_headers, json={"feed_id": str(test_feed.id)}
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_mark_all_read_unauthorized(self, client: AsyncClient):
        """Test marking all as read without authentication."""
        response = await client.post("/api/entries/mark-all-read")

        assert response.status_code == 401
