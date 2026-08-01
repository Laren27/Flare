"""no_location rejection reason

Adds `no_location` to the dispatch_events.rejection_reason CHECK constraint and
makes distance_m nullable -- a verified, available volunteer we have never had a
position for cannot have a distance computed (ADR-021).

Autogenerate produced the nullability change only: it does not diff CHECK
constraints backed by a non-native enum, so the constraint swap below is written
by hand. Dropping and recreating a CHECK is a metadata-only operation; the same
change against a native Postgres ENUM would have been materially harder, which
is the trade ADR-017 and the models module called at the outset.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "rejection_reason"
TABLE = "dispatch_events"

REASONS_BEFORE = ("out_of_radius", "unavailable", "unverified", "already_alerted", "no_socket")
REASONS_AFTER = (*REASONS_BEFORE, "no_location")


def _in_clause(values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{value}'" for value in values)
    return f"rejection_reason IN ({joined})"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(CONSTRAINT, TABLE, _in_clause(REASONS_AFTER))

    op.alter_column(
        TABLE,
        "distance_m",
        existing_type=sa.DOUBLE_PRECISION(precision=53),
        nullable=True,
    )


def downgrade() -> None:
    # Rows recorded under the new reason have no meaning in the old vocabulary,
    # and their null distance cannot satisfy a NOT NULL column. Discard them
    # rather than fabricating a distance for a volunteer who had no position.
    op.execute(f"DELETE FROM {TABLE} WHERE rejection_reason = 'no_location'")

    op.alter_column(
        TABLE,
        "distance_m",
        existing_type=sa.DOUBLE_PRECISION(precision=53),
        nullable=False,
    )

    op.drop_constraint(CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(CONSTRAINT, TABLE, _in_clause(REASONS_BEFORE))
