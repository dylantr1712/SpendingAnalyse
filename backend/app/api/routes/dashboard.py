from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import DashboardResponse, DashboardTrendsResponse
from app.services.analytics import build_dashboard, build_dashboard_trends

router = APIRouter()


@router.get("", response_model=DashboardResponse)
def get_dashboard(
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return build_dashboard(db=db, user_id=current_user.id, month=month)


@router.get("/trends", response_model=DashboardTrendsResponse)
def get_dashboard_trends(
    months: int = Query(default=12, ge=1, le=36),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return build_dashboard_trends(db=db, user_id=current_user.id, months=months)
