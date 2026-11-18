"""UUID query filters must reject malformed IDs before calling a service."""

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient

from glean_api.dependencies import (
    get_admin_service,
    get_bookmark_service,
    get_current_admin,
    get_current_user,
    get_entry_service,
    get_feed_service,
    get_score_service,
)
from glean_api.main import create_app

UUID_VALUE = "12345678-abcd-4321-abcd-123456789012"
FILTERS = [
    ("/api/feeds", "folder_id", "get_user_subscriptions_paginated"),
    ("/api/entries", "folder_id", "get_entries"),
    ("/api/entries", "feed_id", "get_entries"),
    ("/api/admin/entries", "feed_id", "list_entries"),
    ("/api/bookmarks", "folder_id", "get_bookmarks"),
    ("/api/bookmarks", "tag_ids", "get_bookmarks"),
]


@pytest.fixture
def query_app() -> tuple[FastAPI, AsyncMock]:
    """Keep real routes and request validation, replacing auth and services."""
    app = create_app()
    service = AsyncMock()
    empty_page = {"items": [], "total": 0, "page": 1, "per_page": 20, "total_pages": 0}
    service.get_user_subscriptions_paginated.return_value = empty_page
    service.get_entries.return_value = empty_page
    service.list_entries.return_value = ([], 0)
    service.get_bookmarks.return_value = {
        "items": [],
        "total": 0,
        "page": 1,
        "per_page": 20,
        "pages": 0,
    }

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=UUID_VALUE)
    app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(id=UUID_VALUE)
    for dependency in (
        get_feed_service,
        get_entry_service,
        get_admin_service,
        get_bookmark_service,
    ):
        app.dependency_overrides[dependency] = lambda: service
    app.dependency_overrides[get_score_service] = lambda: None
    return app, service


@pytest.fixture
def query_client(query_app: tuple[FastAPI, AsyncMock]) -> Iterator[TestClient]:
    # Avoid lifespan startup: validation does not need infrastructure.
    client = TestClient(query_app[0])
    yield client
    client.close()


@pytest.mark.parametrize("path,parameter,method", FILTERS)
@pytest.mark.parametrize(
    "value",
    [UUID_VALUE + "%00", "%00", "not-a-uuid", UUID_VALUE + "x", UUID_VALUE + "%0A"],
)
def test_invalid_uuid_query_never_reaches_service(
    query_client: TestClient,
    query_app: tuple[FastAPI, AsyncMock],
    path: str,
    parameter: str,
    method: str,
    value: str,
) -> None:
    response = query_client.get(f"{path}?{parameter}={value}")

    assert response.status_code == 422
    assert any(error["loc"][:2] == ["query", parameter] for error in response.json()["detail"])
    getattr(query_app[1], method).assert_not_awaited()


@pytest.mark.parametrize("path,parameter,method", FILTERS)
@pytest.mark.parametrize(
    "value", [None, UUID_VALUE, UUID_VALUE.upper(), UUID_VALUE.replace("-", "")]
)
def test_valid_uuid_query_is_passed_to_service_as_string(
    query_client: TestClient,
    query_app: tuple[FastAPI, AsyncMock],
    path: str,
    parameter: str,
    method: str,
    value: str | None,
) -> None:
    response = query_client.get(path, params={parameter: value} if value is not None else {})

    assert response.status_code == 200
    call = getattr(query_app[1], method).await_args
    actual = call.args[3] if path == "/api/feeds" else call.kwargs[parameter]
    expected = UUID_VALUE if value is not None else None
    assert actual == ([expected] if parameter == "tag_ids" and expected is not None else expected)


@pytest.mark.parametrize("path,parameter,method", FILTERS[:-1])
def test_empty_uuid_filter_keeps_existing_sentinel(
    query_client: TestClient,
    query_app: tuple[FastAPI, AsyncMock],
    path: str,
    parameter: str,
    method: str,
) -> None:
    response = query_client.get(path, params={parameter: ""})

    assert response.status_code == 200
    call = getattr(query_app[1], method).await_args
    actual = call.args[3] if path == "/api/feeds" else call.kwargs[parameter]
    assert actual == ""


def test_every_tag_id_is_validated(
    query_client: TestClient, query_app: tuple[FastAPI, AsyncMock]
) -> None:
    response = query_client.get(f"/api/bookmarks?tag_ids={UUID_VALUE}&tag_ids={UUID_VALUE}%00")

    assert response.status_code == 422
    query_app[1].get_bookmarks.assert_not_awaited()


def test_feed_failure_filter_preserves_uuid_validation(
    query_client: TestClient, query_app: tuple[FastAPI, AsyncMock]
) -> None:
    response = query_client.get(
        "/api/feeds",
        params={"folder_id": UUID_VALUE, "include_descendants": "true", "failed_only": "true"},
    )

    assert response.status_code == 200
    query_app[1].get_user_subscriptions_paginated.assert_awaited_once_with(
        UUID_VALUE, 1, 20, UUID_VALUE, None, True, True
    )


def test_bookmark_library_filters_preserve_uuid_validation(
    query_client: TestClient, query_app: tuple[FastAPI, AsyncMock]
) -> None:
    response = query_client.get(
        "/api/bookmarks",
        params={
            "folder_id": UUID_VALUE,
            "tag_ids": UUID_VALUE,
            "search": "annotation",
            "sort": "relevance",
            "order": "asc",
            "unfiled": "true",
            "source_type": "external",
        },
    )

    assert response.status_code == 200
    query_app[1].get_bookmarks.assert_awaited_once_with(
        user_id=UUID_VALUE,
        page=1,
        per_page=20,
        folder_id=UUID_VALUE,
        tag_ids=[UUID_VALUE],
        search="annotation",
        sort="relevance",
        order="asc",
        unfiled=True,
        source_type="external",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["/api/feeds", "/api/feeds?include_descendants=true", "/api/entries"]
)
async def test_null_byte_folder_filter_with_database(
    client: AsyncClient, auth_headers: dict[str, str], path: str
) -> None:
    """Exercise the reported payload with real auth, services and PostgreSQL."""
    baseline = await client.get(path, headers=auth_headers)
    assert baseline.status_code == 200

    separator = "&" if "?" in path else "?"
    response = await client.get(
        f"{path}{separator}folder_id=00000000-0000-0000-0000-000000000001%00",
        headers=auth_headers,
    )

    assert response.status_code == 422
