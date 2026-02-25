from sqlalchemy import case, func
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import FctTransaction, User
from app.schemas import (
    CategoryReviewMerchantItem,
    ReviewQueueMerchantItem,
    ReviewQueueResponse,
    ReviewQueueTransactionItem,
)

router = APIRouter()


def _tx_item(tx: FctTransaction) -> ReviewQueueTransactionItem:
    return ReviewQueueTransactionItem(
        id=tx.id,
        txn_date=tx.txn_date,
        amount=tx.amount,
        description_raw=tx.description_raw,
        merchant_key=tx.merchant_key,
        category=tx.category,
        is_movement=tx.is_movement,
        is_high_impact=tx.is_high_impact,
        user_confirmed=tx.user_confirmed,
    )


@router.get("", response_model=ReviewQueueResponse)
def get_review_queue(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    unknown_merchants = (
        db.query(
            FctTransaction.merchant_key.label("merchant_key"),
            func.count(FctTransaction.id).label("txn_count"),
            func.max(FctTransaction.txn_date).label("latest_txn_date"),
            func.min(FctTransaction.description_raw).label("sample_description"),
            func.sum(FctTransaction.amount).label("total_amount"),
        )
        .filter(FctTransaction.user_id == user_id, FctTransaction.category == "Unknown")
        .group_by(FctTransaction.merchant_key)
        .order_by(func.count(FctTransaction.id).desc(), FctTransaction.merchant_key.asc())
        .all()
    )

    large_movements = (
        db.query(FctTransaction)
        .filter(
            FctTransaction.user_id == user_id,
            FctTransaction.is_movement.is_(True),
            func.abs(FctTransaction.amount) >= 500,
        )
        .order_by(FctTransaction.txn_date.desc(), func.abs(FctTransaction.amount).desc())
        .limit(100)
        .all()
    )

    high_impact_spend = (
        db.query(FctTransaction)
        .filter(
            FctTransaction.user_id == user_id,
            FctTransaction.is_high_impact.is_(True),
            FctTransaction.amount < 0,
        )
        .order_by(FctTransaction.txn_date.desc(), func.abs(FctTransaction.amount).desc())
        .limit(100)
        .all()
    )

    category_review_rows = (
        db.query(
            FctTransaction.merchant_key.label("merchant_key"),
            FctTransaction.category.label("category"),
            FctTransaction.is_movement.label("is_movement"),
            func.count(FctTransaction.id).label("txn_count"),
            func.max(FctTransaction.txn_date).label("latest_txn_date"),
            func.min(FctTransaction.description_raw).label("sample_description"),
            func.sum(FctTransaction.amount).label("total_amount"),
            func.sum(case((FctTransaction.user_confirmed.is_(True), 1), else_=0)).label("user_confirmed_count"),
        )
        .filter(FctTransaction.user_id == user_id)
        .group_by(FctTransaction.merchant_key, FctTransaction.category, FctTransaction.is_movement)
        .order_by(func.max(FctTransaction.txn_date).desc(), func.count(FctTransaction.id).desc())
        .limit(300)
        .all()
    )

    return ReviewQueueResponse(
        unknown_merchants=[
            ReviewQueueMerchantItem(
                merchant_key=row.merchant_key,
                txn_count=int(row.txn_count or 0),
                latest_txn_date=row.latest_txn_date,
                sample_description=row.sample_description or "",
                total_amount=float(row.total_amount or 0.0),
            )
            for row in unknown_merchants
        ],
        category_review_merchants=[
            CategoryReviewMerchantItem(
                merchant_key=row.merchant_key,
                category=row.category,
                txn_count=int(row.txn_count or 0),
                latest_txn_date=row.latest_txn_date,
                sample_description=row.sample_description or "",
                total_amount=float(row.total_amount or 0.0),
                is_movement=bool(row.is_movement),
                user_confirmed_count=int(row.user_confirmed_count or 0),
            )
            for row in category_review_rows
        ],
        large_movements=[_tx_item(tx) for tx in large_movements],
        high_impact_spend=[_tx_item(tx) for tx in high_impact_spend],
    )
