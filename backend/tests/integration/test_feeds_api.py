"""Integration tests for feeds and subscriptions API endpoints."""

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


@pytest.fixture(autouse=True)
def feed_discovery(monkeypatch):
    async def discover(url):
        return url, "Test Feed"

    mock = AsyncMock(side_effect=discover)
    monkeypatch.setattr("glean_api.routers.feeds.discover_feed", mock)
    return mock


class TestListSubscriptions:
    """Test listing user subscriptions."""

    @pytest.mark.asyncio
    async def test_list_empty_subscriptions(self, client: AsyncClient, auth_headers):
        """Test listing subscriptions when user has none."""
        response = await client.get("/api/feeds", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "items" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) == 0
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_subscriptions(self, client: AsyncClient, auth_headers, test_subscription):
        """Test listing user subscriptions."""
        response = await client.get("/api/feeds", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "items" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) == 1
        assert data["total"] == 1

        subscription = data["items"][0]
        assert subscription["id"] == str(test_subscription.id)
        assert "feed" in subscription
        assert subscription["feed"]["url"] == "https://example.com/feed.xml"

    @pytest.mark.asyncio
    async def test_list_subscriptions_unauthorized(self, client: AsyncClient):
        """Test listing subscriptions without authentication."""
        response = await client.get("/api/feeds")

        assert response.status_code == 401


class TestGetSubscription:
    """Test getting a specific subscription."""

    @pytest.mark.asyncio
    async def test_get_subscription_success(
        self, client: AsyncClient, auth_headers, test_subscription
    ):
        """Test getting a specific subscription."""
        response = await client.get(f"/api/feeds/{test_subscription.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == str(test_subscription.id)
        assert "feed" in data
        assert data["feed"]["url"] == "https://example.com/feed.xml"

    @pytest.mark.asyncio
    async def test_get_nonexistent_subscription(self, client: AsyncClient, auth_headers):
        """Test getting a non-existent subscription."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/feeds/{fake_id}", headers=auth_headers)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_subscription_unauthorized(self, client: AsyncClient, test_subscription):
        """Test getting subscription without authentication."""
        response = await client.get(f"/api/feeds/{test_subscription.id}")

        assert response.status_code == 401


class TestCreateSubscription:
    """Test creating subscriptions (discovering feeds)."""

    @pytest.mark.asyncio
    async def test_discover_feed_new_feed(self, client: AsyncClient, auth_headers):
        """Test discovering and subscribing to a new feed."""
        response = await client.post(
            "/api/feeds/discover",
            headers=auth_headers,
            json={"url": "https://newblog.com/feed.xml"},
        )

        assert response.status_code == 201
        data = response.json()

        assert "id" in data
        assert "feed" in data
        assert data["feed"]["url"] == "https://newblog.com/feed.xml"

    @pytest.mark.asyncio
    async def test_discover_feed_existing_feed(self, client: AsyncClient, auth_headers, test_feed):
        """Test subscribing to an existing feed."""
        response = await client.post(
            "/api/feeds/discover", headers=auth_headers, json={"url": test_feed.url}
        )

        assert response.status_code == 201
        data = response.json()

        assert "id" in data
        assert data["feed"]["url"] == test_feed.url

    @pytest.mark.asyncio
    async def test_discover_feed_duplicate_subscription(
        self, client: AsyncClient, auth_headers, test_subscription, test_feed
    ):
        """Test subscribing to an already subscribed feed."""
        response = await client.post(
            "/api/feeds/discover", headers=auth_headers, json={"url": test_feed.url}
        )

        assert response.status_code == 409
        assert "already subscribed" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_discover_feed_unauthorized(self, client: AsyncClient):
        """Test discovering feed without authentication."""
        response = await client.post(
            "/api/feeds/discover", json={"url": "https://example.com/feed.xml"}
        )

        assert response.status_code == 401


class TestUpdateSubscription:
    """Test updating subscription settings."""

    @pytest.mark.asyncio
    async def test_update_subscription_custom_title(
        self, client: AsyncClient, auth_headers, test_subscription
    ):
        """Test updating subscription with custom title."""
        response = await client.patch(
            f"/api/feeds/{test_subscription.id}",
            headers=auth_headers,
            json={"custom_title": "My Custom Feed Title"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["custom_title"] == "My Custom Feed Title"

    @pytest.mark.asyncio
    async def test_update_subscription_clear_custom_title(
        self, client: AsyncClient, auth_headers, test_subscription
    ):
        """Test clearing custom title."""
        # First set a custom title
        await client.patch(
            f"/api/feeds/{test_subscription.id}",
            headers=auth_headers,
            json={"custom_title": "Custom Title"},
        )

        # Then clear it
        response = await client.patch(
            f"/api/feeds/{test_subscription.id}", headers=auth_headers, json={"custom_title": None}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["custom_title"] is None

    @pytest.mark.asyncio
    async def test_update_nonexistent_subscription(self, client: AsyncClient, auth_headers):
        """Test updating a non-existent subscription."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.patch(
            f"/api/feeds/{fake_id}", headers=auth_headers, json={"custom_title": "Title"}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_subscription_unauthorized(self, client: AsyncClient, test_subscription):
        """Test updating subscription without authentication."""
        response = await client.patch(
            f"/api/feeds/{test_subscription.id}", json={"custom_title": "Title"}
        )

        assert response.status_code == 401


class TestDeleteSubscription:
    """Test deleting subscriptions."""

    @pytest.mark.asyncio
    async def test_delete_subscription_success(
        self, client: AsyncClient, auth_headers, test_subscription
    ):
        """Test successfully deleting a subscription."""
        response = await client.delete(f"/api/feeds/{test_subscription.id}", headers=auth_headers)

        assert response.status_code == 204

        # Verify it's actually deleted
        get_response = await client.get(f"/api/feeds/{test_subscription.id}", headers=auth_headers)
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_subscription(self, client: AsyncClient, auth_headers):
        """Test deleting a non-existent subscription."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.delete(f"/api/feeds/{fake_id}", headers=auth_headers)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_subscription_unauthorized(self, client: AsyncClient, test_subscription):
        """Test deleting subscription without authentication."""
        response = await client.delete(f"/api/feeds/{test_subscription.id}")

        assert response.status_code == 401


class TestFeedManagement:
    async def test_preview_does_not_create_subscription(self, client, auth_headers, db_session):
        from sqlalchemy import func, select

        from glean_database.models import Feed, Subscription

        preview = await client.post(
            "/api/feeds/validate", headers=auth_headers, json={"url": "https://example.com/new"}
        )
        assert preview.status_code == 200
        assert preview.json()["url"] == "https://example.com/new"
        assert await db_session.scalar(select(func.count()).select_from(Feed)) == 0
        assert await db_session.scalar(select(func.count()).select_from(Subscription)) == 0

    async def test_invalid_feed_never_creates_records(
        self, client, auth_headers, db_session, feed_discovery
    ):
        from sqlalchemy import func, select

        from glean_database.models import Feed, Subscription

        feed_discovery.side_effect = ValueError("No RSS feed found at this URL")
        for endpoint in ("validate", "discover"):
            response = await client.post(
                f"/api/feeds/{endpoint}",
                headers=auth_headers,
                json={"url": "https://example.com/not-a-feed"},
            )
            assert response.status_code == 400
            assert "No RSS feed" in response.json()["detail"]
        assert await db_session.scalar(select(func.count()).select_from(Feed)) == 0
        assert await db_session.scalar(select(func.count()).select_from(Subscription)) == 0

    async def test_moving_does_not_clear_title_and_url_is_immutable(
        self, client, auth_headers, test_subscription, db_session
    ):
        test_subscription.custom_title = "My title"
        await db_session.commit()
        response = await client.patch(
            f"/api/feeds/{test_subscription.id}", headers=auth_headers, json={"folder_id": None}
        )
        assert response.status_code == 200
        assert response.json()["custom_title"] == "My title"
        response = await client.patch(
            f"/api/feeds/{test_subscription.id}",
            headers=auth_headers,
            json={"feed_url": "https://example.com/replacement"},
        )
        assert response.status_code == 422
        await db_session.refresh(test_subscription.feed)
        assert test_subscription.feed.url == "https://example.com/feed.xml"

    async def test_folder_filter_can_include_descendants(
        self, client, auth_headers, test_user, db_session
    ):
        from glean_database.models import Feed, Folder, Subscription

        parent = Folder(user_id=test_user.id, name="Tech", type="feed")
        db_session.add(parent)
        await db_session.flush()
        child = Folder(user_id=test_user.id, name="News", type="feed", parent_id=parent.id)
        feeds = [Feed(url=f"https://example.com/{i}") for i in range(3)]
        db_session.add_all([child, *feeds])
        await db_session.flush()
        db_session.add_all(
            [
                Subscription(user_id=test_user.id, feed_id=feed.id, folder_id=folder_id)
                for feed, folder_id in zip(feeds, [parent.id, child.id, None], strict=True)
            ]
        )
        await db_session.commit()
        direct = await client.get(
            "/api/feeds", headers=auth_headers, params={"folder_id": parent.id}
        )
        recursive = await client.get(
            "/api/feeds",
            headers=auth_headers,
            params={"folder_id": parent.id, "include_descendants": "true"},
        )
        assert direct.json()["total"] == 1
        assert recursive.json()["total"] == 2
        ungrouped = await client.get("/api/feeds", headers=auth_headers, params={"folder_id": ""})
        assert ungrouped.json()["total"] == 1

    async def test_cannot_place_feed_in_another_users_folder(
        self, client, auth_headers, db_session
    ):
        from glean_database.models import Folder, User

        other = User()
        db_session.add(other)
        await db_session.flush()
        folder = Folder(user_id=other.id, name="Private", type="feed")
        db_session.add(folder)
        await db_session.commit()
        response = await client.post(
            "/api/feeds/discover",
            headers=auth_headers,
            json={"url": "https://example.com/new", "folder_id": folder.id},
        )
        assert response.status_code == 400
        assert "folder" in response.json()["detail"].lower()

    async def test_import_export_nested_folders_reuse_and_failure_details(
        self, client, auth_headers, feed_discovery
    ):
        from glean_rss import parse_opml_with_folders

        async def discover(url):
            if url.endswith("/invalid"):
                raise ValueError("No RSS feed found")
            return url, "Valid"

        feed_discovery.side_effect = discover
        opml = """<opml><body>
          <outline text="Tech"><outline text="News"><outline text="A" xmlUrl="https://example.com/a"/></outline></outline>
          <outline text="Life"><outline text="News"><outline text="B" xmlUrl="https://example.com/b"/><outline text="Bad" xmlUrl="https://example.com/invalid"/></outline></outline>
          <outline text="Empty"/>
        </body></opml>"""
        response = await client.post(
            "/api/feeds/import",
            headers=auth_headers,
            files={"file": ("feeds.opml", opml, "application/xml")},
        )
        assert response.status_code == 200
        result = response.json()
        assert (result["success"], result["failed"], result["folders_created"]) == (2, 1, 5)
        assert result["failures"] == [
            {
                "url": "https://example.com/invalid",
                "title": "Bad",
                "folder_path": ["Life", "News"],
                "reason": "No RSS feed found",
            }
        ]
        exported = await client.get("/api/feeds/export", headers=auth_headers)
        assert exported.status_code == 200
        parsed = parse_opml_with_folders(exported.text)
        assert {feed.folder_path for feed in parsed.feeds} == {("Tech", "News"), ("Life", "News")}
        assert ("Empty",) in parsed.folder_paths
        repeat = await client.post(
            "/api/feeds/import", headers=auth_headers, files={"file": ("feeds.opml", opml)}
        )
        assert repeat.json()["folders_created"] == 0
        assert repeat.json()["success"] == 0
        assert repeat.json()["failed"] == 3

    async def test_refresh_status_requires_subscription_access(self, client, auth_headers):
        from uuid import uuid4

        response = await client.get(f"/api/feeds/{uuid4()}/refresh", headers=auth_headers)
        assert response.status_code == 404

    async def test_worker_failure_commits_health_record(self, db_session, test_feed, monkeypatch):
        from contextlib import asynccontextmanager

        from glean_database.models import Feed
        from glean_worker.tasks.feed_fetcher import fetch_feed_task

        feed_id = test_feed.id

        @asynccontextmanager
        async def session_context():
            yield db_session
            await db_session.commit()

        monkeypatch.setattr("glean_worker.tasks.feed_fetcher.get_session_context", session_context)
        monkeypatch.setattr(
            "glean_worker.tasks.feed_fetcher.fetch_feed",
            AsyncMock(side_effect=ValueError("HTTP 404")),
        )
        result = await fetch_feed_task({}, feed_id)
        assert result["status"] == "error"
        db_session.expire_all()
        stored = await db_session.get(Feed, feed_id)
        assert stored.error_count == 1
        assert stored.fetch_error_message == "HTTP 404"
        assert stored.last_fetched_at is not None
        assert stored.last_success_at is None
        assert stored.next_fetch_at is not None

    async def test_worker_304_clears_errors_and_schedules_next_fetch(
        self, db_session, test_feed, monkeypatch
    ):
        from contextlib import asynccontextmanager

        from glean_worker.tasks.feed_fetcher import fetch_feed_task

        test_feed.error_count = 3
        test_feed.fetch_error_message = "Temporary failure"
        test_feed.status = "error"
        await db_session.commit()

        @asynccontextmanager
        async def session_context():
            yield db_session
            await db_session.commit()

        monkeypatch.setattr("glean_worker.tasks.feed_fetcher.get_session_context", session_context)
        monkeypatch.setattr(
            "glean_worker.tasks.feed_fetcher.fetch_feed", AsyncMock(return_value=None)
        )
        result = await fetch_feed_task({}, test_feed.id)
        assert result == {"status": "not_modified", "new_entries": 0}
        await db_session.refresh(test_feed)
        assert test_feed.error_count == 0
        assert test_feed.fetch_error_message is None
        assert test_feed.status == "active"
        assert test_feed.last_success_at == test_feed.last_fetched_at
        assert test_feed.next_fetch_at > test_feed.last_fetched_at
