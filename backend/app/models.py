"""SQLAlchemy models for every table in Chapter 12.

All seven tables are defined now, in full, including the timestamp columns
listed at the end of Chapter 13 -- `first_dispatch_at`, `matched_at`,
`resolved_at` and friends are written from week 4 onward and read by the
analytics layer in week 6, but they exist from the first migration so that
later weeks change behaviour rather than schema.

Two schema-wide conventions:

* Enums are stored as VARCHAR with a CHECK constraint, not as native Postgres
  ENUM types. Native enums are awkward to ALTER through a migration, and the
  accept-lock of ADR-011 compares `status` against a string literal in raw SQL
  either way. Simpler thing that satisfies the requirement (Rule 002).
* Every timestamp is TIMESTAMP WITH TIME ZONE. Time-to-acceptance (ADR-015) is
  a difference between two of them; a naive column makes that arithmetic wrong
  the moment the app and the database disagree about a timezone.

No ORM relationships are declared. Under asyncio, lazy-loading a relationship
raises on attribute access outside a session, so relationships have to be
loaded deliberately -- the services that need joins will write them explicitly.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserRole(enum.StrEnum):
    CITIZEN = "citizen"
    VOLUNTEER = "volunteer"
    ADMIN = "admin"


class SkillClass(enum.StrEnum):
    """Single-valued per volunteer (Ch. 12) -- see ADR-007 for how it ranks."""

    CPR = "cpr"
    BLOOD_DONOR = "blood_donor"
    FIRST_AID = "first_aid"
    GENERAL = "general"


class SOSStatus(enum.StrEnum):
    PENDING = "pending"
    MATCHED = "matched"
    RESOLVED = "resolved"
    # Withdrawn by the citizen, from `pending` or `matched` (ADR-025). Distinct
    # from `resolved` on purpose: folding "never mind" into "help arrived" would
    # inflate the funnel's resolved count and pollute the time-to-acceptance
    # distribution with incidents nobody was still travelling to.
    CANCELLED = "cancelled"
    NO_RESPONDER_FOUND = "no_responder_found"


class AIPriority(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AIStatus(enum.StrEnum):
    """`ok` only when the bounded call of ADR-013 returned inside its 3s budget."""

    OK = "ok"
    TIMEOUT = "timeout"
    ERROR = "error"
    SKIPPED = "skipped"


class NotificationStatus(enum.StrEnum):
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    DISMISSED = "dismissed"


class DispatchOutcome(enum.StrEnum):
    ALERTED = "alerted"
    REJECTED = "rejected"


class RejectionReason(enum.StrEnum):
    """Why a candidate was not alerted. Null when `outcome` is `alerted`.

    When several apply, ADR-021 fixes the precedence: eligibility before
    geography, so `out_of_radius` counts only volunteers who genuinely could
    have responded but were too far away.
    """

    OUT_OF_RADIUS = "out_of_radius"
    UNAVAILABLE = "unavailable"
    UNVERIFIED = "unverified"
    ALREADY_ALERTED = "already_alerted"
    NO_SOCKET = "no_socket"
    # A verified, available volunteer we have never had a position for. Distinct
    # from `unavailable` on purpose -- "never located" and "went offline" are
    # different failures with different remedies (ADR-021).
    NO_LOCATION = "no_location"


class EscalationTrigger(enum.StrEnum):
    """Which ADR-012 condition expanded the radius, if any."""

    NONE = "none"
    EMPTY_SET = "empty_set"
    TIMEOUT = "timeout"


def enum_column(enum_cls: type[enum.StrEnum], constraint_name: str) -> Enum:
    """VARCHAR + CHECK for a StrEnum, storing values rather than member names."""
    return Enum(
        enum_cls,
        name=constraint_name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Phone is the login identifier -- Ch. 12 gives users no email column.
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    role: Mapped[UserRole] = mapped_column(enum_column(UserRole, "user_role"), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Volunteer(Base):
    """One row per volunteer user, keyed on the user itself (Ch. 12: no own id)."""

    __tablename__ = "volunteers"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Verification is manual admin approval (ADR-006), so this starts false and
    # only an admin can flip it.
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    certificate_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    skills: Mapped[SkillClass] = mapped_column(
        enum_column(SkillClass, "skill_class"), nullable=False, default=SkillClass.GENERAL
    )
    availability: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Location(Base):
    """Latest known location only -- no history table, by design (Rule 004)."""

    __tablename__ = "locations"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SOS(Base):
    """An emergency event. Table name is `sos` -- ADR-011's conditional UPDATE
    is written against it literally."""

    __tablename__ = "sos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    victim_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[SOSStatus] = mapped_column(
        enum_column(SOSStatus, "sos_status"), nullable=False, default=SOSStatus.PENDING
    )
    # Base radius is 1km; the ladder of ADR-012 walks it to 2km then 3km.
    current_radius_m: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    wave_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ADR-013: written by the concurrent AI call, never waited on before wave 1.
    ai_category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ai_priority: Mapped[AIPriority | None] = mapped_column(
        enum_column(AIPriority, "ai_priority"), nullable=True
    )
    ai_status: Mapped[AIStatus] = mapped_column(
        enum_column(AIStatus, "ai_status"), nullable=False, default=AIStatus.SKIPPED
    )

    # The funnel timestamps of Ch. 13 / ADR-015. Nothing reads them until week 6.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    first_dispatch_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    accepted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Notification(Base):
    """One row per alert actually sent to a responder."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sos_id: Mapped[int] = mapped_column(ForeignKey("sos.id", ondelete="CASCADE"), nullable=False)
    volunteer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    wave_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        enum_column(NotificationStatus, "notification_status"),
        nullable=False,
        default=NotificationStatus.SENT,
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DispatchEvent(Base):
    """Append-only decision log -- ADR-014.

    One row per candidate evaluated, alerted or rejected, with the reason. This
    is the sole source for every metric in ADR-015, which is why it is
    deliberately denormalised: `radius_m_at_eval` and `distance_m` record what
    was true at evaluation time, not what is true now.
    """

    __tablename__ = "dispatch_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sos_id: Mapped[int] = mapped_column(ForeignKey("sos.id", ondelete="CASCADE"), nullable=False)
    volunteer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    wave_number: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    radius_m_at_eval: Mapped[int] = mapped_column(Integer, nullable=False)
    # Null exactly when rejection_reason is `no_location`: a volunteer with no
    # fix has no distance, and inventing one would corrupt every distance-based
    # metric in ADR-015 (ADR-021).
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    skill_match: Mapped[bool] = mapped_column(Boolean, nullable=False)
    outcome: Mapped[DispatchOutcome] = mapped_column(
        enum_column(DispatchOutcome, "dispatch_outcome"), nullable=False
    )
    # Null exactly when outcome is `alerted`.
    rejection_reason: Mapped[RejectionReason | None] = mapped_column(
        enum_column(RejectionReason, "rejection_reason"), nullable=True
    )


class IncidentHistory(Base):
    """Per-incident summary written once on resolution. One row per SOS."""

    __tablename__ = "incident_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sos_id: Mapped[int] = mapped_column(
        ForeignKey("sos.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    response_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_radius_m: Mapped[int] = mapped_column(Integer, nullable=False)
    # Which ADR-012 condition drove escalation -- the split ADR-015 reports on.
    escalation_trigger: Mapped[EscalationTrigger] = mapped_column(
        enum_column(EscalationTrigger, "escalation_trigger"),
        nullable=False,
        default=EscalationTrigger.NONE,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
