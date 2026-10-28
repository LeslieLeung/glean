"""
Admin API endpoint tests.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import RedisKeys
from glean_database.models import (
    Entry,
    Feed,
    Subscription,
    User,
    UserPreferenceStats,
    VectorCleanupPending,
)


@pytest.mark.asyncio
class TestAdminAuth:
    """Test admin authentication endpoints."""

    async def test_admin_login_success(self, client: AsyncClient, admin_user):
        """Test successful admin login."""
        response = await client.post(
            "/api/admin/auth/login", json={"username": "admin_test", "password": "Admin123!"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "admin" in data
        assert data["admin"]["username"] == "admin_test"

    async def test_admin_login_invalid_credentials(self, client: AsyncClient, admin_user):
        """Test admin login with invalid credentials."""
        response = await client.post(
            "/api/admin/auth/login", json={"username": "admin_test", "password": "wrongpassword"}
        )

        assert response.status_code == 401

    async def test_admin_login_nonexistent_user(self, client: AsyncClient):
        """Test admin login with nonexistent user."""
        response = await client.post(
            "/api/admin/auth/login", json={"username": "nonexistent", "password": "password"}
        )

        assert response.status_code == 401

    async def test_get_current_admin(self, client: AsyncClient, admin_headers):
        """Test getting current admin information."""
        response = await client.get("/api/admin/me", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "admin_test"
        assert "role" in data


@pytest.mark.asyncio
class TestAdminUsers:
    """Test admin user management endpoints."""

    async def test_list_users(self, client: AsyncClient, admin_headers, test_user):
        """Test listing users."""
        response = await client.get("/api/admin/users", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "total_pages" in data
        assert len(data["items"]) >= 1

    async def test_list_users_with_pagination(self, client: AsyncClient, admin_headers, test_user):
        """Test listing users with pagination."""
        response = await client.get(
            "/api/admin/users", headers=admin_headers, params={"page": 1, "per_page": 10}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["per_page"] == 10

    async def test_list_users_with_search(self, client: AsyncClient, admin_headers, test_user):
        """Test listing users with search."""
        response = await client.get(
            "/api/admin/users", headers=admin_headers, params={"search": "test@example.com"}
        )

        assert response.status_code == 200
        data = response.json()
        if data["total"] > 0:
            assert any("test@example.com" in user["email"] for user in data["items"])

    async def test_list_users_unauthorized(self, client: AsyncClient, auth_headers):
        """Test that regular users cannot access admin endpoints."""
        response = await client.get("/api/admin/users", headers=auth_headers)

        assert response.status_code == 403

    async def test_toggle_user_status_disable(self, client: AsyncClient, admin_headers, test_user):
        """Test disabling a user."""
        user_id = test_user.id

        response = await client.patch(
            f"/api/admin/users/{user_id}/status",
            headers=admin_headers,
            json={"is_active": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    async def test_toggle_user_status_enable(self, client: AsyncClient, admin_headers, test_user):
        """Test enabling a user."""
        user_id = test_user.id

        # First disable
        await client.patch(
            f"/api/admin/users/{user_id}/status",
            headers=admin_headers,
            json={"is_active": False},
        )

        # Then enable
        response = await client.patch(
            f"/api/admin/users/{user_id}/status",
            headers=admin_headers,
            json={"is_active": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True

    async def test_toggle_user_status_nonexistent(self, client: AsyncClient, admin_headers):
        """Test toggling status of nonexistent user."""
        response = await client.patch(
            "/api/admin/users/00000000-0000-0000-0000-000000000000/status",
            headers=admin_headers,
            json={"is_active": False},
        )

        assert response.status_code == 404


@pytest.mark.asyncio
class TestAdminStats:
    """Test admin statistics endpoints."""

    async def test_get_dashboard_stats(self, client: AsyncClient, admin_headers, test_user):
        """Test getting dashboard statistics."""
        response = await client.get("/api/admin/stats", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "total_users" in data
        assert "active_users" in data
        assert "total_feeds" in data
        assert "total_entries" in data
        assert "total_subscriptions" in data
        assert "new_users_today" in data
        assert "new_entries_today" in data
        assert data["total_users"] >= 1

    async def test_get_dashboard_stats_unauthorized(self, client: AsyncClient):
        """Test that stats endpoint requires authentication."""
        response = await client.get("/api/admin/stats")

        assert response.status_code == 401


@pytest.mark.asyncio
class TestAdminHealth:
    """Test admin health check endpoint."""

    async def test_admin_health(self, client: AsyncClient):
        """Test admin health check."""
        response = await client.get("/api/admin/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
class TestAdminFeedDeletion:
    """Admin feed deletion must preserve external cleanup and preference invariants."""

    async def test_delete_feed_stages_cleanup_and_invalidates_preferences(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
        test_mock_redis,
    ) -> None:
        test_feed = Feed(url="https://example.com/admin-delete.xml", title="Admin delete feed")
        db_session.add(test_feed)
        await db_session.flush()
        test_subscription = Subscription(user_id=test_user.id, feed_id=test_feed.id)
        entry = Entry(
            feed_id=test_feed.id,
            url="https://example.com/admin-delete-entry",
            title="Admin delete entry",
            guid="admin-delete-entry",
        )
        stats = UserPreferenceStats(
            user_id=test_user.id,
            source_affinity={test_feed.id: {"positive": 2, "negative": 0}},
        )
        db_session.add_all([test_subscription, entry, stats])
        await db_session.commit()
        await db_session.refresh(entry)
        initial_revision = test_user.preference_revision

        response = await client.delete(f"/api/admin/feeds/{test_feed.id}", headers=admin_headers)

        assert response.status_code == 204
        pending = (
            await db_session.execute(
                select(VectorCleanupPending).where(VectorCleanupPending.entry_id == entry.id)
            )
        ).scalar_one()
        assert pending.feed_id == test_feed.id
        await db_session.refresh(test_user)
        await db_session.refresh(stats)
        assert test_user.preference_revision == initial_revision + 1
        assert test_feed.id not in stats.source_affinity
        assert ("cleanup_orphan_embeddings", (test_feed.id, [entry.id])) in (
            test_mock_redis.enqueued_jobs
        )
        assert test_mock_redis.has_key(RedisKeys.PREFERENCE_PENDING_USERS_KEY)

    async def test_batch_delete_stages_each_feed_and_dirties_user_once(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        db_session: AsyncSession,
        test_user: User,
        test_mock_redis,
    ) -> None:
        feeds = [
            Feed(url=f"https://example.com/admin-batch-{index}.xml", title=f"Feed {index}")
            for index in range(2)
        ]
        db_session.add_all(feeds)
        await db_session.flush()
        entries = [
            Entry(
                feed_id=feed.id,
                url=f"https://example.com/admin-batch-entry-{index}",
                title=f"Entry {index}",
                guid=f"admin-batch-entry-{index}",
            )
            for index, feed in enumerate(feeds)
        ]
        subscriptions = [Subscription(user_id=test_user.id, feed_id=feed.id) for feed in feeds]
        stats = UserPreferenceStats(
            user_id=test_user.id,
            source_affinity={feed.id: {"positive": 1, "negative": 0} for feed in feeds},
        )
        db_session.add_all([*entries, *subscriptions, stats])
        await db_session.commit()
        initial_revision = test_user.preference_revision

        response = await client.post(
            "/api/admin/feeds/batch",
            headers=admin_headers,
            json={"action": "delete", "feed_ids": [feed.id for feed in feeds]},
        )

        assert response.status_code == 200
        assert response.json() == {"affected": 2}
        pending_ids = set(
            (
                await db_session.execute(
                    select(VectorCleanupPending.entry_id).where(
                        VectorCleanupPending.entry_id.in_([entry.id for entry in entries])
                    )
                )
            ).scalars()
        )
        assert pending_ids == {entry.id for entry in entries}
        await db_session.refresh(test_user)
        await db_session.refresh(stats)
        assert test_user.preference_revision == initial_revision + 1
        assert stats.source_affinity == {}
        cleanup_jobs = [
            args
            for name, args in test_mock_redis.enqueued_jobs
            if name == "cleanup_orphan_embeddings"
        ]
        assert {args[0] for args in cleanup_jobs} == {feed.id for feed in feeds}
