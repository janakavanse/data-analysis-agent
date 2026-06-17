"""tool registry and sessions

Revision ID: e2c8b5a1d9f3
Revises: f3c81a2d9e04
Create Date: 2026-06-17 00:00:00.000000

Redesign: replace datasets table with data_sources + tools + tool_capabilities.
Add sessions table as intermediate between data_source and query_records.
Migrate query_records to use session_id instead of dataset_id.
"""
from alembic import op
import sqlalchemy as sa

revision = 'e2c8b5a1d9f3'
down_revision = 'f3c81a2d9e04'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # New tables
    op.create_table(
        'data_sources',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('file_path', sa.Text(), nullable=True),
        sa.Column('row_count', sa.Integer(), nullable=True),
        sa.Column('column_names_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'tools',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('data_source_id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('config_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'tool_capabilities',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('tool_id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('parameter_schema_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'sessions',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('data_source_id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # Migrate query_records: add session_id + query_history_json, then drop dataset_id.
    # For any existing rows, create a placeholder data_source+session per dataset_id.
    conn = op.get_bind()
    existing_dataset_ids = [
        r[0] for r in conn.execute(sa.text("SELECT DISTINCT dataset_id FROM query_records")).fetchall()
    ]

    from datetime import datetime, timezone
    from uuid import uuid4
    now = datetime.now(timezone.utc).isoformat()

    dataset_to_session: dict[str, str] = {}
    for dataset_id in existing_dataset_ids:
        # Try to grab original dataset metadata
        ds_row = conn.execute(
            sa.text("SELECT filename, file_path, row_count, column_names_json FROM datasets WHERE id = :id"),
            {"id": dataset_id},
        ).fetchone()

        ds_id = str(uuid4())
        name = ds_row[0] if ds_row else f"imported-{dataset_id[:8]}"
        file_path = ds_row[1] if ds_row else None
        row_count = ds_row[2] if ds_row else None
        col_json = ds_row[3] if ds_row else None

        conn.execute(
            sa.text(
                "INSERT INTO data_sources (id, name, type, file_path, row_count, column_names_json, created_at) "
                "VALUES (:id, :name, 'csv', :fp, :rc, :cj, :now)"
            ),
            {"id": ds_id, "name": name, "fp": file_path, "rc": row_count, "cj": col_json, "now": now},
        )

        tool_id = str(uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO tools (id, data_source_id, name, type, description, config_json, created_at) "
                "VALUES (:id, :ds_id, 'csv_query', 'csv_query', "
                "'Execute SQL SELECT queries against the dataset', '{\"table_name\": \"data\"}', :now)"
            ),
            {"id": tool_id, "ds_id": ds_id, "now": now},
        )
        cap_id = str(uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO tool_capabilities "
                "(id, tool_id, name, description, parameter_schema_json, created_at) "
                "VALUES (:id, :tool_id, 'run_query', "
                "'Execute a SQL SELECT statement. Table is always named data.', "
                "'{\"query\": {\"type\": \"string\", \"description\": \"A valid SQL SELECT statement\"}}', "
                ":now)"
            ),
            {"id": cap_id, "tool_id": tool_id, "now": now},
        )

        session_id = str(uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO sessions (id, data_source_id, name, created_at, updated_at) "
                "VALUES (:id, :ds_id, 'Migrated session', :now, :now)"
            ),
            {"id": session_id, "ds_id": ds_id, "now": now},
        )
        dataset_to_session[dataset_id] = session_id

    # Recreate query_records with session_id replacing dataset_id, plus new columns
    with op.batch_alter_table('query_records', recreate='always') as batch_op:
        batch_op.add_column(sa.Column('session_id', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('query_history_json', sa.Text(), nullable=True))

    # Populate session_id from our mapping
    for dataset_id, session_id in dataset_to_session.items():
        conn.execute(
            sa.text("UPDATE query_records SET session_id = :sid WHERE dataset_id = :did"),
            {"sid": session_id, "did": dataset_id},
        )

    # Drop dataset_id
    with op.batch_alter_table('query_records', recreate='always') as batch_op:
        batch_op.drop_column('dataset_id')

    # Drop old datasets table
    op.drop_table('datasets')


def downgrade() -> None:
    op.create_table(
        'datasets',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('filename', sa.Text(), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=True),
        sa.Column('column_names_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('query_records', recreate='always') as batch_op:
        batch_op.add_column(sa.Column('dataset_id', sa.Text(), nullable=True))
        batch_op.drop_column('session_id')
        batch_op.drop_column('query_history_json')
    op.drop_table('sessions')
    op.drop_table('tool_capabilities')
    op.drop_table('tools')
    op.drop_table('data_sources')
