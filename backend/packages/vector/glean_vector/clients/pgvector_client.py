"""pgvector client for vector operations."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import BIGINT, Column, Float, Integer, MetaData, String, Table, and_, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from glean_core import get_logger
from glean_vector.config import pgvector_config

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover
    Vector = None  # type: ignore[assignment,misc]

logger = get_logger(__name__)


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

    @staticmethod
    def _build_model_signature(provider: str, model: str, dimension: int) -> str:
        return f"{provider}:{model}:{dimension}"

    @property
    def _database_url(self) -> str:
        if self.config.database_url:
            return self.config.database_url
        return os.getenv("DATABASE_URL", "")

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
        self._entries_table = Table(
            self.config.entries_table,
            self._metadata,
            Column("id", String(36), primary_key=True),
            Column("embedding", Vector(), nullable=False),  # type: ignore[misc,operator]
            Column("feed_id", String(36), nullable=False),
            Column("published_at", BIGINT, nullable=False),
            Column("language", String(10), nullable=False, server_default=""),
            Column("word_count", Integer, nullable=False, server_default="0"),
            Column("author", String(200), nullable=False, server_default=""),
        )
        self._prefs_table = Table(
            self.config.prefs_table,
            self._metadata,
            Column("id", String(50), primary_key=True),
            Column("user_id", String(36), nullable=False),
            Column("vector_type", String(20), nullable=False),
            Column("embedding", Vector(), nullable=False),  # type: ignore[misc,operator]
            Column("sample_count", Float, nullable=False),
            Column("updated_at", BIGINT, nullable=False),
        )
        self._meta_table = Table(
            self.config.metadata_table,
            self._metadata,
            Column("name", String(50), primary_key=True),
            Column("model_signature", String(255), nullable=False),
            Column("updated_at", BIGINT, nullable=False),
        )

    def disconnect(self) -> None:
        """Close connection resources."""
        if self._engine is not None:
            self._engine.sync_engine.dispose()
        self._connected = False
        self._engine = None
        self._session_maker = None

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

    async def _execute(self, statement: Any) -> Any:
        if self._session_maker is None:
            raise RuntimeError("pgvector client not connected")
        async with self._session_maker() as session:
            result = await session.execute(statement)
            await session.commit()
            return result

    async def _load_model_signature(self) -> str | None:
        if self._session_maker is None:
            raise RuntimeError("pgvector client not connected")
        _, _, meta_table = self._tables()
        async with self._session_maker() as session:
            rows = (
                await session.execute(
                    select(meta_table.c.name, meta_table.c.model_signature).where(
                        meta_table.c.name.in_(["entries", "preferences"])
                    )
                )
            ).all()
        signatures = {str(row.name): str(row.model_signature) for row in rows}
        entries_signature = signatures.get("entries")
        prefs_signature = signatures.get("preferences")
        if entries_signature and entries_signature == prefs_signature:
            return entries_signature
        return None

    async def _write_model_metadata(self, signature: str) -> None:
        _, _, meta_table = self._tables()
        now_ts = int(datetime.now(UTC).timestamp())
        await self._execute(
            insert(meta_table)
            .values(name="entries", model_signature=signature, updated_at=now_ts)
            .on_conflict_do_update(
                index_elements=["name"],
                set_={"model_signature": signature, "updated_at": now_ts},
            )
        )
        await self._execute(
            insert(meta_table)
            .values(name="preferences", model_signature=signature, updated_at=now_ts)
            .on_conflict_do_update(
                index_elements=["name"],
                set_={"model_signature": signature, "updated_at": now_ts},
            )
        )
        self._last_model_signature = signature

    def _tables(self) -> tuple[Table, Table, Table]:
        if self._entries_table is None or self._prefs_table is None or self._meta_table is None:
            raise RuntimeError("pgvector tables not initialized")
        return self._entries_table, self._prefs_table, self._meta_table

    async def ensure_collections(
        self, dimension: int, provider: str | None = None, model: str | None = None
    ) -> None:
        """Ensure pgvector extension/tables/indexes exist.

        Results are cached so that repeated calls within the same client
        lifetime skip the DDL checks.  The cache is invalidated by
        ``recreate_collections``.
        """
        self._ensure_connected()
        if self._engine is None:
            raise RuntimeError("pgvector engine unavailable")
        entries_table, prefs_table, _meta_table = self._tables()

        if not self._schema_ensured:
            async with self._engine.begin() as conn:
                await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
                await conn.run_sync(self._metadata.create_all)
                await conn.exec_driver_sql(
                    f"CREATE INDEX IF NOT EXISTS {_quote_ident('idx_' + entries_table.name + '_feed_id')} "
                    f"ON {_quote_ident(entries_table.name)} (feed_id)"
                )
                await conn.exec_driver_sql(
                    f"CREATE INDEX IF NOT EXISTS {_quote_ident('idx_' + entries_table.name + '_published_at')} "
                    f"ON {_quote_ident(entries_table.name)} (published_at)"
                )
                await conn.exec_driver_sql(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {_quote_ident('idx_' + prefs_table.name + '_user_type')} "
                    f"ON {_quote_ident(prefs_table.name)} (user_id, vector_type)"
                )
            self._schema_ensured = True

        if provider and model and self._last_model_signature is None:
            self._last_model_signature = await self._load_model_signature()

    async def recreate_collections(
        self, dimension: int, provider: str | None = None, model: str | None = None
    ) -> None:
        """Drop and recreate pgvector tables."""
        self._ensure_connected()
        if self._engine is None:
            raise RuntimeError("pgvector engine unavailable")
        entries_table, prefs_table, meta_table = self._tables()
        # Invalidate caches before destructive operation
        self._schema_ensured = False
        self._last_model_signature = None
        async with self._engine.begin() as conn:
            await conn.exec_driver_sql(f"DROP TABLE IF EXISTS {_quote_ident(prefs_table.name)}")
            await conn.exec_driver_sql(f"DROP TABLE IF EXISTS {_quote_ident(entries_table.name)}")
            await conn.exec_driver_sql(f"DROP TABLE IF EXISTS {_quote_ident(meta_table.name)}")
        await self.ensure_collections(dimension)
        if provider and model:
            signature = self._build_model_signature(provider, model, dimension)
            await self._write_model_metadata(signature)

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
        await self._execute(stmt)

    async def get_entry_embedding(self, entry_id: str) -> list[float] | None:
        self._ensure_connected()
        if self._session_maker is None:
            raise RuntimeError("pgvector client not connected")
        entries_table, _, _ = self._tables()
        async with self._session_maker() as session:
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
        async with self._session_maker() as session:
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
        if self._session_maker is None:
            raise RuntimeError("pgvector client not connected")
        entries_table, _, _ = self._tables()
        distance = entries_table.c.embedding.cosine_distance(query_vector)  # type: ignore[union-attr]
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
        async with self._session_maker() as session:
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
        await self._execute(stmt)

    async def get_user_preferences(self, user_id: str) -> dict[str, dict[str, Any]]:
        self._ensure_connected()
        if self._session_maker is None:
            raise RuntimeError("pgvector client not connected")
        _, prefs_table, _ = self._tables()
        async with self._session_maker() as session:
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
        await self._execute(delete(entries_table).where(entries_table.c.id == entry_id))

    async def delete_user_preferences(self, user_id: str) -> None:
        self._ensure_connected()
        _, prefs_table, _ = self._tables()
        await self._execute(delete(prefs_table).where(prefs_table.c.user_id == user_id))
