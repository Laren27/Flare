"""Pydantic request and response bodies (Ch. 20).

Kept separate from `app.models`: those are the persistence schema, these are the
wire contract, and the two are free to diverge. `UserOut` in particular exists
so that `password_hash` cannot be returned by accident.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import UserRole

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
