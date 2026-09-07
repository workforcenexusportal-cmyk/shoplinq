"""newsletter subscribers

Revision ID: a1b2c3d4e5f6
Revises: 4e099cec0ff4
Create Date: 2026-09-07 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '4e099cec0ff4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'newsletter_subscribers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_date', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('newsletter_subscribers', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_newsletter_subscribers_email'), ['email'], unique=True)


def downgrade():
    with op.batch_alter_table('newsletter_subscribers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_newsletter_subscribers_email'))
    op.drop_table('newsletter_subscribers')
