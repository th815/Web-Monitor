"""Add alert_suppression_seconds to monitoring_config

Revision ID: c007c9af2919
Revises: 
Create Date: 2025-10-23 06:23:39.188705

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c007c9af2919'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('monitoring_config')]
    
    if 'alert_suppression_seconds' not in columns:
        with op.batch_alter_table('monitoring_config', schema=None) as batch_op:
            batch_op.add_column(sa.Column('alert_suppression_seconds', sa.Integer(), nullable=False, server_default='600'))


def downgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('monitoring_config')]
    
    if 'alert_suppression_seconds' in columns:
        with op.batch_alter_table('monitoring_config', schema=None) as batch_op:
            batch_op.drop_column('alert_suppression_seconds')
