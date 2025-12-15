"""Integration tests for feeds and subscriptions API endpoints."""

import pytest
from httpx import AsyncClient


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

        assert response.status_code == 400
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
