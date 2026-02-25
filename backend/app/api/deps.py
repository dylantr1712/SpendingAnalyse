from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.core.auth import verify_password


basic_security = HTTPBasic(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Basic"},
    )


def get_current_user(
    db: Session = Depends(get_db),
    credentials: HTTPBasicCredentials | None = Depends(basic_security),
) -> User:
    user = db.query(User).filter(User.id == 1).first()
    if user is None:
        user = User(id=1, email=None, password_hash=None)
        db.add(user)
        db.commit()
        db.refresh(user)

    # Bootstrap mode: no credentials configured yet.
    if not user.password_hash:
        return user

    if credentials is None:
        raise _unauthorized()

    if user.email != credentials.username or not verify_password(credentials.password, user.password_hash):
        raise _unauthorized()

    return user
