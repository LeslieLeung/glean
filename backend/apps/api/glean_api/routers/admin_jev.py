"""Admin-only Jev configuration and connection testing."""

from typing import Annotated, Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.schemas.jev import JevConfig, JevConfigRequest, JevConfigResponse
from glean_core.services import TypedConfigService
from glean_core.services.jev_service import test_connection
from glean_database.models import Entry
from glean_database.session import get_session

from ..dependencies import get_current_admin, get_typed_config_service

router = APIRouter(dependencies=[Depends(get_current_admin)])
ConfigService = Annotated[TypedConfigService, Depends(get_typed_config_service)]


async def _candidate(request: JevConfigRequest, service: TypedConfigService) -> JevConfig:
    current = await service.get(JevConfig)
    values = request.model_dump(exclude={"api_key"})
    values["api_key"] = current.api_key if request.api_key is None else request.api_key or None
    return JevConfig(**values, version=str(uuid4()))


@router.get("/config")
async def get_config(service: ConfigService) -> JevConfigResponse:
    return JevConfigResponse.from_config(await service.get(JevConfig))


@router.put("/config")
async def save_config(request: JevConfigRequest, service: ConfigService) -> JevConfigResponse:
    config = await _candidate(request, service)
    if config.enabled and not config.api_key:
        raise HTTPException(status_code=400, detail="An API key is required to enable Jev")
    await service.set(JevConfig, config)
    return JevConfigResponse.from_config(config)


@router.post("/test")
async def test_config(request: JevConfigRequest, service: ConfigService) -> dict[str, Any]:
    config = await _candidate(request, service)
    try:
        await test_connection(config)
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=400, detail="Could not connect to the Jev server"
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"success": True}


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
    config = await service.get(JevConfig)
    if not config.enabled:
        raise HTTPException(status_code=400, detail="Enable Jev before reclassifying entries")
    # Bump the generation so an in-flight request cannot overwrite this reset.
    await service.update(JevConfig, version=str(uuid4()))
    await session.execute(
        update(Entry).values(classification_status="pending", classification_error=None)
    )
    await session.commit()
    return {"success": True}
