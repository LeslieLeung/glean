"""
Feeds and subscriptions router.

Provides endpoints for feed discovery, subscription management, and OPML import/export.
"""

import asyncio
from typing import Annotated, Any, cast
from uuid import UUID

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, Header, HTTPException, Response, UploadFile, status

from glean_core import RedisKeys, get_logger
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
from glean_core.schemas.feed import (
    FeedRefreshResponse,
    OPMLImportFailure,
    OPMLImportResponse,
    ValidateFeedResponse,
)
from glean_core.services import FeedService, FolderService
from glean_core.services.feed_service import UNSET
from glean_rss import discover_feed, generate_opml, parse_opml_with_folders

from ..dependencies import get_current_user, get_feed_service, get_folder_service, get_redis_pool
from ..feed_refresh import enqueue_feed_refresh, get_feed_refresh_status

router = APIRouter()
logger = get_logger(__name__)


@router.get("")
async def list_subscriptions(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    folder_id: str | None = None,
    page: int = 1,
    per_page: int = 20,
    search: str | None = None,
    include_descendants: bool = False,
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
        current_user.id, page, per_page, folder_id, search, include_descendants
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


@router.post("/validate")
async def validate_feed_url(
    data: DiscoverFeedRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
) -> ValidateFeedResponse:
    try:
        url, title = await asyncio.wait_for(discover_feed(str(data.url)), timeout=30)
    except (ValueError, TimeoutError) as error:
        raise HTTPException(
            status_code=400, detail=str(error) or "Feed validation timed out"
        ) from None
    existing = await feed_service.find_subscription_by_url(current_user.id, url)
    return ValidateFeedResponse(
        url=url,
        title=title,
        existing_subscription_id=existing.id if existing else None,
        existing_folder_id=existing.folder_id if existing else None,
    )


@router.post("/discover", status_code=status.HTTP_201_CREATED)
async def discover_feed_url(
    data: DiscoverFeedRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> SubscriptionResponse:
    # Validate again at the write boundary, including callers bypassing the preview.
    preview = await validate_feed_url(data, current_user, feed_service)
    if preview.existing_subscription_id:
        raise HTTPException(status_code=409, detail="Already subscribed to this feed")
    try:
        subscription = await feed_service.create_subscription(
            current_user.id, preview.url, preview.title, data.folder_id
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    if subscription.feed.last_fetched_at is None:
        try:
            await enqueue_feed_refresh(redis, subscription.feed.id)
        except Exception:
            # The committed subscription remains valid; the scheduler will fetch it.
            logger.exception("Initial feed enqueue failed", extra={"feed_id": subscription.feed.id})
    return subscription


@router.patch("/{subscription_id}")
async def update_subscription(
    subscription_id: UUID,
    data: UpdateSubscriptionRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
) -> SubscriptionResponse:
    """
    Update subscription settings.

    Args:
        subscription_id: Subscription identifier.
        data: Update data (custom_title, folder_id).
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
            str(subscription_id),
            current_user.id,
            data.custom_title if "custom_title" in data.model_fields_set else UNSET,
            data.folder_id if should_update_folder else UNSET,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    subscription_id: UUID,
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
            str(subscription_id), current_user.id
        )

        # Queue vector embedding cleanup if feed was orphaned
        if orphaned_feed_id and entry_ids:
            try:
                await redis.enqueue_job(
                    "cleanup_orphan_embeddings",
                    orphaned_feed_id,
                    entry_ids,
                )
            except Exception:
                logger.warning(
                    "Immediate vector cleanup enqueue failed; durable outbox will retry",
                    extra={"feed_id": orphaned_feed_id},
                    exc_info=True,
                )
        try:
            await cast(Any, redis).sadd(
                RedisKeys.PREFERENCE_PENDING_USERS_KEY,
                current_user.id,
            )
            await redis.enqueue_job(
                "rebuild_user_preference",
                user_id=current_user.id,
            )
        except Exception:
            logger.warning(
                "Immediate preference enqueue failed; durable revision will retry",
                extra={"user_id": current_user.id},
                exc_info=True,
            )
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

    # Queue vector embedding cleanup for each orphaned feed
    for feed_id, entry_ids in orphaned_feeds.items():
        if entry_ids:
            try:
                await redis.enqueue_job(
                    "cleanup_orphan_embeddings",
                    feed_id,
                    entry_ids,
                )
            except Exception:
                logger.warning(
                    "Immediate vector cleanup enqueue failed; durable outbox will retry",
                    extra={"feed_id": feed_id},
                    exc_info=True,
                )
    if deleted_count > 0:
        try:
            await cast(Any, redis).sadd(
                RedisKeys.PREFERENCE_PENDING_USERS_KEY,
                current_user.id,
            )
            await redis.enqueue_job(
                "rebuild_user_preference",
                user_id=current_user.id,
            )
        except Exception:
            logger.warning(
                "Immediate preference enqueue failed; durable revision will retry",
                extra={"user_id": current_user.id},
                exc_info=True,
            )

    return BatchDeleteSubscriptionsResponse(deleted_count=deleted_count, failed_count=failed_count)


@router.get("/{subscription_id}/refresh")
async def feed_refresh_status(
    subscription_id: UUID,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> FeedRefreshResponse:
    try:
        subscription = await feed_service.get_subscription(str(subscription_id), current_user.id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None
    return await get_feed_refresh_status(redis, subscription.feed_id)


@router.post("/{subscription_id}/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_feed(
    subscription_id: UUID,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> FeedRefreshResponse:
    try:
        subscription = await feed_service.get_subscription(str(subscription_id), current_user.id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None
    return await enqueue_feed_refresh(redis, subscription.feed_id)


@router.post("/refresh-all", status_code=status.HTTP_202_ACCEPTED)
async def refresh_all_feeds(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> dict[str, int | str]:
    subscriptions = await feed_service.get_user_subscriptions(current_user.id)
    for subscription in subscriptions:
        await enqueue_feed_refresh(redis, subscription.feed_id)
    return {"status": "queued", "queued_count": len(subscriptions)}


@router.post("/import")
async def import_opml(
    file: UploadFile,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    folder_service: Annotated[FolderService, Depends(get_folder_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> OPMLImportResponse:
    try:
        content = await file.read()
        parsed = parse_opml_with_folders(content.decode("utf-8-sig"))
    except (ValueError, UnicodeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from None

    # Validate network content concurrently, without sharing the database session.
    semaphore = asyncio.Semaphore(5)

    async def validate(url: str) -> tuple[str, str] | str:
        async with semaphore:
            try:
                return await asyncio.wait_for(discover_feed(url), timeout=30)
            except (ValueError, TimeoutError) as error:
                return str(error) or "Feed validation timed out"

    previews = await asyncio.gather(*(validate(feed.xml_url) for feed in parsed.feeds))
    tree = await folder_service.get_folders_tree(current_user.id, "feed")
    folder_ids: dict[tuple[str, ...], str] = {}

    def collect(nodes: list[FolderTreeNode], parent: tuple[str, ...] = ()) -> None:
        for node in nodes:
            path = (*parent, node.name)
            folder_ids[path] = node.id
            collect(node.children, path)

    collect(tree.folders)
    folders_created = 0
    for path in parsed.folder_paths:
        if path not in folder_ids:
            folder = await folder_service.create_folder(
                current_user.id,
                FolderCreate(name=path[-1], type="feed", parent_id=folder_ids.get(path[:-1])),
            )
            folder_ids[path] = folder.id
            folders_created += 1

    failures: list[OPMLImportFailure] = []
    success = 0
    for feed, preview in zip(parsed.feeds, previews, strict=True):
        reason = preview if isinstance(preview, str) else None
        if reason is None:
            assert isinstance(preview, tuple)
            try:
                subscription = await feed_service.create_subscription(
                    current_user.id,
                    preview[0],
                    preview[1],
                    folder_ids.get(feed.folder_path),
                    custom_title=feed.title if feed.title and feed.title != preview[1] else None,
                )
            except ValueError as error:
                reason = str(error)
            else:
                success += 1
                if subscription.feed.last_fetched_at is None:
                    try:
                        await enqueue_feed_refresh(redis, subscription.feed_id)
                    except Exception:
                        logger.exception("Imported feed enqueue failed")
        if reason is not None:
            failures.append(
                OPMLImportFailure(
                    url=feed.xml_url,
                    title=feed.title,
                    folder_path=list(feed.folder_path),
                    reason=reason,
                )
            )

    return OPMLImportResponse(
        success=success,
        failed=len(failures),
        total=len(parsed.feeds),
        folders_created=folders_created,
        failures=failures,
    )


@router.get("/export")
async def export_opml(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    folder_service: Annotated[FolderService, Depends(get_folder_service)],
) -> Response:
    subscriptions = await feed_service.get_user_subscriptions(current_user.id)
    tree = await folder_service.get_folders_tree(current_user.id, "feed")
    folder_paths: dict[str, tuple[str, ...]] = {}

    def collect(nodes: list[FolderTreeNode], parent: tuple[str, ...] = ()) -> None:
        for node in nodes:
            path = (*parent, node.name)
            folder_paths[node.id] = path
            collect(node.children, path)

    collect(tree.folders)
    content = generate_opml(
        [
            {
                "title": sub.custom_title or sub.feed.title,
                "url": sub.feed.url,
                "site_url": sub.feed.site_url,
                "folder_path": folder_paths.get(sub.folder_id, ()) if sub.folder_id else (),
            }
            for sub in subscriptions
        ],
        folder_paths=list(folder_paths.values()),
    )
    return Response(
        content=content,
        media_type="application/xml",
        headers={"Content-Disposition": "attachment; filename=glean-subscriptions.opml"},
    )


@router.get("/{subscription_id}")
async def get_subscription(
    subscription_id: UUID,
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
        return await feed_service.get_subscription(str(subscription_id), current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
