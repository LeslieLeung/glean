"""
Feeds and subscriptions router.

Provides endpoints for feed discovery, subscription management, and OPML import/export.
"""

from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, Header, HTTPException, Response, UploadFile, status

from glean_core.schemas import (
    BatchDeleteSubscriptionsRequest,
    BatchDeleteSubscriptionsResponse,
    DiscoverFeedRequest,
    FolderCreate,
    FolderTreeNode,
    SubscriptionListResponse,
    SubscriptionResponse,
    SubscriptionSyncResponse,
    UpdateSubscriptionRequest,
    UserResponse,
)
from glean_core.services import FeedService, FolderService
from glean_core.services.feed_service import UNSET
from glean_rss import discover_feed, generate_opml, parse_opml_with_folders

from ..dependencies import get_current_user, get_feed_service, get_folder_service, get_redis_pool

router = APIRouter()


@router.get("")
async def list_subscriptions(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    folder_id: str | None = None,
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
) -> SubscriptionListResponse:
    """
    Get paginated user subscriptions.

    Args:
        current_user: Current authenticated user.
        feed_service: Feed service.
        folder_id: Optional folder filter. Use empty string for ungrouped feeds.
        page: Page number (1-indexed, default 1).
        per_page: Items per page (default 20, max 100).
        search: Optional search query to filter by title or URL.

    Returns:
        Paginated list of user subscriptions.
    """
    # Clamp per_page to reasonable limits
    per_page = max(1, min(per_page, 100))
    page = max(1, page)

    return await feed_service.get_user_subscriptions_paginated(
        current_user.id, page, per_page, folder_id, search
    )


@router.get("/sync/all")
async def sync_all_subscriptions(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    response: Response,
    if_none_match: Annotated[str | None, Header()] = None,
) -> SubscriptionSyncResponse | None:
    """
    Get all subscriptions with ETag support for efficient syncing.

    This endpoint returns all subscriptions for the current user along with
    an ETag. Clients can cache the response and send the ETag in the
    If-None-Match header on subsequent requests. If the data hasn't changed,
    a 304 Not Modified response is returned.

    Args:
        current_user: Current authenticated user.
        feed_service: Feed service.
        response: FastAPI response object for setting headers.
        if_none_match: Optional ETag from client cache.

    Returns:
        All subscriptions with ETag, or 304 if unchanged.
    """
    sync_response = await feed_service.get_user_subscriptions_sync(current_user.id)

    # Set ETag header
    response.headers["ETag"] = f'"{sync_response.etag}"'

    # Check if client has cached data
    if if_none_match:
        # Strip quotes from If-None-Match header if present
        client_etag = if_none_match.strip('"')
        if client_etag == sync_response.etag:
            response.status_code = status.HTTP_304_NOT_MODIFIED
            return None

    return sync_response


@router.get("/{subscription_id}")
async def get_subscription(
    subscription_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
) -> SubscriptionResponse:
    """
    Get a specific subscription.

    Args:
        subscription_id: Subscription identifier.
        current_user: Current authenticated user.
        feed_service: Feed service.

    Returns:
        Subscription details.

    Raises:
        HTTPException: If subscription not found or unauthorized.
    """
    try:
        return await feed_service.get_subscription(subscription_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.post("/discover", status_code=status.HTTP_201_CREATED)
async def discover_feed_url(
    data: DiscoverFeedRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> SubscriptionResponse:
    """
    Discover and subscribe to a feed from URL.

    This endpoint performs feed discovery (tries to fetch and parse the URL).
    For direct subscription without discovery, the feed service will create
    a basic feed if discovery fails.

    Args:
        data: Feed discovery request with URL and optional folder_id.
        current_user: Current authenticated user.
        feed_service: Feed service.
        redis: Redis connection pool for task queue.

    Returns:
        Created subscription.

    Raises:
        HTTPException: If feed discovery fails or already subscribed.
    """
    feed_url = str(data.url)
    feed_title = None

    import contextlib

    with contextlib.suppress(ValueError):
        # Try to discover feed (fetch and parse)
        feed_url, feed_title = await discover_feed(feed_url)

    try:
        # Create subscription (will create feed if needed)
        subscription = await feed_service.create_subscription(
            current_user.id, feed_url, feed_title, data.folder_id
        )

        # Immediately enqueue feed fetch task only if feed has never been fetched
        if subscription.feed.last_fetched_at is None:
            await redis.enqueue_job("fetch_feed_task", subscription.feed.id)

        return subscription
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.patch("/{subscription_id}")
async def update_subscription(
    subscription_id: str,
    data: UpdateSubscriptionRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
) -> SubscriptionResponse:
    """
    Update subscription settings.

    Args:
        subscription_id: Subscription identifier.
        data: Update data (custom_title, folder_id, feed_url).
        current_user: Current authenticated user.
        feed_service: Feed service.

    Returns:
        Updated subscription.

    Raises:
        HTTPException: If subscription not found or unauthorized.
    """
    try:
        # Determine if folder_id was explicitly provided
        # - "__unset__" means not provided, keep unchanged
        # - None means explicitly set to null (remove from folder)
        # - string means move to that folder
        should_update_folder = data.folder_id != "__unset__"

        return await feed_service.update_subscription(
            subscription_id,
            current_user.id,
            data.custom_title,
            data.folder_id if should_update_folder else UNSET,
            str(data.feed_url) if data.feed_url else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    subscription_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> None:
    """
    Delete a subscription and clean up related data.

    This endpoint:
    1. Deletes the user's reading state for entries in this feed
    2. Removes the subscription
    3. If no other users subscribe, deletes the feed and its entries
    4. Queues cleanup of vector embeddings if feed was deleted

    Args:
        subscription_id: Subscription identifier.
        current_user: Current authenticated user.
        feed_service: Feed service.
        redis: Redis connection pool for task queue.

    Raises:
        HTTPException: If subscription not found or unauthorized.
    """
    try:
        orphaned_feed_id, entry_ids = await feed_service.delete_subscription(
            subscription_id, current_user.id
        )

        # Queue Milvus embedding cleanup if feed was orphaned
        if orphaned_feed_id and entry_ids:
            await redis.enqueue_job("cleanup_orphan_embeddings", orphaned_feed_id, entry_ids)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.post("/batch-delete")
async def batch_delete_subscriptions(
    data: BatchDeleteSubscriptionsRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> BatchDeleteSubscriptionsResponse:
    """
    Delete multiple subscriptions at once with cleanup.

    This endpoint performs the same cleanup as single delete for each subscription.

    Args:
        data: Batch delete request with subscription IDs.
        current_user: Current authenticated user.
        feed_service: Feed service.
        redis: Redis connection pool for task queue.

    Returns:
        Result with deleted and failed counts.
    """
    deleted_count, failed_count, orphaned_feeds = await feed_service.batch_delete_subscriptions(
        data.subscription_ids, current_user.id
    )

    # Queue Milvus embedding cleanup for each orphaned feed
    for feed_id, entry_ids in orphaned_feeds.items():
        if entry_ids:
            await redis.enqueue_job("cleanup_orphan_embeddings", feed_id, entry_ids)

    return BatchDeleteSubscriptionsResponse(deleted_count=deleted_count, failed_count=failed_count)


@router.post("/{subscription_id}/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_feed(
    subscription_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> dict[str, str]:
    """
    Manually trigger a feed refresh.

    Args:
        subscription_id: Subscription identifier.
        current_user: Current authenticated user.
        feed_service: Feed service.
        redis: Redis connection pool for task queue.

    Returns:
        Job status message.

    Raises:
        HTTPException: If subscription not found or unauthorized.
    """
    try:
        subscription = await feed_service.get_subscription(subscription_id, current_user.id)
        # Enqueue feed fetch task
        job = await redis.enqueue_job("fetch_feed_task", subscription.feed.id)
        job_id = job.job_id if job else "unknown"
        return {"status": "queued", "job_id": job_id, "feed_id": subscription.feed.id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.post("/refresh-all", status_code=status.HTTP_202_ACCEPTED)
async def refresh_all_feeds(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> dict[str, int | str]:
    """
    Manually trigger a refresh for all user's subscribed feeds.

    Args:
        current_user: Current authenticated user.
        feed_service: Feed service.
        redis: Redis connection pool for task queue.

    Returns:
        Job status with count of queued feeds.
    """
    subscriptions = await feed_service.get_user_subscriptions(current_user.id)
    queued_count = 0

    for subscription in subscriptions:
        await redis.enqueue_job("fetch_feed_task", subscription.feed.id)
        queued_count += 1

    return {"status": "queued", "queued_count": queued_count}


@router.post("/import")
async def import_opml(
    file: UploadFile,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    folder_service: Annotated[FolderService, Depends(get_folder_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> dict[str, int]:
    """
    Import subscriptions from OPML file with folder structure.

    Args:
        file: OPML file upload.
        current_user: Current authenticated user.
        feed_service: Feed service.
        folder_service: Folder service.
        redis: Redis connection pool for task queue.

    Returns:
        Import statistics (success, failed, and folder counts).

    Raises:
        HTTPException: If file is invalid.
    """
    try:
        content = await file.read()
        opml_result = parse_opml_with_folders(content.decode("utf-8"))

        success_count = 0
        failed_count = 0
        folder_count = 0

        # Create folders first and build a mapping of folder name -> folder id
        folder_id_map: dict[str, str] = {}
        for folder_name in opml_result.folders:
            try:
                folder = await folder_service.create_folder(
                    current_user.id,
                    FolderCreate(name=folder_name, type="feed"),
                )
                folder_id_map[folder_name] = folder.id
                folder_count += 1
            except ValueError:
                # Folder might already exist, try to find it
                existing_folders = await folder_service.get_folders_tree(current_user.id, "feed")
                for existing_folder in existing_folders.folders:
                    if existing_folder.name == folder_name:
                        folder_id_map[folder_name] = existing_folder.id
                        break

        # Import feeds with folder assignment
        for opml_feed in opml_result.feeds:
            try:
                # Get folder_id if feed has a folder
                folder_id = folder_id_map.get(opml_feed.folder) if opml_feed.folder else None

                subscription = await feed_service.create_subscription(
                    current_user.id,
                    opml_feed.xml_url,
                    opml_feed.title,
                    folder_id,
                )
                # Immediately enqueue feed fetch task only if feed has never been fetched
                if subscription.feed.last_fetched_at is None:
                    await redis.enqueue_job("fetch_feed_task", subscription.feed.id)
                success_count += 1
            except ValueError:
                # Already subscribed or invalid feed
                failed_count += 1

        return {
            "success": success_count,
            "failed": failed_count,
            "total": len(opml_result.feeds),
            "folders_created": folder_count,
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.get("/export")
async def export_opml(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    folder_service: Annotated[FolderService, Depends(get_folder_service)],
) -> Response:
    """
    Export subscriptions as OPML file with folder structure.

    Args:
        current_user: Current authenticated user.
        feed_service: Feed service.
        folder_service: Folder service.

    Returns:
        OPML file download.
    """
    subscriptions = await feed_service.get_user_subscriptions(current_user.id)

    # Build folder_id -> folder_name mapping
    folder_tree = await folder_service.get_folders_tree(current_user.id, "feed")
    folder_id_to_name: dict[str, str] = {}

    def collect_folders(folders: list[FolderTreeNode]) -> None:
        for folder in folders:
            folder_id_to_name[folder.id] = folder.name
            if folder.children:
                collect_folders(folder.children)

    collect_folders(folder_tree.folders)

    feeds = [
        {
            "title": sub.custom_title or sub.feed.title,
            "url": sub.feed.url,
            "site_url": sub.feed.site_url,
            "folder": folder_id_to_name.get(sub.folder_id) if sub.folder_id else None,
        }
        for sub in subscriptions
    ]

    opml_content = generate_opml(feeds)

    return Response(
        content=opml_content,
        media_type="application/xml",
        headers={"Content-Disposition": "attachment; filename=glean-subscriptions.opml"},
    )
