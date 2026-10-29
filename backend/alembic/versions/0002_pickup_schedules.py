"""pickup schedules and long-term medicine flag

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.database

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("medicines") as batch:
        batch.add_column(sa.Column("is_long_term", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.create_index("ix_medicines_is_long_term", ["is_long_term"])
    op.create_table(
        "pickup_schedules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("medicine_id", sa.String(length=36), nullable=False),
        sa.Column("county_id", sa.Integer(), nullable=False),
        sa.Column("preferred_facility_id", sa.String(length=36), nullable=True),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("next_pickup_on", sa.Date(), nullable=False),
        sa.Column("remind_days_before", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("consent_at", app.database.UTCDateTime(), nullable=False),
        sa.Column("consent_source", sa.String(length=20), nullable=False),
        sa.Column("unsubscribed_at", app.database.UTCDateTime(), nullable=True),
        sa.Column("last_reminded_at", app.database.UTCDateTime(), nullable=True),
        sa.Column("last_reminded_for", sa.Date(), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", app.database.UTCDateTime(), nullable=False),
        sa.CheckConstraint("interval_days >= 7 AND interval_days <= 180", name="ck_pickup_interval"),
        sa.CheckConstraint("remind_days_before >= 1 AND remind_days_before <= 14", name="ck_pickup_remind"),
        sa.ForeignKeyConstraint(["county_id"], ["counties.id"]),
        sa.ForeignKeyConstraint(["medicine_id"], ["medicines.id"]),
        sa.ForeignKeyConstraint(["preferred_facility_id"], ["facilities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone", "medicine_id", name="uq_pickup_phone_medicine"),
    )
    op.create_index("ix_pickup_schedules_phone", "pickup_schedules", ["phone"])
    op.create_index("ix_pickup_due", "pickup_schedules", ["is_active", "next_pickup_on"])
    op.create_index("ix_pickup_schedules_is_demo", "pickup_schedules", ["is_demo"])
    op.create_index("ix_pickup_schedules_next_pickup_on", "pickup_schedules", ["next_pickup_on"])


def downgrade() -> None:
    op.drop_table("pickup_schedules")
    with op.batch_alter_table("medicines") as batch:
        batch.drop_index("ix_medicines_is_long_term")
        batch.drop_column("is_long_term")
