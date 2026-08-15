"""cancelled SOS status

Adds `cancelled` to the sos.status CHECK constraint (ADR-025). A citizen
withdrawing a request is a different outcome from a rescue completing, and
recording both as `resolved` corrupted the funnel's resolved count and the
time-to-acceptance distribution.

Written by hand for the same reason as 0002: autogenerate does not diff CHECK
constraints backed by a non-native enum. Dropping and recreating the constraint
is metadata-only -- the trade ADR-017 and the models module called at the
outset, and the second time it has paid for itself.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "sos_status"
TABLE = "sos"

STATUSES_BEFORE = ("pending", "matched", "resolved", "no_responder_found")
STATUSES_AFTER = ("pending", "matched", "resolved", "cancelled", "no_responder_found")


def _in_clause(values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{value}'" for value in values)
    return f"status IN ({joined})"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(CONSTRAINT, TABLE, _in_clause(STATUSES_AFTER))


def downgrade() -> None:
    # A cancelled incident has no honest representation in the old vocabulary.
    # `resolved` is the value this change exists to stop it being conflated
    # with, and `no_responder_found` asserts a dispatch failure that did not
    # happen. Returning it to `pending` is the least false of the three: the
    # incident is once again one with no terminal outcome recorded, which is
    # what the old schema is able to say about it.
    op.execute(f"UPDATE {TABLE} SET status = 'pending' WHERE status = 'cancelled'")

    op.drop_constraint(CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(CONSTRAINT, TABLE, _in_clause(STATUSES_BEFORE))
