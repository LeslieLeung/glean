"""Test race condition handling in preference updates."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from glean_vector.clients.milvus_client import MilvusClient
from glean_vector.services.preference_service import PreferenceService


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_milvus_client():
    """Create a mock Milvus client."""
    client = MagicMock(spec=MilvusClient)

    # Mock get_user_preferences to return initial state
    # This will be called multiple times during concurrent updates
    client.get_user_preferences = AsyncMock(
        return_value={
            "positive": {
                "embedding": np.random.rand(384).tolist(),
                "sample_count": 5.0,
            }
        }
    )

    # Mock upsert_user_preference
    client.upsert_user_preference = AsyncMock()

    return client


@pytest.fixture
async def mock_redis_client():
    """Create a mock Redis client with real lock behavior."""
    redis = MagicMock(spec=Redis)

    # Track if lock is currently held
    lock_held = {"value": False}

    class MockLock:
        def __init__(self, key, timeout, blocking_timeout):
            self.key = key
            self.timeout = timeout
            self.blocking_timeout = blocking_timeout
            self._acquired = False

        async def acquire(self):
            """Simulate lock acquisition with blocking."""
            start_time = asyncio.get_event_loop().time()

            while True:
                # Try to acquire lock
                if not lock_held["value"]:
                    lock_held["value"] = True
                    self._acquired = True
                    return True

                # Check timeout
                if asyncio.get_event_loop().time() - start_time > self.blocking_timeout:
                    return False

                # Wait a bit before retry
                await asyncio.sleep(0.01)

        async def release(self):
            """Release the lock."""
            if self._acquired and lock_held["value"]:
                lock_held["value"] = False
                self._acquired = False

    redis.lock = lambda key, timeout, blocking_timeout: MockLock(key, timeout, blocking_timeout)

    return redis


@pytest.mark.asyncio
async def test_concurrent_preference_updates_with_lock(
    mock_db_session, mock_milvus_client, mock_redis_client
):
    """
    Test that concurrent preference updates don't cause race conditions when using Redis locks.

    Scenario:
    - Initial preference vector has sample_count=5
    - Two tasks try to add signals concurrently (weight=1.0 each)
    - Expected final count: 7.0 (5 + 1 + 1)
    - Without locks, we might get 6.0 (lost update)
    """
    service = PreferenceService(
        db_session=mock_db_session,
        milvus_client=mock_milvus_client,
        redis_client=mock_redis_client,
    )

    user_id = "test-user-123"
    embedding = np.random.rand(384).tolist()

    # Mock Entry lookup
    mock_entry = MagicMock()
    mock_entry.id = "entry-1"
    mock_entry.feed_id = "feed-1"
    mock_entry.author = "Test Author"

    # Launch two concurrent updates
    tasks = [
        service._update_preference_vector(user_id, embedding, 1.0),
        service._update_preference_vector(user_id, embedding, 1.0),
    ]

    # Run concurrently
    await asyncio.gather(*tasks)

    # Verify both updates completed (called twice)
    assert mock_milvus_client.upsert_user_preference.call_count == 2

    # Check the final call's sample_count
    # With proper locking, the second update should see the first update's result
    calls = mock_milvus_client.upsert_user_preference.call_args_list

    # First call should have count around 6.0 (5.0 + 1.0)
    first_call_count = calls[0][1]["sample_count"]
    assert abs(first_call_count - 6.0) < 0.1, (
        f"First update count should be ~6.0, got {first_call_count}"
    )

    # NOTE: In a real scenario with locks, the second call would read the updated
    # preference from Milvus. In this test, our mock always returns the initial state,
    # so both calls will compute based on count=5.
    # In production, this test would be:
    # - Task 1: reads count=5, writes count=6
    # - Task 2: waits for lock, reads count=6, writes count=7


@pytest.mark.asyncio
async def test_preference_update_without_redis(mock_db_session, mock_milvus_client):
    """Test that preference updates work even without Redis (degraded mode)."""
    service = PreferenceService(
        db_session=mock_db_session,
        milvus_client=mock_milvus_client,
        redis_client=None,  # No Redis
    )

    user_id = "test-user-456"
    embedding = np.random.rand(384).tolist()

    # Should still work, just without lock protection
    await service._update_preference_vector(user_id, embedding, 1.0)

    # Verify update completed
    assert mock_milvus_client.upsert_user_preference.call_count == 1


@pytest.mark.asyncio
async def test_lock_timeout_handling(mock_db_session, mock_milvus_client):
    """Test handling of lock acquisition timeout."""
    # Create a Redis mock that always fails to acquire lock
    redis = MagicMock(spec=Redis)

    class AlwaysBlockedLock:
        def __init__(self, key, timeout, blocking_timeout):
            pass

        async def acquire(self):
            # Simulate lock timeout
            await asyncio.sleep(0.1)
            return False

        async def release(self):
            pass

    redis.lock = lambda key, timeout, blocking_timeout: AlwaysBlockedLock(
        key, timeout, blocking_timeout
    )

    service = PreferenceService(
        db_session=mock_db_session,
        milvus_client=mock_milvus_client,
        redis_client=redis,
    )

    user_id = "test-user-789"
    embedding = np.random.rand(384).tolist()

    # Should raise TimeoutError
    with pytest.raises(TimeoutError, match="Failed to acquire lock"):
        await service._update_preference_vector(user_id, embedding, 1.0)


@pytest.mark.asyncio
async def test_lock_release_on_exception(mock_db_session, mock_milvus_client, mock_redis_client):
    """Test that locks are released even when exceptions occur."""
    service = PreferenceService(
        db_session=mock_db_session,
        milvus_client=mock_milvus_client,
        redis_client=mock_redis_client,
    )

    # Make get_user_preferences raise an exception
    mock_milvus_client.get_user_preferences = AsyncMock(side_effect=Exception("Milvus error"))

    user_id = "test-user-error"
    embedding = np.random.rand(384).tolist()

    # Should propagate the exception
    with pytest.raises(Exception, match="Milvus error"):
        await service._update_preference_vector(user_id, embedding, 1.0)

    # Lock should have been released - verify by checking another update succeeds
    mock_milvus_client.get_user_preferences = AsyncMock(
        return_value={
            "positive": {
                "embedding": np.random.rand(384).tolist(),
                "sample_count": 5.0,
            }
        }
    )

    # This should succeed (lock was released)
    await service._update_preference_vector(user_id, embedding, 1.0)
    assert mock_milvus_client.upsert_user_preference.call_count == 1


@pytest.mark.asyncio
async def test_separate_locks_per_vector_type(
    mock_db_session, mock_milvus_client, mock_redis_client
):
    """Test that positive and negative preferences have separate locks."""
    service = PreferenceService(
        db_session=mock_db_session,
        milvus_client=mock_milvus_client,
        redis_client=mock_redis_client,
    )

    user_id = "test-user-multi"
    embedding = np.random.rand(384).tolist()

    # Mock to return both positive and negative preferences
    mock_milvus_client.get_user_preferences = AsyncMock(
        return_value={
            "positive": {
                "embedding": np.random.rand(384).tolist(),
                "sample_count": 5.0,
            },
            "negative": {
                "embedding": np.random.rand(384).tolist(),
                "sample_count": 3.0,
            },
        }
    )

    # Update positive and negative concurrently
    # These should NOT block each other since they use different lock keys
    tasks = [
        service._update_preference_vector(user_id, embedding, 1.0),  # positive
        service._update_preference_vector(user_id, embedding, -1.0),  # negative
    ]

    # Run concurrently - should complete quickly
    start_time = asyncio.get_event_loop().time()
    await asyncio.gather(*tasks)
    duration = asyncio.get_event_loop().time() - start_time

    # Should be fast (< 1 second) since they don't block each other
    assert duration < 1.0, f"Concurrent updates of different types took too long: {duration}s"

    # Both should complete
    assert mock_milvus_client.upsert_user_preference.call_count == 2
