"""Admin-only System One article classification configuration and connection testing."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.schemas.systemone import (
    ProviderId,
    ProviderProfile,
    SystemOneConfig,
    SystemOneConfigRequest,
    SystemOneConfigResponse,
)
from glean_core.services import TypedConfigService
from glean_core.services.systemone_providers import get_provider, list_provider_descriptors
from glean_core.services.systemone_service import resolve_connection, test_connection
from glean_database.models import Entry
from glean_database.session import get_session

from ..dependencies import get_current_admin, get_typed_config_service

router = APIRouter(dependencies=[Depends(get_current_admin)])
ConfigService = Annotated[TypedConfigService, Depends(get_typed_config_service)]


async def _candidate(
    request: SystemOneConfigRequest, service: TypedConfigService
) -> SystemOneConfig:
    current = await service.get(SystemOneConfig)
    target_provider: ProviderId = (
        request.provider if request.provider is not None else current.provider
    )

    merged_providers: dict[ProviderId, ProviderProfile] = {
        pid: profile.model_copy() for pid, profile in current.providers.items()
    }
    if request.providers is not None:
        for pid, profile in request.providers.items():
            updates = profile.model_dump(exclude_unset=True)
            existing = merged_providers.get(pid, ProviderProfile())
            merged_providers[pid] = existing.model_copy(update=updates)

    active_updates: dict[str, Any] = {}
    for field_name in ("base_url", "model", "account_id"):
        if field_name in request.model_fields_set:
            active_updates[field_name] = getattr(request, field_name)
    if active_updates:
        existing_active = merged_providers.get(target_provider, ProviderProfile())
        merged_providers[target_provider] = existing_active.model_copy(update=active_updates)

    merged_keys: dict[ProviderId, str] = dict(current.provider_api_keys)
    if request.provider_api_keys is not None:
        for pid, key in request.provider_api_keys.items():
            if key is None:
                continue
            if key == "":
                merged_keys.pop(pid, None)
            else:
                merged_keys[pid] = key

    if request.api_key is not None:
        if request.api_key == "":
            merged_keys.pop(target_provider, None)
        else:
            merged_keys[target_provider] = request.api_key

    return SystemOneConfig(
        enabled=request.enabled,
        provider=target_provider,
        providers=merged_providers,
        provider_api_keys=merged_keys,
        ai_prompt=request.ai_prompt,
        classify_content=request.classify_content,
        content_prompt=request.content_prompt,
        categories=request.categories,
        version=str(uuid4()),
    )


async def run_test_config(
    request: SystemOneConfigRequest,
    service: TypedConfigService,
    tester: Callable[[SystemOneConfig], Awaitable[None]],
) -> dict[str, Any]:
    config = await _candidate(request, service)
    provider_name = get_provider(config.provider).descriptor.name
    try:
        await tester(config)
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=400, detail=f"Could not connect to {provider_name}"
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"success": True}


@router.get("/config")
async def get_config(service: ConfigService) -> SystemOneConfigResponse:
    return SystemOneConfigResponse.from_config(
        await service.get(SystemOneConfig), list_provider_descriptors()
    )


@router.put("/config")
async def save_config(
    request: SystemOneConfigRequest, service: ConfigService
) -> SystemOneConfigResponse:
    config = await _candidate(request, service)
    if config.enabled:
        try:
            resolve_connection(config, require_credentials=True)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    await service.set(SystemOneConfig, config)
    return SystemOneConfigResponse.from_config(config, list_provider_descriptors())


@router.post("/test")
async def test_config(request: SystemOneConfigRequest, service: ConfigService) -> dict[str, Any]:
    return await run_test_config(request, service, test_connection)


@router.get("/status")
async def classification_status(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    rows = await session.execute(
        select(Entry.classification_status, func.count()).group_by(Entry.classification_status)
    )
    counts = {str(state): int(count) for state, count in rows}
    latest_error = await session.scalar(
        select(Entry.classification_error)
        .where(Entry.classification_status == "failed")
        .order_by(Entry.classified_at.desc())
        .limit(1)
    )
    return {"counts": counts, "last_error": latest_error}


@router.post("/reclassify")
async def reclassify_entries(
    service: ConfigService,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, bool]:
    config = await service.get(SystemOneConfig)
    if not config.enabled:
        raise HTTPException(
            status_code=400, detail="Enable classification before reclassifying entries"
        )
    try:
        resolve_connection(config, require_credentials=True)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    # Bump the generation so an in-flight request cannot overwrite this reset.
    await service.update(SystemOneConfig, version=str(uuid4()))
    await session.execute(
        update(Entry).values(classification_status="pending", classification_error=None)
    )
    await session.commit()
    return {"success": True}
