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
        from mcp.server.auth.middleware.auth_context import auth_context_var
        from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
        from mcp.server.auth.provider import AccessToken

        from glean_api.mcp.tools.entries import search_entries

        # Mock authentication
        access_token = AccessToken(
            token="test-token", client_id="test-client", scopes=[f"user:{test_user.id}"]
        )
        auth_context_var.set(AuthenticatedUser(access_token))

        # Try to search with 1 character
        result = await search_entries(None, "a", None, 20)  # type: ignore[arg-type]

        assert isinstance(result, list)
        assert len(result) == 1
        assert "error" in result[0]
        error_msg = result[0].get("error")
        assert isinstance(error_msg, str)
        assert "at least 2 characters" in error_msg

    @pytest.mark.asyncio
    async def test_search_query_too_long(self, db_session: AsyncSession, test_user):
        """Test that search queries longer than 200 characters are rejected."""
        from mcp.server.auth.middleware.auth_context import auth_context_var
        from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
        from mcp.server.auth.provider import AccessToken

        from glean_api.mcp.tools.entries import search_entries

        # Mock authentication
        access_token = AccessToken(
            token="test-token", client_id="test-client", scopes=[f"user:{test_user.id}"]
        )
        auth_context_var.set(AuthenticatedUser(access_token))

        # Try to search with 201 characters
        long_query = "x" * 201
        result = await search_entries(None, long_query, None, 20)  # type: ignore[arg-type]

        assert isinstance(result, list)
        assert len(result) == 1
        assert "error" in result[0]
        error_msg = result[0].get("error")
        assert isinstance(error_msg, str)
        assert "at most 200 characters" in error_msg

    @pytest.mark.asyncio
    async def test_search_query_empty_string(self, db_session: AsyncSession, test_user):
        """Test that empty search queries are rejected."""
        from mcp.server.auth.middleware.auth_context import auth_context_var
        from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
        from mcp.server.auth.provider import AccessToken

        from glean_api.mcp.tools.entries import search_entries

        # Mock authentication
        access_token = AccessToken(
            token="test-token", client_id="test-client", scopes=[f"user:{test_user.id}"]
        )
        auth_context_var.set(AuthenticatedUser(access_token))

        result = await search_entries(None, "", None, 20)  # type: ignore[arg-type]

        assert isinstance(result, list)
        assert len(result) == 1
        assert "error" in result[0]
        error_msg = result[0].get("error")
        assert isinstance(error_msg, str)
        assert "at least 2 characters" in error_msg


class TestListEntriesByDateValidation:
    """Test list entries by date input validation."""

    @pytest.mark.asyncio
    async def test_invalid_date_format(self, db_session: AsyncSession, test_user):
        """Test that invalid date formats are rejected."""
        from mcp.server.auth.middleware.auth_context import auth_context_var
        from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
        from mcp.server.auth.provider import AccessToken

        from glean_api.mcp.tools.entries import list_entries_by_date

        # Mock authentication
        access_token = AccessToken(
            token="test-token", client_id="test-client", scopes=[f"user:{test_user.id}"]
        )
        auth_context_var.set(AuthenticatedUser(access_token))

        result = await list_entries_by_date(None, "invalid-date", "2024-01-02", None, None, 50)  # type: ignore[arg-type]

        assert isinstance(result, list)
        assert len(result) == 1
        assert "error" in result[0]
        error_msg = result[0].get("error")
        assert isinstance(error_msg, str)
        assert "Invalid date format" in error_msg

    @pytest.mark.asyncio
    async def test_start_date_after_end_date(self, db_session: AsyncSession, test_user):
        """Test that start date after end date is rejected."""
        from mcp.server.auth.middleware.auth_context import auth_context_var
        from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
        from mcp.server.auth.provider import AccessToken

        from glean_api.mcp.tools.entries import list_entries_by_date

        # Mock authentication
        access_token = AccessToken(
            token="test-token", client_id="test-client", scopes=[f"user:{test_user.id}"]
        )
        auth_context_var.set(AuthenticatedUser(access_token))

        result = await list_entries_by_date(None, "2024-01-02", "2024-01-01", None, None, 50)  # type: ignore[arg-type]

        assert isinstance(result, list)
        assert len(result) == 1
        assert "error" in result[0]
        error_msg = result[0].get("error")
        assert isinstance(error_msg, str)
        assert "Start date must be before or equal to end date" in error_msg

    @pytest.mark.asyncio
    async def test_date_range_exceeds_limit(self, db_session: AsyncSession, test_user):
        """Test that date ranges exceeding 365 days are rejected."""
        from mcp.server.auth.middleware.auth_context import auth_context_var
        from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
        from mcp.server.auth.provider import AccessToken

        from glean_api.mcp.tools.entries import list_entries_by_date

        # Mock authentication
        access_token = AccessToken(
            token="test-token", client_id="test-client", scopes=[f"user:{test_user.id}"]
        )
        auth_context_var.set(AuthenticatedUser(access_token))

        result = await list_entries_by_date(None, "2023-01-01", "2024-01-02", None, None, 50)  # type: ignore[arg-type]

        assert isinstance(result, list)
        assert len(result) == 1
        assert "error" in result[0]
        error_msg = result[0].get("error")
        assert isinstance(error_msg, str)
        assert "cannot exceed 365 days" in error_msg


class TestSearchEntriesLikeInjection:
    """Test LIKE injection prevention in search."""

    @pytest.mark.asyncio
    async def test_search_with_percent_wildcard(self, mcp_db_session: AsyncSession):
        """Test that % wildcards are escaped in search queries."""
        from datetime import UTC, datetime

        from mcp.server.auth.middleware.auth_context import auth_context_var
        from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
        from mcp.server.auth.provider import AccessToken

        from glean_api.mcp.tools.entries import search_entries
        from glean_core.schemas.user import UserCreate
        from glean_core.services.user_service import UserService

        # Create user
        user_service = UserService(mcp_db_session)
        user = await user_service.create_user(
            UserCreate(email="test_like@example.com", name="Test User", password="TestPass123")
        )
        await mcp_db_session.commit()

        # Create feed
        feed = Feed(
            url="https://example.com/feed.xml",
            title="Test Feed",
            description="A test RSS feed",
            status="active",
        )
        mcp_db_session.add(feed)
        await mcp_db_session.flush()

        # Create subscription
        subscription = Subscription(user_id=str(user.id), feed_id=str(feed.id))
        mcp_db_session.add(subscription)

        # Create entries
        entry1 = Entry(
            feed_id=str(feed.id),
            title="Test Entry with 50%",
            url="https://example.com/1",
            content="Content with % symbol",
            summary="Summary",
            published_at=datetime.now(UTC),
        )
        entry2 = Entry(
            feed_id=str(feed.id),
            title="Test Entry without wildcard",
            url="https://example.com/2",
            content="Normal content",
            summary="Summary",
            published_at=datetime.now(UTC),
        )
        mcp_db_session.add_all([entry1, entry2])
        await mcp_db_session.commit()

        # Mock authentication
        access_token = AccessToken(
            token="test-token", client_id="test-client", scopes=[f"user:{user.id}"]
        )
        auth_context_var.set(AuthenticatedUser(access_token))

        # Search for literal % character - use "50%" to test escaping
        # Without escaping, "%" would match all entries as a wildcard
        # With proper escaping, it should only match entries containing literal "%"
        result = await search_entries(None, "50%", None, 20)  # type: ignore[arg-type]

        # Should only match entry1, not all entries
        assert isinstance(result, list)
        if result and "error" in result[0]:
            raise AssertionError(f"Search returned error: {result[0]['error']}")
        assert len(result) == 1, f"Expected 1 result, got {len(result)}: {result}"
        title = result[0].get("title")
        assert isinstance(title, str), (
            f"Title should be string, got: {title}, full result: {result[0]}"
        )
        assert "50%" in title

    @pytest.mark.asyncio
    async def test_search_with_underscore_wildcard(self, mcp_db_session: AsyncSession):
        """Test that _ wildcards are escaped in search queries."""
        from datetime import UTC, datetime

        from mcp.server.auth.middleware.auth_context import auth_context_var
        from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
        from mcp.server.auth.provider import AccessToken

        from glean_api.mcp.tools.entries import search_entries
        from glean_core.schemas.user import UserCreate
        from glean_core.services.user_service import UserService

        # Create user
        user_service = UserService(mcp_db_session)
        user = await user_service.create_user(
            UserCreate(email="test_like2@example.com", name="Test User", password="TestPass123")
        )
        await mcp_db_session.commit()

        # Create feed
        feed = Feed(
            url="https://example.com/feed2.xml",
            title="Test Feed",
            description="A test RSS feed",
            status="active",
        )
        mcp_db_session.add(feed)
        await mcp_db_session.flush()

        # Create subscription
        subscription = Subscription(user_id=str(user.id), feed_id=str(feed.id))
        mcp_db_session.add(subscription)

        # Create entries
        entry1 = Entry(
            feed_id=str(feed.id),
            title="test_entry",
            url="https://example.com/1",
            content="Content",
            summary="Summary",
            published_at=datetime.now(UTC),
        )
        entry2 = Entry(
            feed_id=str(feed.id),
            title="testXentry",
            url="https://example.com/2",
            content="Content",
            summary="Summary",
            published_at=datetime.now(UTC),
        )
        mcp_db_session.add_all([entry1, entry2])
        await mcp_db_session.commit()

        # Mock authentication
        access_token = AccessToken(
            token="test-token", client_id="test-client", scopes=[f"user:{user.id}"]
        )
        auth_context_var.set(AuthenticatedUser(access_token))

        # Search for literal _ character
        result = await search_entries(None, "test_", None, 20)  # type: ignore[arg-type]

        # Should only match entry1 (test_entry), not entry2 (testXentry)
        assert isinstance(result, list)
        assert len(result) == 1
        title = result[0].get("title")
        assert isinstance(title, str)
        assert "test_entry" in title


class TestSubscriptionsN1Query:
    """Test that subscriptions list doesn't have N+1 query problem."""

    @pytest.mark.asyncio
    async def test_list_subscriptions_no_n1_query(self, mcp_db_session: AsyncSession):
        """Test that listing subscriptions uses efficient queries."""
        from datetime import UTC, datetime

        from mcp.server.auth.middleware.auth_context import auth_context_var
        from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
        from mcp.server.auth.provider import AccessToken

        from glean_api.mcp.tools.subscriptions import list_subscriptions
        from glean_core.schemas.user import UserCreate
        from glean_core.services.user_service import UserService

        # Create user
        user_service = UserService(mcp_db_session)
        user = await user_service.create_user(
            UserCreate(email="test_n1@example.com", name="Test User", password="TestPass123")
        )
        await mcp_db_session.commit()

        # Create multiple feeds and subscriptions
        # Use unique URLs to avoid conflicts with other tests
        import uuid

        feed_suffix = str(uuid.uuid4())[:8]
        feeds = []
        for i in range(10):
            feed = Feed(
                url=f"https://example.com/n1test-{feed_suffix}-feed{i}.xml",
                title=f"Feed {i}",
                description=f"Test feed {i}",
                status="active",
            )
            mcp_db_session.add(feed)
            feeds.append(feed)

        await mcp_db_session.flush()

        # Create subscriptions for all feeds
        for feed in feeds:
            subscription = Subscription(user_id=str(user.id), feed_id=str(feed.id))
            mcp_db_session.add(subscription)

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
                mcp_db_session.add(entry)

        await mcp_db_session.commit()

        # Mock authentication
        access_token = AccessToken(
            token="test-token", client_id="test-client", scopes=[f"user:{user.id}"]
        )
        auth_context_var.set(AuthenticatedUser(access_token))

        # List subscriptions
        result = await list_subscriptions(None, None)  # type: ignore[arg-type]

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
