"""Pydantic request and response bodies (Ch. 20).

Kept separate from `app.models`: those are the persistence schema, these are the
wire contract, and the two are free to diverge. `UserOut` in particular exists
so that `password_hash` cannot be returned by accident.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import SkillClass, SOSStatus, UserRole

# Signup is open to citizens and volunteers only. Admins approve volunteer
# certificates (ADR-006), so an open admin route would make that trust
# unfalsifiable -- they are created by scripts/create_admin.py instead (ADR-019).
SignupRole = Literal[UserRole.CITIZEN, UserRole.VOLUNTEER]

# bcrypt hashes at most 72 bytes; the service enforces the byte limit, this
# catches the common case at the edge with a readable error.
PasswordField = Field(min_length=8, max_length=72)


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=6, max_length=20)
    password: str = PasswordField
    role: SignupRole


class LoginRequest(BaseModel):
    """JSON rather than an OAuth2 password form -- ADR-019. The identifier is a
    phone number, which the form's `username` field would misname."""

    phone: str = Field(min_length=6, max_length=20)
    password: str = Field(min_length=1, max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    role: UserRole
    created_at: datetime


class SOSCreateRequest(BaseModel):
    """Coordinates come from the browser Geolocation API (Ch. 17). Bounds are
    validated here so an impossible coordinate is rejected at the edge rather
    than producing a plausible-looking distance deeper in."""

    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    description: str | None = Field(default=None, max_length=2000)


class CandidateOut(BaseModel):
    """Deliberately free of personal data. The citizen has no need for a
    responder's name or number before anyone has accepted (Ch. 22), and week 5's
    citizen view only ever renders the one responder who did."""

    model_config = ConfigDict(from_attributes=True)

    volunteer_id: int
    distance_m: float
    skill: SkillClass
    skill_match: bool


class SOSCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: SOSStatus
    current_radius_m: int
    wave_count: int
    created_at: datetime
    first_dispatch_at: datetime | None

    candidates: list[CandidateOut]
    # Every volunteer assessed, selected or not. The gap between this and
    # len(candidates) is the first stage of the ADR-015 dispatch funnel, and
    # each one has a DispatchEvents row explaining itself.
    evaluated_count: int
    # Selected candidates whose alert reached a live socket. The gap between
    # this and len(candidates) is the no_socket population -- selected, but
    # not reachable at the moment it mattered.
    alerted_count: int
