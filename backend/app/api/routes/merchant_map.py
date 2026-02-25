from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import FctTransaction, MerchantMap, User
from app.schemas import MerchantMapUpdateRequest, MerchantMapUpdateResponse

router = APIRouter()

DISCRETIONARY = {
    "Eating Out",
    "Food Delivery",
    "Shopping",
    "Entertainment",
    "Subscriptions",
    "Other",
    "Unknown",
}


@router.post("", response_model=MerchantMapUpdateResponse)
def update_merchant_map(
    payload: MerchantMapUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    mapping = (
        db.query(MerchantMap)
        .filter(MerchantMap.user_id == user_id, MerchantMap.merchant_key == payload.merchant_key)
        .first()
    )
    if mapping is None:
        mapping = MerchantMap(
            user_id=user_id,
            merchant_key=payload.merchant_key,
            category=payload.category,
            source="user",
            updated_at=datetime.utcnow(),
        )
        db.add(mapping)
    else:
        mapping.category = payload.category
        mapping.source = "user"
        mapping.updated_at = datetime.utcnow()

    updated_count = 0
    if payload.apply_to_existing:
        rows = (
            db.query(FctTransaction)
            .filter(FctTransaction.user_id == user_id, FctTransaction.merchant_key == payload.merchant_key)
            .all()
        )
        for tx in rows:
            tx.category = payload.category
            tx.is_high_impact = abs(tx.amount) >= 100 and payload.category in DISCRETIONARY
            tx.user_confirmed = True
        updated_count = len(rows)

    db.commit()
    return MerchantMapUpdateResponse(
        merchant_key=payload.merchant_key,
        category=payload.category,
        updated_transactions=updated_count,
    )
