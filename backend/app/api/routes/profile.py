from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import FctTransaction, Goal, ImportBatch, RawTransaction, User, UserProfile
from app.schemas import BalanceProfileRequest, BalanceProfileResponse, ResetResponse

router = APIRouter()


@router.get("/balances", response_model=BalanceProfileResponse)
def get_balances(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if profile is None:
        return BalanceProfileResponse()
    return BalanceProfileResponse(
        bank_balance=profile.bank_balance_override,
        savings_balance=profile.savings_balance_override,
        investments_balance=profile.investments_balance_override,
        balances_as_of=profile.balances_as_of,
    )


@router.post("/balances", response_model=BalanceProfileResponse)
def update_balances(
    payload: BalanceProfileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.bank_balance is None and payload.savings_balance is None and payload.investments_balance is None:
        if payload.balances_as_of is not None:
            raise HTTPException(status_code=400, detail="Balances are required when setting as-of date")

    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if profile is None:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)

    profile.bank_balance_override = payload.bank_balance
    profile.savings_balance_override = payload.savings_balance
    profile.investments_balance_override = payload.investments_balance
    if payload.bank_balance is not None or payload.savings_balance is not None or payload.investments_balance is not None:
        profile.balances_as_of = payload.balances_as_of or date.today()
    else:
        profile.balances_as_of = payload.balances_as_of

    db.commit()

    return BalanceProfileResponse(
        bank_balance=profile.bank_balance_override,
        savings_balance=profile.savings_balance_override,
        investments_balance=profile.investments_balance_override,
        balances_as_of=profile.balances_as_of,
    )


@router.post("/reset", response_model=ResetResponse)
def reset_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    batch_ids = db.query(ImportBatch.id).filter(ImportBatch.user_id == user_id).subquery()
    db.query(RawTransaction).filter(RawTransaction.import_batch_id.in_(batch_ids)).delete(
        synchronize_session=False
    )
    db.query(FctTransaction).filter(FctTransaction.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(ImportBatch).filter(ImportBatch.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(Goal).filter(Goal.user_id == user_id).delete(synchronize_session=False)
    db.query(UserProfile).filter(UserProfile.user_id == user_id).delete(synchronize_session=False)

    db.commit()
    return ResetResponse(ok=True)
