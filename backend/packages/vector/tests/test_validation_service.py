"""Vector backend capability validation regressions."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from glean_vector.services.validation_service import EmbeddingValidationService


class _ExtensionResult:
    def __init__(self, values: tuple[bool, bool, bool]) -> None:
        self.values = values

    def one(self) -> tuple[bool, bool, bool]:
        return self.values


class _Connection:
    def __init__(self, values: tuple[bool, bool, bool]) -> None:
        self.values = values

    async def execute(self, _statement: Any) -> _ExtensionResult:
        return _ExtensionResult(self.values)


class _ConnectionContext:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, *_args: Any) -> None:
        return None


class _Engine:
    def __init__(self, values: tuple[bool, bool, bool]) -> None:
        self.connection = _Connection(values)
        self.dispose = AsyncMock()

    def connect(self) -> _ConnectionContext:
        return _ConnectionContext(self.connection)


@pytest.mark.asyncio
async def test_pgvector_validation_rejects_unavailable_extension() -> None:
    engine = _Engine((False, False, True))
    with patch(
        "sqlalchemy.ext.asyncio.create_async_engine",
        return_value=engine,
    ):
        result = await EmbeddingValidationService().validate_pgvector(1536)

    assert result.success is False
    assert "not available" in result.message
    assert result.details["vector_extension_available"] is False
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_pgvector_validation_rejects_missing_create_privilege() -> None:
    engine = _Engine((False, True, False))
    with patch(
        "sqlalchemy.ext.asyncio.create_async_engine",
        return_value=engine,
    ):
        result = await EmbeddingValidationService().validate_pgvector(1536)

    assert result.success is False
    assert "cannot install" in result.message
    assert result.details["can_create_extension"] is False
    engine.dispose.assert_awaited_once()
