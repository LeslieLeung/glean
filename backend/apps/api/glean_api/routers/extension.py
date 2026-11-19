"""Browser extension endpoints authenticated with personal API tokens."""

from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, HttpUrl, field_validator

from glean_core.schemas import DiscoverFeedRequest, UserResponse
from glean_core.schemas.bookmark import BookmarkCreate
from glean_core.services import APITokenService, BookmarkService, FeedService, UserService

from ..dependencies import (
    get_api_token_service,
    get_bookmark_service,
    get_feed_service,
    get_redis_pool,
    get_user_service,
)
from .bookmarks import create_bookmark
from .feeds import discover_feed_url

router = APIRouter()
api_key = HTTPBearer(scheme_name="GleanAPIKey", bearerFormat="glean_…")


async def get_extension_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(api_key)],
    token_service: Annotated[APITokenService, Depends(get_api_token_service)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Identify the active account that owns the supplied API token."""
    token = await token_service.verify_token(credentials.credentials)
    if token is not None:
        user = await user_service.get_user(token.user_id)
        if user.is_active:
            await token_service.update_last_used(token.id)
            return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


ExtensionUser = Annotated[UserResponse, Depends(get_extension_user)]


class ExtensionPage(BaseModel):
    url: HttpUrl = Field(max_length=2048)

    @field_validator("url")
    @classmethod
    def reject_url_credentials(cls, url: HttpUrl) -> HttpUrl:
        if url.username is not None or url.password is not None:
            raise ValueError("URLs must not contain credentials")
        return url


class ExtensionBookmark(ExtensionPage):
    title: str | None = Field(default=None, max_length=500)


@router.get("/connection", status_code=status.HTTP_204_NO_CONTENT)
async def check_connection(_user: ExtensionUser, response: Response) -> None:
    """Verify the extension's Glean instance and API key."""
    response.headers["Cache-Control"] = "no-store"


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED, response_class=Response)
async def subscribe(
    data: ExtensionPage,
    user: ExtensionUser,
    feed_service: Annotated[FeedService, Depends(get_feed_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> None:
    """Discover and subscribe to a feed from a page or feed URL."""
    await discover_feed_url(DiscoverFeedRequest(url=data.url), user, feed_service, redis)


@router.post("/bookmarks", status_code=status.HTTP_201_CREATED, response_class=Response)
async def bookmark_page(
    data: ExtensionBookmark,
    user: ExtensionUser,
    bookmark_service: Annotated[BookmarkService, Depends(get_bookmark_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> None:
    """Bookmark a web page using the existing metadata and snapshot pipeline."""
    await create_bookmark(
        BookmarkCreate(url=str(data.url), title=data.title), user, bookmark_service, redis
    )
