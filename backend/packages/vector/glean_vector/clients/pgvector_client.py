"""pgvector client for vector operations."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import (
    BIGINT,
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    and_,
    cast,
    delete,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from glean_core import get_logger
from glean_vector.config import pgvector_config, resolve_pgvector_database_url

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover
    Vector = None  # type: ignore[assignment,misc]

logger = get_logger(__name__)

# All pgvector clients use the same PostgreSQL advisory lock.  Rebuilds take the
# exclusive form while normal writes take the shared form, so a stale worker can
# never write across the TRUNCATE/model-signature boundary.
_MODEL_FENCE_LOCK_ID = 4_706_563_786_092_671_342
_HNSW_MAX_VECTOR_DIMENSIONS = 2_000


class PgVectorModelMismatchError(RuntimeError):
    """The caller's embedding model does not own the current vector store."""


class PgVectorDimensionError(ValueError):
    """A vector does not have the active model's configured dimension."""


def _quote_ident(name: str) -> str:
    """Return a properly double-quoted PostgreSQL identifier."""
    return '"' + name.replace('"', '""') + '"'


class PgVectorClient:
    """pgvector-backed vector store client."""

    def __init__(self) -> None:
        self.config = pgvector_config
        self._connected = False
        self._engine: AsyncEngine | None = None
        self._session_maker: async_sessionmaker[AsyncSession] | None = None
        self._metadata = MetaData()
        self._entries_table: Table | None = None
        self._prefs_table: Table | None = None
        self._meta_table: Table | None = None
        # Caching flags to avoid repeated DDL / metadata queries
        self._schema_ensured = False
        self._last_model_signature: str | None = None
        self._active_dimension: int | None = None

    @staticmethod
    def _build_model_signature(provider: str, model: str, dimension: int) -> str:
        return f"{provider}:{model}:{dimension}"

    @property
    def _database_url(self) -> str:
        return resolve_pgvector_database_url()

    def _ensure_connected(self) -> None:
        if not self._connected:
            self.connect()

    def connect(self) -> None:
        """Create SQLAlchemy engine/session factory for pgvector operations."""
        if self._connected and self._engine and self._session_maker:
            return
        if Vector is None:
            raise ConnectionError("pgvector package is not installed")
        database_url = self._database_url
        if not database_url:
            raise ConnectionError("PGVECTOR_DATABASE_URL or DATABASE_URL is required")

        self._engine = create_async_engine(database_url, echo=False)
        self._session_maker = async_sessionmaker(self._engine, expire_on_commit=False)
        self._init_tables()
        self._connected = True

    def _init_tables(self) -> None:
        if Vector is None:
            raise RuntimeError("pgvector package is not installed")
        self._metadata = MetaData()
        # Do not put the ``entries`` foreign key in this standalone MetaData.
        # ``MetaData.create_all`` sorts foreign-key dependencies before issuing
        # any DDL and raises NoReferencedTableError when the ORM's ``entries``
        # table is not part of this metadata.  The runtime fallback must also
        # support PGVECTOR_DATABASE_URL pointing at a dedicated database where
        # ``entries`` intentionally does not exist.  A best-effort FK is added
        # after table creation when both stores share a database.
        self._entries_table = Table(
            self.config.entries_table,
            self._metadata,
            Column("id", String(36), primary_key=True),
            Column("embedding", Vector(), nullable=False),  # type: ignore[misc,operator]
            Column("feed_id", String(36), nullable=False, index=True),
            Column("published_at", BIGINT, nullable=False, index=True),
            Column("language", String(10), nullable=False, server_default=""),
            Column("word_count", Integer, nullable=False, server_default="0"),
            Column("author", String(200), nullable=False, server_default=""),
        )
        preference_unique_name = (
            "uq_user_vector_type"
            if self.config.prefs_table == "user_preference_vectors"
            else self._bounded_identifier(f"uq_{self.config.prefs_table}_user_vector_type")
        )
        self._prefs_table = Table(
            self.config.prefs_table,
            self._metadata,
            Column("id", String(50), primary_key=True),
            Column("user_id", String(36), nullable=False, index=True),
            Column("vector_type", String(20), nullable=False),
            Column("embedding", Vector(), nullable=False),  # type: ignore[misc,operator]
            Column("sample_count", Float, nullable=False),
            Column("updated_at", BIGINT, nullable=False),
            UniqueConstraint("user_id", "vector_type", name=preference_unique_name),
        )
        self._meta_table = Table(
            self.config.metadata_table,
            self._metadata,
            Column("name", String(50), primary_key=True),
            Column("model_signature", String(255), nullable=False),
            Column("updated_at", BIGINT, nullable=False),
        )

    async def disconnect(self) -> None:
        """Close connection resources.

        Uses the async ``AsyncEngine.dispose`` so asyncpg connections are closed
        through the running event loop instead of being torn down synchronously
        (which can raise ``MissingGreenlet`` / "Event loop is closed").
        """
        if self._engine is not None:
            await self._engine.dispose()
        self._connected = False
        self._engine = None
        self._session_maker = None
        self._schema_ensured = False
        self._last_model_signature = None
        self._active_dimension = None

    def collections_exist(self) -> bool:
        """Whether required vector tables have been verified to exist.

        Returns the cached result from the most recent ``ensure_collections``
        or ``recreate_collections`` call.  Before either has been called the
        answer is conservatively ``False``.
        """
        return self._schema_ensured

    def check_model_compatibility(
        self, dimension: int, provider: str, model: str
    ) -> tuple[bool, str | None]:
        """Check whether existing data is compatible with the given model config.

        Uses the model signature cached by ``ensure_collections``.
        """
        if not self._schema_ensured:
            return (False, "Collections not yet verified")
        expected = self._build_model_signature(provider, model, dimension)
        if self._last_model_signature == expected:
            return (True, None)
        return (
            False,
            f"Model signature mismatch: current={self._last_model_signature}, expected={expected}",
        )

    @staticmethod
    async def _take_model_lock(executor: Any, *, shared: bool = False) -> None:
        function = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
        await executor.execute(text(f"SELECT {function}({_MODEL_FENCE_LOCK_ID})"))

    async def _load_model_signatures(self, executor: Any) -> dict[str, str]:
        _, _, meta_table = self._tables()
        rows = (
            await executor.execute(
                select(meta_table.c.name, meta_table.c.model_signature).where(
                    meta_table.c.name.in_(["entries", "preferences"])
                )
            )
        ).all()
        return {str(row[0]): str(row[1]) for row in rows}

    def _model_metadata_statements(self, signature: str) -> tuple[Any, Any]:
        _, _, meta_table = self._tables()
        now_ts = int(datetime.now(UTC).timestamp())
        return (
            insert(meta_table)
            .values(name="entries", model_signature=signature, updated_at=now_ts)
            .on_conflict_do_update(
                index_elements=["name"],
                set_={"model_signature": signature, "updated_at": now_ts},
            ),
            insert(meta_table)
            .values(name="preferences", model_signature=signature, updated_at=now_ts)
            .on_conflict_do_update(
                index_elements=["name"],
                set_={"model_signature": signature, "updated_at": now_ts},
            ),
        )

    async def _model_data_exists(self, executor: Any) -> bool:
        entries_table, prefs_table, _ = self._tables()
        result = await executor.exec_driver_sql(
            "SELECT "
            f"EXISTS (SELECT 1 FROM {_quote_ident(entries_table.name)} LIMIT 1) OR "
            f"EXISTS (SELECT 1 FROM {_quote_ident(prefs_table.name)} LIMIT 1)"
        )
        return bool(result.scalar_one())

    async def _validate_stored_dimensions(self, executor: Any, dimension: int) -> None:
        entries_table, prefs_table, _ = self._tables()
        result = await executor.exec_driver_sql(
            "SELECT "
            f"(SELECT count(*) FROM {_quote_ident(entries_table.name)} "
            f"WHERE vector_dims(embedding) IS DISTINCT FROM {dimension}) + "
            f"(SELECT count(*) FROM {_quote_ident(prefs_table.name)} "
            f"WHERE vector_dims(embedding) IS DISTINCT FROM {dimension})"
        )
        invalid_count = int(result.scalar_one())
        if invalid_count:
            raise PgVectorDimensionError(
                f"pgvector contains {invalid_count} vector(s) that do not have "
                f"the configured dimension {dimension}; run a full rebuild"
            )

    @staticmethod
    def _bounded_identifier(name: str) -> str:
        """Keep generated identifiers within PostgreSQL's 63-byte limit."""
        if len(name.encode()) <= 63:
            return name
        digest = sha256(name.encode()).hexdigest()[:12]
        prefix = name.encode()[:46].decode(errors="ignore")
        return f"{prefix}_{digest}"

    def _hnsw_index_name(self) -> str:
        entries_table, _, _ = self._tables()
        return self._bounded_identifier(f"ix_{entries_table.name}_embedding_hnsw")

    async def _ensure_hnsw_index(
        self,
        executor: Any,
        dimension: int,
        *,
        replace: bool = False,
    ) -> None:
        """Create an index whose expression matches similarity-search queries."""
        entries_table, _, _ = self._tables()
        index_name = _quote_ident(self._hnsw_index_name())
        if replace:
            await executor.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")
        if dimension > _HNSW_MAX_VECTOR_DIMENSIONS:
            logger.warning(
                "Skipping pgvector HNSW index because vector dimensions exceed its limit",
                extra={
                    "dimension": dimension,
                    "max_dimension": _HNSW_MAX_VECTOR_DIMENSIONS,
                },
            )
            return
        await executor.exec_driver_sql(
            f"CREATE INDEX IF NOT EXISTS {index_name} "
            f"ON {_quote_ident(entries_table.name)} USING hnsw "
            f"((embedding::vector({dimension})) vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )

    async def _ensure_entry_foreign_key(self, executor: Any) -> None:
        """Add ON DELETE CASCADE only when the relational entries table is local."""
        entries_table, _, _ = self._tables()
        parent_result = await executor.execute(text("SELECT to_regclass('entries')"))
        if parent_result.scalar_one_or_none() is None:
            return

        constraint_name = self._bounded_identifier(f"fk_{entries_table.name}_entry")
        existing_result = await executor.execute(
            text(
                "SELECT 1 FROM pg_constraint "
                "WHERE conrelid = to_regclass(:table_name) "
                "AND confrelid = to_regclass('entries') AND contype = 'f' LIMIT 1"
            ),
            {"table_name": entries_table.name},
        )
        if existing_result.scalar_one_or_none() is not None:
            return

        # NOT VALID avoids making a backend switch fail because of historical
        # orphan rows while still enforcing the relationship for all new writes.
        await executor.exec_driver_sql(
            f"ALTER TABLE {_quote_ident(entries_table.name)} "
            f"ADD CONSTRAINT {_quote_ident(constraint_name)} "
            'FOREIGN KEY ("id") REFERENCES "entries" ("id") '
            "ON DELETE CASCADE NOT VALID"
        )

    async def _assert_active_signature(self, executor: Any, expected: str) -> None:
        signatures = await self._load_model_signatures(executor)
        if signatures.get("entries") != expected or signatures.get("preferences") != expected:
            raise PgVectorModelMismatchError(
                "pgvector model signature changed while this job was running: "
                f"current={signatures or None}, expected={expected}"
            )

    def _require_active_model(self) -> tuple[str, int]:
        if self._last_model_signature is None or self._active_dimension is None:
            raise PgVectorModelMismatchError(
                "pgvector model is not initialized; call ensure_collections with "
                "provider and model before vector operations"
            )
        return self._last_model_signature, self._active_dimension

    def _validate_vector(self, vector: list[float]) -> int:
        _, dimension = self._require_active_model()
        if len(vector) != dimension:
            raise PgVectorDimensionError(
                f"Vector dimension mismatch: got {len(vector)}, expected {dimension}"
            )
        return dimension

    async def _execute_model_write(self, statement: Any) -> Any:
        """Execute a write under a shared lock and re-check its model fence."""
        if self._session_maker is None:
            raise RuntimeError("pgvector client not connected")
        expected, _ = self._require_active_model()
        async with self._session_maker() as session, session.begin():
            await self._take_model_lock(session, shared=True)
            await self._assert_active_signature(session, expected)
            return await session.execute(statement)

    def _tables(self) -> tuple[Table, Table, Table]:
        if self._entries_table is None or self._prefs_table is None or self._meta_table is None:
            raise RuntimeError("pgvector tables not initialized")
        return self._entries_table, self._prefs_table, self._meta_table

    async def ensure_collections(
        self, dimension: int, provider: str | None = None, model: str | None = None
    ) -> None:
        """Ensure schema exists and fence operations to the requested model."""
        self._ensure_connected()
        if self._engine is None:
            raise RuntimeError("pgvector engine unavailable")
        if dimension <= 0:
            raise PgVectorDimensionError("Vector dimension must be positive")
        if bool(provider) != bool(model):
            raise ValueError("provider and model must be supplied together")

        if not self._schema_ensured:
            async with self._engine.begin() as conn:
                await self._take_model_lock(conn)
                await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
                tables = list(self._tables())
                await conn.run_sync(
                    lambda sync_conn: self._metadata.create_all(sync_conn, tables=tables)
                )
                await self._ensure_entry_foreign_key(conn)
            self._schema_ensured = True

        if not provider or not model:
            return

        expected = self._build_model_signature(provider, model, dimension)
        if self._last_model_signature == expected and self._active_dimension == dimension:
            if self._session_maker is None:
                raise RuntimeError("pgvector client not connected")
            # Cached schema identity must not turn readiness into a local-only
            # check. Ping the selected database and verify persisted ownership.
            async with self._session_maker() as session, session.begin():
                await self._take_model_lock(session, shared=True)
                await self._assert_active_signature(session, expected)
            return

        async with self._engine.begin() as conn:
            await self._take_model_lock(conn)
            signatures = await self._load_model_signatures(conn)
            data_exists = await self._model_data_exists(conn)

            if not signatures and not data_exists:
                for statement in self._model_metadata_statements(expected):
                    await conn.execute(statement)
                # Building HNSW on a new/empty store is cheap. Existing stores
                # without this index can add it CONCURRENTLY using DEPLOY.md.
                await self._ensure_hnsw_index(conn, dimension)
                signatures = {"entries": expected, "preferences": expected}

            if signatures.get("entries") != expected or signatures.get("preferences") != expected:
                current = signatures or None
                self._last_model_signature = (
                    signatures.get("entries")
                    if signatures.get("entries") == signatures.get("preferences")
                    else None
                )
                self._active_dimension = None
                raise PgVectorModelMismatchError(
                    f"pgvector model signature mismatch: current={current}, "
                    f"expected={expected}; run a full rebuild"
                )

            await self._validate_stored_dimensions(conn, dimension)

        self._last_model_signature = expected
        self._active_dimension = dimension

    async def recreate_collections(
        self, dimension: int, provider: str | None = None, model: str | None = None
    ) -> None:
        """Atomically clear data, stamp the new model, and rebuild its HNSW index."""
        self._ensure_connected()
        if self._engine is None:
            raise RuntimeError("pgvector engine unavailable")
        if dimension <= 0:
            raise PgVectorDimensionError("Vector dimension must be positive")
        if not provider or not model:
            raise ValueError("provider and model are required when recreating pgvector storage")

        await self.ensure_collections(dimension)
        entries_table, prefs_table, meta_table = self._tables()
        signature = self._build_model_signature(provider, model, dimension)

        async with self._engine.begin() as conn:
            await self._take_model_lock(conn)
            await conn.exec_driver_sql(
                f"TRUNCATE TABLE {_quote_ident(entries_table.name)}, "
                f"{_quote_ident(prefs_table.name)}, {_quote_ident(meta_table.name)}"
            )
            for statement in self._model_metadata_statements(signature):
                await conn.execute(statement)
            await self._ensure_hnsw_index(conn, dimension, replace=True)

        # Publish the new fence only after the transaction commits.
        self._last_model_signature = signature
        self._active_dimension = dimension

    async def insert_entry_embedding(
        self,
        entry_id: str,
        embedding: list[float],
        feed_id: str,
        published_at: datetime | None = None,
        language: str = "",
        word_count: int = 0,
        author: str = "",
    ) -> None:
        self._ensure_connected()
        self._validate_vector(embedding)
        entries_table, _, _ = self._tables()
        published_ts = (
            int(published_at.timestamp()) if published_at else int(datetime.now(UTC).timestamp())
        )
        stmt = (
            insert(entries_table)
            .values(
                id=entry_id,
                embedding=embedding,
                feed_id=feed_id,
                published_at=published_ts,
                language=language or "",
                word_count=word_count,
                author=author or "",
            )
            .on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "embedding": embedding,
                    "feed_id": feed_id,
                    "published_at": published_ts,
                    "language": language or "",
                    "word_count": word_count,
                    "author": author or "",
                },
            )
        )
        await self._execute_model_write(stmt)

    async def get_entry_embedding(self, entry_id: str) -> list[float] | None:
        self._ensure_connected()
        if self._session_maker is None:
            raise RuntimeError("pgvector client not connected")
        entries_table, _, _ = self._tables()
        expected, _ = self._require_active_model()
        async with self._session_maker() as session, session.begin():
            await self._take_model_lock(session, shared=True)
            await self._assert_active_signature(session, expected)
            row = (
                await session.execute(
                    select(entries_table.c.embedding).where(entries_table.c.id == entry_id)
                )
            ).first()
            if not row:
                return None
            return list(row[0]) if row[0] is not None else None

    async def batch_get_entry_embeddings(self, entry_ids: list[str]) -> dict[str, list[float]]:
        self._ensure_connected()
        if not entry_ids:
            return {}
        if self._session_maker is None:
            raise RuntimeError("pgvector client not connected")
        entries_table, _, _ = self._tables()
        expected, _ = self._require_active_model()
        async with self._session_maker() as session, session.begin():
            await self._take_model_lock(session, shared=True)
            await self._assert_active_signature(session, expected)
            rows = (
                await session.execute(
                    select(entries_table.c.id, entries_table.c.embedding).where(
                        entries_table.c.id.in_(entry_ids)
                    )
                )
            ).all()
            return {row[0]: list(row[1]) for row in rows}

    async def search_similar_entries(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_connected()
        dimension = self._validate_vector(query_vector)
        if self._session_maker is None:
            raise RuntimeError("pgvector client not connected")
        entries_table, _, _ = self._tables()
        if Vector is None:  # pragma: no cover - guarded by connect()
            raise RuntimeError("pgvector package is not installed")
        indexed_embedding = cast(entries_table.c.embedding, Vector(dimension))  # type: ignore[misc]
        distance = indexed_embedding.cosine_distance(query_vector)  # type: ignore[union-attr]
        stmt = select(
            entries_table.c.id,
            entries_table.c.feed_id,
            entries_table.c.published_at,
            entries_table.c.author,
            distance.label("distance"),
        )
        if filters:
            clauses = []
            if "feed_id" in filters:
                clauses.append(entries_table.c.feed_id == filters["feed_id"])
            if "min_published_at" in filters:
                min_ts = int(filters["min_published_at"].timestamp())
                clauses.append(entries_table.c.published_at >= min_ts)
            if clauses:
                stmt = stmt.where(and_(*clauses))
        stmt = stmt.order_by(distance).limit(top_k)
        expected, _ = self._require_active_model()
        async with self._session_maker() as session, session.begin():
            await self._take_model_lock(session, shared=True)
            await self._assert_active_signature(session, expected)
            rows = (await session.execute(stmt)).all()
            return [
                {
                    "id": row.id,
                    "score": 1.0 - float(row.distance),
                    "feed_id": row.feed_id,
                    "published_at": row.published_at,
                    "author": row.author,
                }
                for row in rows
            ]

    async def upsert_user_preference(
        self,
        user_id: str,
        vector_type: str,
        embedding: list[float],
        sample_count: float,
        updated_at: int,
    ) -> None:
        self._ensure_connected()
        self._validate_vector(embedding)
        _, prefs_table, _ = self._tables()
        pref_id = f"{user_id}_{vector_type}"
        stmt = (
            insert(prefs_table)
            .values(
                id=pref_id,
                user_id=user_id,
                vector_type=vector_type,
                embedding=embedding,
                sample_count=sample_count,
                updated_at=updated_at,
            )
            .on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "user_id": user_id,
                    "vector_type": vector_type,
                    "embedding": embedding,
                    "sample_count": sample_count,
                    "updated_at": updated_at,
                },
            )
        )
        await self._execute_model_write(stmt)

    async def get_user_preferences(self, user_id: str) -> dict[str, dict[str, Any]]:
        self._ensure_connected()
        if self._session_maker is None:
            raise RuntimeError("pgvector client not connected")
        _, prefs_table, _ = self._tables()
        expected, _ = self._require_active_model()
        async with self._session_maker() as session, session.begin():
            await self._take_model_lock(session, shared=True)
            await self._assert_active_signature(session, expected)
            rows = (
                await session.execute(
                    select(
                        prefs_table.c.vector_type,
                        prefs_table.c.embedding,
                        prefs_table.c.sample_count,
                        prefs_table.c.updated_at,
                    ).where(prefs_table.c.user_id == user_id)
                )
            ).all()
            return {
                row.vector_type: {
                    "embedding": list(row.embedding),
                    "sample_count": row.sample_count,
                    "updated_at": row.updated_at,
                }
                for row in rows
            }

    async def delete_entry_embedding(self, entry_id: str) -> None:
        self._ensure_connected()
        entries_table, _, _ = self._tables()
        await self._execute_model_write(delete(entries_table).where(entries_table.c.id == entry_id))

    async def delete_user_preferences(self, user_id: str) -> None:
        self._ensure_connected()
        _, prefs_table, _ = self._tables()
        await self._execute_model_write(delete(prefs_table).where(prefs_table.c.user_id == user_id))
