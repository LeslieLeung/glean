"""Integration tests for MCP tools."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from glean_api.mcp.tools.entries import escape_like_pattern
from glean_database.models import Entry, Feed, Subscription


class TestEscapeLikePattern:
    """Test LIKE pattern escaping function."""

    def test_escape_percent_wildcard(self):
        """Test escaping percent wildcard."""
        result = escape_like_pattern("test%pattern")
        assert result == r"test\%pattern"

    def test_escape_underscore_wildcard(self):
        """Test escaping underscore wildcard."""
        result = escape_like_pattern("test_pattern")
        assert result == r"test\_pattern"

    def test_escape_both_wildcards(self):
        """Test escaping both wildcards."""
        result = escape_like_pattern("test%_pattern")
        assert result == r"test\%\_pattern"

    def test_escape_multiple_wildcards(self):
        """Test escaping multiple instances of wildcards."""
        result = escape_like_pattern("%test%_%pattern_")
        assert result == r"\%test\%\_\%pattern\_"

    def test_escape_no_wildcards(self):
        """Test pattern with no wildcards."""
        result = escape_like_pattern("test pattern")
        assert result == "test pattern"

    def test_escape_empty_string(self):
        """Test escaping empty string."""
        result = escape_like_pattern("")
        assert result == ""


class TestSearchEntriesValidation:
    """Test search entries input validation."""

    @pytest.mark.asyncio
    async def test_search_query_too_short(self, db_session: AsyncSession, test_user):
        """Test that search queries less than 2 characters are rejected."""
        from mcp.server.auth.middleware.auth_context import set_access_token
        from mcp.server.models import AccessToken

        from glean_api.mcp.tools.entries import search_entries

        # Mock authentication
        access_token = AccessToken(scopes=[f"user:{test_user.id}"])
        set_access_token(access_token)

        # Try to search with 1 character
        result = await search_entries(None, "a", None, 20)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "error" in result[0]
        assert "at least 2 characters" in result[0]["error"]

    @pytest.mark.asyncio
    async def test_search_query_too_long(self, db_session: AsyncSession, test_user):
        """Test that search queries longer than 200 characters are rejected."""
        from mcp.server.auth.middleware.auth_context import set_access_token
        from mcp.server.models import AccessToken

        from glean_api.mcp.tools.entries import search_entries

        # Mock authentication
        access_token = AccessToken(scopes=[f"user:{test_user.id}"])
        set_access_token(access_token)

        # Try to search with 201 characters
        long_query = "x" * 201
        result = await search_entries(None, long_query, None, 20)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "error" in result[0]
        assert "at most 200 characters" in result[0]["error"]

    @pytest.mark.asyncio
    async def test_search_query_empty_string(self, db_session: AsyncSession, test_user):
        """Test that empty search queries are rejected."""
        from mcp.server.auth.middleware.auth_context import set_access_token
        from mcp.server.models import AccessToken

        from glean_api.mcp.tools.entries import search_entries

        # Mock authentication
        access_token = AccessToken(scopes=[f"user:{test_user.id}"])
        set_access_token(access_token)

        result = await search_entries(None, "", None, 20)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "error" in result[0]
        assert "at least 2 characters" in result[0]["error"]


class TestListEntriesByDateValidation:
    """Test list entries by date input validation."""

    @pytest.mark.asyncio
    async def test_invalid_date_format(self, db_session: AsyncSession, test_user):
        """Test that invalid date formats are rejected."""
        from mcp.server.auth.middleware.auth_context import set_access_token
        from mcp.server.models import AccessToken

        from glean_api.mcp.tools.entries import list_entries_by_date

        # Mock authentication
        access_token = AccessToken(scopes=[f"user:{test_user.id}"])
        set_access_token(access_token)

        result = await list_entries_by_date(None, "invalid-date", "2024-01-02", None, None, 50)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "error" in result[0]
        assert "Invalid date format" in result[0]["error"]

    @pytest.mark.asyncio
    async def test_start_date_after_end_date(self, db_session: AsyncSession, test_user):
        """Test that start date after end date is rejected."""
        from mcp.server.auth.middleware.auth_context import set_access_token
        from mcp.server.models import AccessToken

        from glean_api.mcp.tools.entries import list_entries_by_date

        # Mock authentication
        access_token = AccessToken(scopes=[f"user:{test_user.id}"])
        set_access_token(access_token)

        result = await list_entries_by_date(None, "2024-01-02", "2024-01-01", None, None, 50)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "error" in result[0]
        assert "Start date must be before or equal to end date" in result[0]["error"]

    @pytest.mark.asyncio
    async def test_date_range_exceeds_limit(self, db_session: AsyncSession, test_user):
        """Test that date ranges exceeding 365 days are rejected."""
        from mcp.server.auth.middleware.auth_context import set_access_token
        from mcp.server.models import AccessToken

        from glean_api.mcp.tools.entries import list_entries_by_date

        # Mock authentication
        access_token = AccessToken(scopes=[f"user:{test_user.id}"])
        set_access_token(access_token)

        result = await list_entries_by_date(None, "2023-01-01", "2024-01-02", None, None, 50)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "error" in result[0]
        assert "cannot exceed 365 days" in result[0]["error"]


class TestSearchEntriesLikeInjection:
    """Test LIKE injection prevention in search."""

    @pytest.mark.asyncio
    async def test_search_with_percent_wildcard(
        self, db_session: AsyncSession, test_user, test_feed
    ):
        """Test that % wildcards are escaped in search queries."""
        from datetime import UTC, datetime

        from mcp.server.auth.middleware.auth_context import set_access_token
        from mcp.server.models import AccessToken

        from glean_api.mcp.tools.entries import search_entries

        # Create subscription
        subscription = Subscription(user_id=str(test_user.id), feed_id=str(test_feed.id))
        db_session.add(subscription)

        # Create entries
        entry1 = Entry(
            feed_id=str(test_feed.id),
            title="Test Entry with %",
            url="https://example.com/1",
            content="Content with % symbol",
            summary="Summary",
            published_at=datetime.now(UTC),
        )
        entry2 = Entry(
            feed_id=str(test_feed.id),
            title="Test Entry without wildcard",
            url="https://example.com/2",
            content="Normal content",
            summary="Summary",
            published_at=datetime.now(UTC),
        )
        db_session.add_all([entry1, entry2])
        await db_session.commit()

        # Mock authentication
        access_token = AccessToken(scopes=[f"user:{test_user.id}"])
        set_access_token(access_token)

        # Search for literal % character
        result = await search_entries(None, "%", None, 20)

        # Should only match entry1, not all entries
        assert isinstance(result, list)
        assert len(result) == 1
        assert "%" in result[0]["title"]

    @pytest.mark.asyncio
    async def test_search_with_underscore_wildcard(
        self, db_session: AsyncSession, test_user, test_feed
    ):
        """Test that _ wildcards are escaped in search queries."""
        from datetime import UTC, datetime

        from mcp.server.auth.middleware.auth_context import set_access_token
        from mcp.server.models import AccessToken

        from glean_api.mcp.tools.entries import search_entries

        # Create subscription
        subscription = Subscription(user_id=str(test_user.id), feed_id=str(test_feed.id))
        db_session.add(subscription)

        # Create entries
        entry1 = Entry(
            feed_id=str(test_feed.id),
            title="test_entry",
            url="https://example.com/1",
            content="Content",
            summary="Summary",
            published_at=datetime.now(UTC),
        )
        entry2 = Entry(
            feed_id=str(test_feed.id),
            title="testXentry",
            url="https://example.com/2",
            content="Content",
            summary="Summary",
            published_at=datetime.now(UTC),
        )
        db_session.add_all([entry1, entry2])
        await db_session.commit()

        # Mock authentication
        access_token = AccessToken(scopes=[f"user:{test_user.id}"])
        set_access_token(access_token)

        # Search for literal _ character
        result = await search_entries(None, "test_", None, 20)

        # Should only match entry1 (test_entry), not entry2 (testXentry)
        assert isinstance(result, list)
        assert len(result) == 1
        assert "test_entry" in result[0]["title"]


class TestSubscriptionsN1Query:
    """Test that subscriptions list doesn't have N+1 query problem."""

    @pytest.mark.asyncio
    async def test_list_subscriptions_no_n1_query(self, db_session: AsyncSession, test_user):
        """Test that listing subscriptions uses efficient queries."""
        from datetime import UTC, datetime

        from mcp.server.auth.middleware.auth_context import set_access_token
        from mcp.server.models import AccessToken

        from glean_api.mcp.tools.subscriptions import list_subscriptions

        # Create multiple feeds and subscriptions
        feeds = []
        for i in range(10):
            feed = Feed(
                url=f"https://example.com/feed{i}.xml",
                title=f"Feed {i}",
                description=f"Test feed {i}",
                status="active",
            )
            db_session.add(feed)
            feeds.append(feed)

        await db_session.flush()

        # Create subscriptions for all feeds
        for feed in feeds:
            subscription = Subscription(user_id=str(test_user.id), feed_id=str(feed.id))
            db_session.add(subscription)

        # Create entries for each feed
        for feed in feeds:
            for j in range(5):
                entry = Entry(
                    feed_id=str(feed.id),
                    title=f"Entry {j} for {feed.title}",
                    url=f"https://example.com/entry{j}",
                    content="Content",
                    summary="Summary",
                    published_at=datetime.now(UTC),
                )
                db_session.add(entry)

        await db_session.commit()

        # Mock authentication
        access_token = AccessToken(scopes=[f"user:{test_user.id}"])
        set_access_token(access_token)

        # List subscriptions
        result = await list_subscriptions(None, None)

        # Verify results
        assert isinstance(result, list)
        assert len(result) == 10

        # Verify all subscriptions have unread counts
        for sub in result:
            assert "unread_count" in sub
            assert sub["unread_count"] == 5  # 5 unread entries per feed

        # NOTE: To properly test for N+1 queries, you would use a query counter
        # or profiler. This test verifies the functionality works correctly.
        # The implementation now uses a single aggregated query with GROUP BY
        # instead of individual queries for each subscription.
