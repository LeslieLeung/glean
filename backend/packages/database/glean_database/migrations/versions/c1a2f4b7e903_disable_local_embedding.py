"""Disable configurations that use the removed local embedding provider.

Revision ID: c1a2f4b7e903
Revises: d84b1a7c902e
"""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "c1a2f4b7e903"
down_revision: str | None = "d84b1a7c902e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Retain the active model identity so re-enabling with a remote provider
    # checks the existing vector space before using it.
    op.execute(
        sa.text(
            """
            UPDATE system_configs
            SET value = value || jsonb_build_object(
                'enabled', false,
                'status', 'disabled',
                'version', CAST(:version AS text),
                'target_vector_backend', NULL,
                'target_vector_store_fingerprint', NULL,
                'target_model_fingerprint', NULL,
                'target_force_rebuild', false,
                'last_error', NULL,
                'last_error_at', NULL,
                'error_count', 0,
                'rebuild_id', NULL,
                'rebuild_started_at', NULL,
                'rebuild_phase', NULL
            ),
            updated_at = now()
            WHERE key = 'embedding'
              AND lower(value->>'provider') IN ('sentence-transformers', 'sentence_transformers')
            """
        ).bindparams(version=str(uuid4()))
    )


def downgrade() -> None:
    # Leave vectorization disabled until an administrator enables it again.
    pass
