"""add_assistant_app

Revision ID: 3ef9b2b6bee6
Revises: 89c7899ca936
Create Date: 2024-01-05 15:26:25.117551

"""
from ast import Index
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '4e99a8df00ff'
down_revision = '89c7899ca936'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('app_questions',
    sa.Column('id', postgresql.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
    sa.Column('app_id', postgresql.UUID(), nullable=False),
    sa.Column('questions', sa.String(length=1024), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP(0)'), nullable=False),
    sa.PrimaryKeyConstraint('id', name='app_qur_pkey'),
    sa.Index('app_qur_app_id_idx','app_id')
    )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('app_questions')
    
    # ### end Alembic commands ###
