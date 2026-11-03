"""Shared job identity for manual, initial, and scheduled feed fetches."""

FEED_RESULT_SECONDS = 5
FEED_QUEUE_EXPIRY_SECONDS = 600


def feed_job_id(feed_id: str) -> str:
    return f"fetch_feed:{feed_id}"
