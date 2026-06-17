"""session datasource many to many

Revision ID: c7d4e3f2a1b8
Revises: e2c8b5a1d9f3
Create Date: 2026-06-17 01:00:00.000000

Sessions and DataSources become many-to-many via a join table.
Migrates existing sessions.data_source_id into the join table then drops the column.
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

revision = 'c7d4e3f2a1b8'
down_revision = 'e2c8b5a1d9f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'session_data_sources',
        sa.Column('session_id', sa.Text(), nullable=False),
        sa.Column('data_source_id', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('session_id', 'data_source_id'),
    )

    # Migrate existing session→data_source FK into the join table
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, data_source_id FROM sessions WHERE data_source_id IS NOT NULL")
    ).fetchall()
    for session_id, ds_id in rows:
        conn.execute(
            sa.text(
                "INSERT OR IGNORE INTO session_data_sources (session_id, data_source_id) "
                "VALUES (:sid, :dsid)"
            ),
            {"sid": session_id, "dsid": ds_id},
        )

    # Drop data_source_id from sessions
    with op.batch_alter_table('sessions', recreate='always') as batch_op:
        batch_op.drop_column('data_source_id')


def downgrade() -> None:
    with op.batch_alter_table('sessions', recreate='always') as batch_op:
        batch_op.add_column(sa.Column('data_source_id', sa.Text(), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT session_id, data_source_id FROM session_data_sources")
    ).fetchall()
    for session_id, ds_id in rows:
        conn.execute(
            sa.text("UPDATE sessions SET data_source_id = :dsid WHERE id = :sid"),
            {"sid": session_id, "dsid": ds_id},
        )

    op.drop_table('session_data_sources')
