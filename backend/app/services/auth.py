"""Authentication logic -- ADR-019.

Everything here is deliberately HTTP-agnostic. Routers translate the domain
errors raised below into status codes; this module knows nothing about FastAPI
(Ch. 20).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# bcrypt directly rather than passlib, which is unmaintained and breaks against
# modern bcrypt releases -- ADR-019.
import bcrypt

# PyJWT rather than python-jose, likewise unmaintained -- ADR-019.
import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import SkillClass, User, UserRole, Volunteer

# bcrypt hashes at most 72 bytes and raises rather than silently truncating.
# Enforced here as well as in the request schema so the limit holds for any
# caller, including scripts/create_admin.py.
MAX_PASSWORD_BYTES = 72


class AuthError(Exception):
    """Base for domain errors this module raises."""


class PhoneAlreadyRegistered(AuthError):
    pass


class InvalidCredentials(AuthError):
    pass


class InvalidToken(AuthError):
    pass


@dataclass(frozen=True, slots=True)
class TokenClaims:
    user_id: int
    role: UserRole


@dataclass(frozen=True, slots=True)
class IssuedToken:
    access_token: str
    expires_in: int
    """Seconds until expiry, so a client need not parse the token to know."""


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))


def create_access_token(user: User) -> IssuedToken:
    settings = get_settings()
    expires_in = settings.jwt_expiry_minutes * 60
    issued_at = datetime.now(UTC)

    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "iat": issued_at,
        "exp": issued_at + timedelta(seconds=expires_in),
    }
    token = jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )
    return IssuedToken(access_token=token, expires_in=expires_in)


def decode_access_token(token: str) -> TokenClaims:
    """Verify signature and expiry (Ch. 22) and return the claims we rely on."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "role"]},
        )
        return TokenClaims(user_id=int(payload["sub"]), role=UserRole(payload["role"]))
    except (jwt.InvalidTokenError, ValueError) as exc:
        # Expired, tampered, wrong algorithm, or carrying a role we no longer
        # recognise -- all indistinguishable to a caller, deliberately.
        raise InvalidToken(str(exc)) from exc


async def create_user(
    session: AsyncSession,
    *,
    name: str,
    phone: str,
    password: str,
    role: UserRole,
) -> User:
    """Register a user. Volunteers also get their `volunteers` row, unverified
    and offline -- skill declaration and admin approval come later (ADR-006).

    Uniqueness is enforced by the constraint, not by a preceding SELECT. A
    check-then-insert would be the same time-of-check-to-time-of-use race that
    ADR-011 rejects for the accept-lock; the argument does not stop being true
    because the stakes are lower here.
    """
    user = User(
        name=name,
        phone=phone,
        role=role,
        password_hash=hash_password(password),
    )
    session.add(user)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise PhoneAlreadyRegistered(phone) from exc

    if role is UserRole.VOLUNTEER:
        session.add(
            Volunteer(
                user_id=user.id,
                verified=False,
                skills=SkillClass.GENERAL,
                availability=False,
            )
        )

    await session.commit()
    return user


async def authenticate(session: AsyncSession, *, phone: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.phone == phone))

    # Hash even when the phone is unknown, so a missing user and a wrong
    # password take comparable time and the endpoint does not leak which
    # phone numbers are registered.
    password_hash = user.password_hash if user else _DUMMY_HASH
    if not verify_password(password, password_hash) or user is None:
        raise InvalidCredentials(phone)

    return user


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


# Compared against when no user matches, purely for timing symmetry above.
_DUMMY_HASH = hash_password("flare-nonexistent-user-placeholder")
