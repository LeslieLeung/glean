"""Tests for ScoreService N+1 query fix."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models import Entry, UserPreferenceStats
from glean_vector.clients.milvus_client import MilvusClient
from glean_vector.services.score_service import ScoreService


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def mock_milvus_client():
    """Create a mock Milvus client."""
    client = MagicMock(spec=MilvusClient)
    return client


@pytest.fixture
def mock_entry():
    """Create a mock entry."""
    entry = MagicMock(spec=Entry)
    entry.id = "entry-1"
    entry.feed_id = "feed-1"
    entry.author = "Test Author"
    return entry


@pytest.fixture
def mock_user_stats():
    """Create mock user preference stats."""
    stats = MagicMock(spec=UserPreferenceStats)
    stats.user_id = "user-1"
    stats.source_affinity = {"feed-1": {"positive": 5, "negative": 1}}
    stats.author_affinity = {"Test Author": {"positive": 3, "negative": 0}}
    return stats


@pytest.mark.asyncio
async def test_calculate_score_caches_user_stats(
    mock_db_session, mock_milvus_client, mock_entry, mock_user_stats
):
    """Test that calculate_score caches UserPreferenceStats to avoid N+1 queries."""
    # Setup mocks - return a coroutine-like object that resolves correctly
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user_stats

    # Track call count manually
    call_count = [0]

    # Make execute return an awaitable that returns mock_result
    async def mock_execute(*args, **kwargs):
        call_count[0] += 1
        return mock_result

    mock_db_session.execute = mock_execute

    mock_milvus_client.get_entry_embedding.return_value = [0.1] * 768
    mock_milvus_client.get_user_preferences.return_value = {
        "positive": {"embedding": [0.2] * 768, "sample_count": 10},
        "negative": {"embedding": [0.1] * 768, "sample_count": 5},
    }

    service = ScoreService(db_session=mock_db_session, milvus_client=mock_milvus_client)

    # Call calculate_score multiple times for the same user
    await service.calculate_score("user-1", "entry-1", entry=mock_entry)
    await service.calculate_score("user-1", "entry-2", entry=mock_entry)
    await service.calculate_score("user-1", "entry-3", entry=mock_entry)

    # DB should be queried only ONCE for UserPreferenceStats
    assert call_count[0] == 1


@pytest.mark.asyncio
async def test_get_user_stats_cache_works(mock_db_session, mock_milvus_client, mock_user_stats):
    """Test that _get_user_stats properly caches results."""
    # Setup mock
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user_stats

    call_count = [0]

    async def mock_execute(*args, **kwargs):
        call_count[0] += 1
        return mock_result

    mock_db_session.execute = mock_execute

    service = ScoreService(db_session=mock_db_session, milvus_client=mock_milvus_client)

    # Call _get_user_stats multiple times
    stats1 = await service._get_user_stats("user-1")
    stats2 = await service._get_user_stats("user-1")
    stats3 = await service._get_user_stats("user-1")

    # Should return the same cached object
    assert stats1 is stats2 is stats3 is mock_user_stats

    # DB should be queried only once
    assert call_count[0] == 1


@pytest.mark.asyncio
async def test_batch_calculate_scores_populates_cache(
    mock_db_session, mock_milvus_client, mock_user_stats
):
    """Test that batch_calculate_scores populates the cache."""
    # Setup mocks
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user_stats

    call_count = [0]

    async def mock_execute(*args, **kwargs):
        call_count[0] += 1
        return mock_result

    mock_db_session.execute = mock_execute

    mock_milvus_client.get_user_preferences.return_value = {
        "positive": {"embedding": [0.2] * 768, "sample_count": 10},
    }
    mock_milvus_client.batch_get_entry_embeddings.return_value = {
        "entry-1": [0.1] * 768,
        "entry-2": [0.15] * 768,
    }

    # Create mock entries
    entry1 = MagicMock(spec=Entry)
    entry1.id = "entry-1"
    entry1.feed_id = "feed-1"
    entry1.author = "Author 1"

    entry2 = MagicMock(spec=Entry)
    entry2.id = "entry-2"
    entry2.feed_id = "feed-2"
    entry2.author = "Author 2"

    service = ScoreService(db_session=mock_db_session, milvus_client=mock_milvus_client)

    # Call batch_calculate_scores
    await service.batch_calculate_scores("user-1", [entry1, entry2])

    # DB should be queried only once for UserPreferenceStats
    assert call_count[0] == 1

    # Cache should be populated
    assert "user-1" in service._user_stats_cache
    assert service._user_stats_cache["user-1"] is mock_user_stats


@pytest.mark.asyncio
async def test_cache_isolates_different_users(mock_db_session, mock_milvus_client, mock_entry):
    """Test that cache correctly isolates stats for different users."""
    # Setup mocks for two different users
    stats_user1 = MagicMock(spec=UserPreferenceStats)
    stats_user1.user_id = "user-1"

    stats_user2 = MagicMock(spec=UserPreferenceStats)
    stats_user2.user_id = "user-2"

    call_count = [0]

    async def mock_execute(query):
        # Return different stats based on call count (first call = user1, second = user2)
        result = MagicMock()
        result.scalar_one_or_none.return_value = stats_user1 if call_count[0] == 0 else stats_user2
        call_count[0] += 1
        return result

    mock_db_session.execute = mock_execute

    service = ScoreService(db_session=mock_db_session, milvus_client=mock_milvus_client)

    # Get stats for both users
    stats1 = await service._get_user_stats("user-1")
    stats2 = await service._get_user_stats("user-2")

    # Should get different stats
    assert stats1 is not stats2
    assert stats1.user_id == "user-1"
    assert stats2.user_id == "user-2"

    # Each user should cause exactly one DB query
    assert call_count[0] == 2

    # Calling again should use cache
    stats1_cached = await service._get_user_stats("user-1")
    stats2_cached = await service._get_user_stats("user-2")

    assert stats1_cached is stats1
    assert stats2_cached is stats2

    # No additional DB queries
    assert call_count[0] == 2
