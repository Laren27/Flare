"""Structured dispatch decision logging -- ADR-014.

Every candidate evaluated emits exactly one row, selected or rejected, with the
reason. There is no code path in this project that skips a candidate without
writing here: that is invariant 4, and it is what makes "why didn't responder X
get alerted?" a query rather than a shrug. Every metric in ADR-015 is a read
over this table.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DispatchEvent, DispatchOutcome, RejectionReason, SkillClass

# Eligibility before geography (ADR-021). The first reason that applies wins, so
# `out_of_radius` counts only volunteers who genuinely could have responded but
# were too far -- otherwise the coverage-gap metric of ADR-015 fills with people
# who were never eligible, and recruitment gets pointed at the wrong districts.
REJECTION_PRECEDENCE: tuple[RejectionReason, ...] = (
    RejectionReason.UNVERIFIED,
    RejectionReason.UNAVAILABLE,
    RejectionReason.NO_LOCATION,
    RejectionReason.OUT_OF_RADIUS,
)


@dataclass(frozen=True, slots=True)
class Evaluation:
    """The outcome of assessing one volunteer against one incident, at one radius."""

    volunteer_id: int
    skill: SkillClass
    skill_match: bool
    # None exactly when the volunteer had no location to measure from.
    distance_m: float | None
    outcome: DispatchOutcome
    rejection_reason: RejectionReason | None

    @property
    def is_selected(self) -> bool:
        return self.outcome is DispatchOutcome.ALERTED


def first_applicable_reason(reasons: set[RejectionReason]) -> RejectionReason | None:
    """Resolve concurrent rejection reasons through the ADR-021 precedence."""
    for reason in REJECTION_PRECEDENCE:
        if reason in reasons:
            return reason
    return None


async def record_evaluations(
    session: AsyncSession,
    *,
    sos_id: int,
    wave_number: int,
    radius_m: int,
    evaluations: list[Evaluation],
) -> None:
    """Append one row per evaluation. Does not commit -- the caller owns the
    transaction, so the events and the incident state they describe land
    together or not at all."""
    session.add_all(
        DispatchEvent(
            sos_id=sos_id,
            volunteer_id=evaluation.volunteer_id,
            wave_number=wave_number,
            radius_m_at_eval=radius_m,
            distance_m=evaluation.distance_m,
            skill_match=evaluation.skill_match,
            outcome=evaluation.outcome,
            rejection_reason=evaluation.rejection_reason,
        )
        for evaluation in evaluations
    )
