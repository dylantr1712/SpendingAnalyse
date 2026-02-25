from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import engine
from app.db.session import SessionLocal
from app.models import User

from app.api.api import api_router

app = FastAPI(title="Spending Leak Detector")
app.include_router(api_router)


@app.on_event("startup")
def ensure_default_user() -> None:
    # Local/dev startup path: create schema if the DB is empty.
    Base.metadata.create_all(bind=engine)

    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == 1).first()
        if user is None:
            db.add(User(id=1, email=None, password_hash=None))
            db.commit()
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}
