"""Auth router (Ch. 14). Handlers translate between HTTP and the service layer
and hold no logic of their own (Ch. 20)."""

from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession
from app.models import UserRole
from app.schemas import LoginRequest, SignupRequest, TokenResponse, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, session: DbSession) -> UserOut:
    try:
        user = await auth_service.create_user(
            session,
            name=payload.name,
            phone=payload.phone,
            password=payload.password,
            role=UserRole(payload.role),
        )
    except auth_service.PhoneAlreadyRegistered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That phone number is already registered",
        ) from None

    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: DbSession) -> TokenResponse:
    try:
        user = await auth_service.authenticate(
            session, phone=payload.phone, password=payload.password
        )
    except auth_service.InvalidCredentials:
        # One message for both "no such phone" and "wrong password".
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect phone number or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    token = auth_service.create_access_token(user)
    return TokenResponse(access_token=token.access_token, expires_in=token.expires_in)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
