from collections import defaultdict
from datetime import date
from statistics import median
import math

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import FctTransaction, Goal, UserProfile, User
from app.schemas import GoalsRequest, GoalsResponse

router = APIRouter()


def _months_remaining(today: date, target: date) -> int:
    months = (target.year - today.year) * 12 + (target.month - today.month)
    if target.day > today.day:
        months += 1
    return max(months, 0)


def _feasibility_status(ratio: float | None) -> str:
    if ratio is None:
        return "Unknown"
    if ratio >= 1.2:
        return "Comfortable"
    if ratio >= 0.9:
        return "On track"
    if ratio >= 0.7:
        return "At risk"
    return "Unrealistic"


def _encouragement(status: str, required: float | None, historical: float | None) -> str:
    if required is None:
        return "Goal is already funded or target date has passed."
    if historical is None:
        return "Import more monthly history to evaluate goal feasibility."
    if status in {"Comfortable", "On track"}:
        return "You're on track to finish early or on time if your current saving pace holds."
    shortfall = max(required - historical, 0.0)
    return f"You're short ${shortfall:.2f}/month. Reduce discretionary categories or extend the target date."


@router.post("", response_model=GoalsResponse)
def update_goals(
    payload: GoalsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    if payload.goal_amount < 0 or payload.reported_total_savings < 0:
        raise HTTPException(status_code=400, detail="Amounts must be non-negative")

    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile is None:
        profile = UserProfile(user_id=user_id, reported_total_savings=payload.reported_total_savings)
        db.add(profile)
    else:
        profile.reported_total_savings = payload.reported_total_savings

    goal = db.query(Goal).filter(Goal.user_id == user_id).first()
    if goal is None:
        goal = Goal(user_id=user_id, goal_amount=payload.goal_amount, target_date=payload.target_date)
        db.add(goal)
    else:
        goal.goal_amount = payload.goal_amount
        goal.target_date = payload.target_date

    txs = (
        db.query(FctTransaction)
        .filter(FctTransaction.user_id == user_id, FctTransaction.is_movement.is_(False))
        .order_by(FctTransaction.txn_date.asc())
        .all()
    )

    monthly_nets: dict[str, float] = defaultdict(float)
    for tx in txs:
        monthly_nets[tx.txn_date.strftime("%Y-%m")] += float(tx.amount)

    recent_months = sorted(monthly_nets.keys())[-6:]
    historical_saving = (
        float(median([monthly_nets[m] for m in recent_months])) if recent_months else None
    )

    today = date.today()
    months_remaining = _months_remaining(today, payload.target_date)
    remaining_amount = max(payload.goal_amount - payload.reported_total_savings, 0.0)
    required_monthly = (remaining_amount / months_remaining) if months_remaining > 0 else None

    feasibility_ratio = None
    if required_monthly and required_monthly > 0 and historical_saving is not None:
        feasibility_ratio = historical_saving / required_monthly

    projected_finish_months = None
    if remaining_amount == 0:
        projected_finish_months = 0
    elif historical_saving is not None and historical_saving > 0:
        projected_finish_months = math.ceil(remaining_amount / historical_saving)

    status = _feasibility_status(feasibility_ratio)

    db.commit()

    return GoalsResponse(
        reported_total_savings=payload.reported_total_savings,
        goal_amount=payload.goal_amount,
        target_date=payload.target_date,
        months_remaining=months_remaining,
        required_monthly=required_monthly,
        historical_saving=historical_saving,
        feasibility_ratio=feasibility_ratio,
        feasibility_status=status,  # type: ignore[arg-type]
        projected_finish_months=projected_finish_months,
        encouragement=_encouragement(status, required_monthly, historical_saving),
    )
