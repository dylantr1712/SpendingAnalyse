from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasicCredentials
from sqlalchemy.orm import Session

from app.api.deps import basic_security, get_current_user
from app.core.auth import hash_password, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas import (
    AuthLoginRequest,
    AuthLoginResponse,
    AuthRegisterRequest,
    AuthSetupRequest,
    AuthStatusResponse,
)

router = APIRouter()


@router.get("/status", response_model=AuthStatusResponse)
def auth_status(db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == 1).first()
    return AuthStatusResponse(
        configured=bool(user and user.password_hash),
        username=user.email if user and user.password_hash else None,
    )


@router.post("/setup", response_model=AuthStatusResponse)
def auth_setup(
    payload: AuthSetupRequest,
    db: Session = Depends(get_db),
    credentials: HTTPBasicCredentials | None = Depends(basic_security),
):
    if not payload.username.strip() or not payload.password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    user = db.query(User).filter(User.id == 1).first()
    if user is None:
        user = User(id=1)
        db.add(user)
        db.flush()

    if user.password_hash:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to reset credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        if user.email != credentials.username or not verify_password(credentials.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )

    user.email = payload.username.strip()
    user.password_hash = hash_password(payload.password)
    db.commit()

    return AuthStatusResponse(configured=True, username=user.email)


@router.post("/register", response_model=AuthStatusResponse)
def auth_register(payload: AuthRegisterRequest, db: Session = Depends(get_db)):
    if not payload.username.strip() or not payload.password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    user = db.query(User).filter(User.id == 1).first()
    if user is None:
        user = User(id=1)
        db.add(user)
        db.flush()

    if user.password_hash:
        raise HTTPException(status_code=409, detail="Local account already registered")

    user.email = payload.username.strip()
    user.password_hash = hash_password(payload.password)
    db.commit()
    return AuthStatusResponse(configured=True, username=user.email)


@router.post("/login", response_model=AuthLoginResponse)
def auth_login(payload: AuthLoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == 1).first()
    if user is None or not user.password_hash:
        raise HTTPException(status_code=400, detail="Local credentials are not configured yet")
    if user.email != payload.username or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return AuthLoginResponse(ok=True, username=user.email or payload.username)


@router.get("/me", response_model=AuthStatusResponse)
def auth_me(current_user: User = Depends(get_current_user)):
    return AuthStatusResponse(configured=bool(current_user.password_hash), username=current_user.email)
