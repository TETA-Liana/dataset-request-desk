"""initial schema

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("organisation", sa.String(255)),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('client', 'operator', 'admin')", name="ck_users_role"),
    )

    op.create_table(
        "episodes",
        sa.Column("episode_id", sa.String(50), primary_key=True),
        sa.Column("robot_id", sa.String(50), nullable=False),
        sa.Column("task_name", sa.String(255), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer, nullable=False),
        sa.Column("operator_name", sa.String(255)),
        sa.Column("quality", sa.String(10), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("quality IN ('good', 'usable', 'bad')", name="ck_episodes_quality"),
        sa.CheckConstraint("duration_seconds > 0", name="ck_episodes_duration"),
    )
    # Every analytics query filters on a date range, so this index matters most.
    op.create_index("ix_episodes_recorded_at", "episodes", ["recorded_at"])

    op.create_table(
        "dataset_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("client_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("task_name", sa.String(255), nullable=False),
        sa.Column("episodes_requested", sa.Integer, nullable=False),
        sa.Column("deadline", sa.Date, nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("status", sa.String(20), nullable=False, server_default="submitted"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('submitted', 'in_progress', 'delivered', 'accepted', 'rejected')",
            name="ck_requests_status",
        ),
        sa.CheckConstraint("episodes_requested > 0", name="ck_requests_count"),
    )
    op.create_index("ix_dataset_requests_client_id", "dataset_requests", ["client_id"])

    op.create_table(
        "status_changes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("request_id", sa.Integer, sa.ForeignKey("dataset_requests.id"), nullable=False),
        sa.Column("from_status", sa.String(20)),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("changed_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("comment", sa.Text),
    )
    op.create_index("ix_status_changes_request_id", "status_changes", ["request_id"])

    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("episode_id", sa.String(50), sa.ForeignKey("episodes.episode_id"), nullable=False, unique=True),
        sa.Column("request_id", sa.Integer, sa.ForeignKey("dataset_requests.id"), nullable=False),
        sa.Column("assigned_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_assignments_request_id", "assignments", ["request_id"])


def downgrade():
    op.drop_table("assignments")
    op.drop_table("status_changes")
    op.drop_table("dataset_requests")
    op.drop_table("episodes")
    op.drop_table("users")
