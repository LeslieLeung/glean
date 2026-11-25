"""Backward-compatible /api/admin/jev alias for /api/admin/classification."""

from typing import Any

from fastapi import APIRouter, Depends

from glean_core.schemas.systemone import SystemOneConfigRequest
from glean_core.services.jev_service import test_connection

from ..dependencies import get_current_admin
from .admin_classification import (
    ConfigService,
    classification_status,
    get_config,
    reclassify_entries,
    run_test_config,
    save_config,
)

router = APIRouter(dependencies=[Depends(get_current_admin)], include_in_schema=False)

router.add_api_route("/config", get_config, methods=["GET"])
router.add_api_route("/config", save_config, methods=["PUT"])
router.add_api_route("/status", classification_status, methods=["GET"])
router.add_api_route("/reclassify", reclassify_entries, methods=["POST"])


@router.post("/test")
async def test_config(request: SystemOneConfigRequest, service: ConfigService) -> dict[str, Any]:
    return await run_test_config(request, service, test_connection)
