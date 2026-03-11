"""
Embedding validation service.

Provides validation for embedding providers and vector backend connections
before enabling vectorization.
"""

import os

from glean_core import get_logger
from glean_core.schemas.config import EmbeddingConfig, ValidationResult
from glean_vector.config import pgvector_config, vector_backend_config

logger = get_logger(__name__)


class EmbeddingValidationService:
    """
    Service for validating embedding configuration.

    Tests provider connections and vector backend availability before
    enabling vectorization to ensure the system will work correctly.
    """

    TEST_TEXT = "This is a test sentence for embedding validation."

    async def infer_dimension(
        self, provider: str, model: str, api_key: str | None = None, base_url: str | None = None
    ) -> ValidationResult:
        """
        Infer embedding dimension by testing the provider.

        Args:
            provider: Embedding provider name
            model: Model name
            api_key: Optional API key
            base_url: Optional base URL

        Returns:
            ValidationResult with inferred dimension in details
        """
        try:
            from glean_vector.clients.embedding_factory import EmbeddingProviderFactory
            from glean_vector.config import EmbeddingConfig as EmbeddingSettings

            # Build minimal settings (dimension will be set to a placeholder)
            settings = EmbeddingSettings(
                provider=provider,
                model=model,
                dimension=1536,  # Placeholder, will be inferred
                api_key=api_key or "",
                base_url=base_url,
            )

            provider_instance = EmbeddingProviderFactory.create(config=settings)

            try:
                # Generate test embedding to infer dimension
                embedding, metadata = await provider_instance.generate_embedding(self.TEST_TEXT)
                actual_dimension = len(embedding)

                logger.info(f"Inferred dimension for {provider}/{model}: {actual_dimension}")
                return ValidationResult(
                    success=True,
                    message=f"Successfully inferred dimension: {actual_dimension}",
                    details={
                        "provider": provider,
                        "model": model,
                        "dimension": actual_dimension,
                        "metadata": metadata,
                    },
                )

            finally:
                await provider_instance.close()

        except Exception as e:
            logger.error(f"Failed to infer dimension: {e}")
            return ValidationResult(
                success=False,
                message=f"Failed to infer dimension: {str(e)}",
                details={"provider": provider, "model": model, "error": str(e)},
            )

    async def validate_provider(self, config: EmbeddingConfig) -> ValidationResult:
        """
        Test embedding provider connection with a sample request.

        Args:
            config: Embedding configuration to test.

        Returns:
            ValidationResult with success status and details.
        """
        try:
            from glean_vector.clients.embedding_factory import EmbeddingProviderFactory
            from glean_vector.config import EmbeddingConfig as EmbeddingSettings

            # Build settings from config
            settings = EmbeddingSettings(
                provider=config.provider,
                model=config.model,
                dimension=config.dimension,
                api_key=config.api_key or "",
                base_url=config.base_url,
                timeout=config.timeout,
                batch_size=config.batch_size,
                max_retries=config.max_retries,
            )

            # Create provider
            provider = EmbeddingProviderFactory.create(config=settings)

            try:
                # Generate test embedding
                embedding, metadata = await provider.generate_embedding(self.TEST_TEXT)

                # Validate dimension
                actual_dimension = len(embedding)
                if actual_dimension != config.dimension:
                    logger.warning(
                        f"Dimension mismatch: expected {config.dimension}, got {actual_dimension}"
                    )
                    return ValidationResult(
                        success=False,
                        message=f"Dimension mismatch: expected {config.dimension}, got {actual_dimension}",
                        details={
                            "expected_dimension": config.dimension,
                            "actual_dimension": actual_dimension,
                            "provider": config.provider,
                            "model": config.model,
                        },
                    )

                logger.info(f"Provider validation successful: {config.provider}/{config.model}")
                return ValidationResult(
                    success=True,
                    message="Provider connection successful",
                    details={
                        "provider": config.provider,
                        "model": config.model,
                        "dimension": actual_dimension,
                        "metadata": metadata,
                    },
                )

            finally:
                await provider.close()

        except ImportError as e:
            logger.error(f"Provider import error: {e}")
            return ValidationResult(
                success=False,
                message=f"Provider not available: {config.provider}. {str(e)}",
                details={"provider": config.provider, "error": str(e)},
            )

        except Exception as e:
            logger.error(f"Provider validation failed: {e}")
            return ValidationResult(
                success=False,
                message=f"Provider connection failed: {str(e)}",
                details={
                    "provider": config.provider,
                    "model": config.model,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

    async def validate_milvus(
        self,
        dimension: int | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> ValidationResult:
        """
        Test Milvus connection (read-only, does not modify collections).

        This validation only tests the connection to Milvus and checks if
        collections exist. It does NOT create or modify collections to avoid
        accidental data loss during validation.

        Args:
            dimension: Optional dimension (for informational purposes only).
            provider: Optional embedding provider (for informational purposes only).
            model: Optional model name (for informational purposes only).

        Returns:
            ValidationResult with success status and details.
        """
        try:
            from pymilvus import connections, utility

            from glean_vector.config import milvus_config

            try:
                # Test connection
                connections.connect(  # type: ignore[reportUnknownMemberType]
                    alias="validation",
                    host=milvus_config.host,
                    port=str(milvus_config.port),
                    user=milvus_config.user or "",
                    password=milvus_config.password or "",
                )

                # Check if collections exist (read-only)
                entries_exists: bool = utility.has_collection(  # type: ignore[reportUnknownVariableType]
                    milvus_config.entries_collection, using="validation"
                )
                prefs_exists: bool = utility.has_collection(  # type: ignore[reportUnknownVariableType]
                    milvus_config.prefs_collection, using="validation"
                )

                logger.info("Milvus validation successful")
                return ValidationResult(
                    success=True,
                    message="Milvus connection successful",
                    details={
                        "host": milvus_config.host,
                        "port": milvus_config.port,
                        "entries_collection": milvus_config.entries_collection,
                        "entries_collection_exists": entries_exists,
                        "prefs_collection": milvus_config.prefs_collection,
                        "prefs_collection_exists": prefs_exists,
                        "dimension": dimension,
                        "provider": provider,
                        "model": model,
                    },
                )

            finally:
                import contextlib

                with contextlib.suppress(Exception):
                    connections.disconnect("validation")

        except ImportError as e:
            logger.error(f"Milvus import error: {e}")
            return ValidationResult(
                success=False,
                message=f"Milvus client not available: {str(e)}",
                details={"error": str(e)},
            )

        except Exception as e:
            logger.error(f"Milvus validation failed: {e}")
            return ValidationResult(
                success=False,
                message=f"Milvus connection failed: {str(e)}",
                details={
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

    async def validate_pgvector(
        self,
        dimension: int | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> ValidationResult:
        """
        Test pgvector backend connection.
        """
        try:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine

            database_url = pgvector_config.database_url or os.getenv("DATABASE_URL", "")
            if not database_url:
                return ValidationResult(
                    success=False,
                    message="PGVECTOR_DATABASE_URL or DATABASE_URL is required",
                    details={},
                )

            engine = create_async_engine(database_url, echo=False)
            try:
                async with engine.connect() as conn:
                    result = await conn.execute(
                        text("SELECT extname FROM pg_extension WHERE extname='vector'")
                    )
                    has_extension = result.scalar_one_or_none() is not None

                    entries_regclass = await conn.execute(
                        text("SELECT to_regclass(:table_name)"),
                        {"table_name": pgvector_config.entries_table},
                    )
                    prefs_regclass = await conn.execute(
                        text("SELECT to_regclass(:table_name)"),
                        {"table_name": pgvector_config.prefs_table},
                    )
                    metadata_regclass = await conn.execute(
                        text("SELECT to_regclass(:table_name)"),
                        {"table_name": pgvector_config.metadata_table},
                    )

                    entries_exists = entries_regclass.scalar_one_or_none() is not None
                    prefs_exists = prefs_regclass.scalar_one_or_none() is not None
                    metadata_exists = metadata_regclass.scalar_one_or_none() is not None

                    collections_exist = entries_exists and prefs_exists
                    expected_signature = None
                    if provider and model and dimension:
                        expected_signature = f"{provider}:{model}:{dimension}"

                    is_compatible = True
                    compatibility_reason: str | None = None
                    model_signatures: dict[str, str] = {}

                    if expected_signature and collections_exist:
                        if metadata_exists:
                            _quoted_table = (
                                '"' + pgvector_config.metadata_table.replace('"', '""') + '"'
                            )
                            rows = await conn.execute(
                                text(  # noqa: S608
                                    f"SELECT name, model_signature FROM {_quoted_table}"
                                    " WHERE name IN ('entries', 'preferences')"
                                )
                            )
                            model_signatures = {str(row[0]): str(row[1]) for row in rows.fetchall()}
                            for target_name in ("entries", "preferences"):
                                current_signature = model_signatures.get(target_name)
                                if not current_signature:
                                    is_compatible = False
                                    compatibility_reason = (
                                        f"Missing model signature for {target_name}"
                                    )
                                    break
                                if current_signature != expected_signature:
                                    is_compatible = False
                                    compatibility_reason = (
                                        f"{target_name} signature mismatch: "
                                        f"existing={current_signature}, expected={expected_signature}"
                                    )
                                    break
                        else:
                            is_compatible = False
                            compatibility_reason = (
                                "Model metadata missing for existing pgvector tables"
                            )

                return ValidationResult(
                    success=True,
                    message="pgvector connection successful",
                    details={
                        "database_url_configured": True,
                        "vector_extension_installed": has_extension,
                        "entries_table_exists": entries_exists,
                        "prefs_table_exists": prefs_exists,
                        "metadata_table_exists": metadata_exists,
                        "collections_exist": collections_exist,
                        "is_compatible": is_compatible,
                        "compatibility_reason": compatibility_reason,
                        "expected_signature": expected_signature,
                        "model_signatures": model_signatures,
                        "dimension": dimension,
                        "provider": provider,
                        "model": model,
                    },
                )
            finally:
                await engine.dispose()
        except Exception as e:
            logger.error(f"pgvector validation failed: {e}")
            return ValidationResult(
                success=False,
                message=f"pgvector connection failed: {str(e)}",
                details={"error": str(e), "error_type": type(e).__name__},
            )

    async def validate_vector_backend(
        self,
        dimension: int | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> ValidationResult:
        """
        Validate configured vector backend.
        """
        backend = vector_backend_config.backend.lower()
        if backend == "milvus":
            return await self.validate_milvus(dimension, provider, model)
        if backend == "pgvector":
            return await self.validate_pgvector(dimension, provider, model)
        return ValidationResult(
            success=False,
            message=f"Unsupported vector backend: {vector_backend_config.backend}",
            details={"backend": vector_backend_config.backend},
        )

    async def validate_full(self, config: EmbeddingConfig) -> ValidationResult:
        """
        Perform full validation of provider and Milvus.

        Args:
            config: Embedding configuration to validate.

        Returns:
            ValidationResult with combined status.
        """
        # Validate provider first
        provider_result = await self.validate_provider(config)
        if not provider_result.success:
            return provider_result

        # Validate vector backend
        backend_result = await self.validate_vector_backend(
            config.dimension,
            config.provider,
            config.model,
        )
        if not backend_result.success:
            return ValidationResult(
                success=False,
                message=f"Vector backend validation failed: {backend_result.message}",
                details={
                    "provider_validation": provider_result.details,
                    "backend_validation": backend_result.details,
                },
            )

        return ValidationResult(
            success=True,
            message="Full validation successful",
            details={
                "provider": provider_result.details,
                "backend": backend_result.details,
            },
        )

    async def check_provider_health(self, config: EmbeddingConfig) -> bool:
        """
        Quick health check for the embedding provider.

        Args:
            config: Embedding configuration.

        Returns:
            True if provider is healthy, False otherwise.
        """
        result = await self.validate_provider(config)
        return result.success

    async def check_vector_backend_health(self) -> bool:
        """
        Quick health check for active vector backend.

        Returns:
            True if backend is healthy, False otherwise.
        """
        result = await self.validate_vector_backend()
        return result.success
