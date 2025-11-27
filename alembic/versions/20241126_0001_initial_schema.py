"""Initial schema with all tables

Revision ID: 0001
Revises:
Create Date: 2024-11-26 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('username', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('is_superuser', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('email')
    )
    op.create_index('ix_users_username', 'users', ['username'])
    op.create_index('ix_users_email', 'users', ['email'])

    # Create processing_jobs table
    op.create_table(
        'processing_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), default='pending'),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('config', postgresql.JSONB()),
        sa.Column('result', postgresql.JSONB()),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('ix_processing_jobs_status', 'processing_jobs', ['status'])
    op.create_index('ix_processing_jobs_job_type', 'processing_jobs', ['job_type'])
    op.create_index('ix_processing_jobs_created_at', 'processing_jobs', ['created_at'])

    # Create satellite_observations table (TimescaleDB hypertable candidate)
    op.create_table(
        'satellite_observations',
        sa.Column('time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('satellite_id', sa.String(50), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('altitude', sa.Float(), nullable=False),
        sa.Column('gravity_value', sa.Float()),
        sa.Column('gravity_uncertainty', sa.Float()),
        sa.Column('meta_info', postgresql.JSONB()),
        sa.Column('job_id', postgresql.UUID(as_uuid=True)),
        sa.PrimaryKeyConstraint('time', 'satellite_id'),
        sa.ForeignKeyConstraint(['job_id'], ['processing_jobs.id'], ondelete='CASCADE')
    )
    op.create_index('ix_satellite_observations_satellite_id', 'satellite_observations', ['satellite_id'])
    op.create_index('ix_satellite_observations_time', 'satellite_observations', ['time'])

    # Create gravity_products table
    op.create_table(
        'gravity_products',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_type', sa.String(50), nullable=False),
        sa.Column('version', sa.String(20), nullable=False),
        sa.Column('time_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('time_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('degree_max', sa.Integer()),
        sa.Column('spatial_resolution', sa.Float()),
        sa.Column('s3_path', sa.Text(), nullable=False),
        sa.Column('meta_info', postgresql.JSONB()),
        sa.Column('job_id', postgresql.UUID(as_uuid=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['job_id'], ['processing_jobs.id'], ondelete='CASCADE')
    )
    op.create_index('ix_gravity_products_product_type', 'gravity_products', ['product_type'])
    op.create_index('ix_gravity_products_time_start', 'gravity_products', ['time_start'])

    # Create baseline_vectors table
    op.create_table(
        'baseline_vectors',
        sa.Column('time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('satellite_1', sa.String(50), nullable=False),
        sa.Column('satellite_2', sa.String(50), nullable=False),
        sa.Column('range_rate', sa.Float()),
        sa.Column('range_acceleration', sa.Float()),
        sa.Column('baseline_length', sa.Float()),
        sa.Column('meta_info', postgresql.JSONB()),
        sa.Column('job_id', postgresql.UUID(as_uuid=True)),
        sa.PrimaryKeyConstraint('time', 'satellite_1', 'satellite_2'),
        sa.ForeignKeyConstraint(['job_id'], ['processing_jobs.id'], ondelete='CASCADE')
    )
    op.create_index('ix_baseline_vectors_time', 'baseline_vectors', ['time'])

    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('resource_type', sa.String(50)),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True)),
        sa.Column('details', postgresql.JSONB()),
        sa.Column('ip_address', postgresql.INET()),
        sa.Column('user_agent', sa.Text()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL')
    )
    op.create_index('ix_audit_logs_timestamp', 'audit_logs', ['timestamp'])
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('baseline_vectors')
    op.drop_table('gravity_products')
    op.drop_table('satellite_observations')
    op.drop_table('processing_jobs')
    op.drop_table('users')
