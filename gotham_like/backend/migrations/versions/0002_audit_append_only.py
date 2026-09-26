"""append-only audit log, partial indexes for active graph, retention helpers

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Audit log is append-only from the application's perspective: UPDATE, DELETE
    # and TRUNCATE are rejected by the database itself. Retention purges must be
    # run by a DBA role that explicitly disables the trigger (documented in SECURITY.md).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_log_block_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only (% blocked)', TG_OP USING ERRCODE = 'insufficient_privilege';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_update BEFORE UPDATE OR DELETE ON audit_log FOR EACH ROW EXECUTE FUNCTION audit_log_block_mutation()"
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log FOR EACH STATEMENT EXECUTE FUNCTION audit_log_block_mutation()"
    )
    # Hot-path partial indexes: traversal only ever touches live (non-deleted) edges.
    op.execute("CREATE INDEX ix_rel_live_source ON relationships (source_id, type, timestamp) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX ix_rel_live_target ON relationships (target_id, type, timestamp) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX ix_entities_live_type ON entities (type, id) WHERE merged_into IS NULL AND deleted_at IS NULL")
    op.execute("CREATE INDEX ix_entities_label_prefix ON entities (lower(label) text_pattern_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_entities_label_prefix")
    op.execute("DROP INDEX IF EXISTS ix_entities_live_type")
    op.execute("DROP INDEX IF EXISTS ix_rel_live_target")
    op.execute("DROP INDEX IF EXISTS ix_rel_live_source")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_block_mutation()")
