from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import FctTransaction, User
from app.schemas import (
    TransactionListItem,
    TransactionListResponse,
    TransactionMonthsResponse,
    TransactionBulkUpdateRequest,
    TransactionBulkUpdateResponse,
    TransactionUpdateRequest,
    TransactionUpdateResponse,
)

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


def _tx_list_item(tx: FctTransaction) -> TransactionListItem:
    return TransactionListItem(
        id=tx.id,
        txn_date=tx.txn_date,
        amount=tx.amount,
        description_raw=tx.description_raw,
        merchant_key=tx.merchant_key,
        category=tx.category,
        is_income=tx.is_income,
        is_movement=tx.is_movement,
        is_high_impact=tx.is_high_impact,
        user_confirmed=tx.user_confirmed,
    )


@router.get("/months", response_model=TransactionMonthsResponse)
def list_transaction_months(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(FctTransaction.txn_date)
        .filter(FctTransaction.user_id == current_user.id)
        .order_by(FctTransaction.txn_date.desc(), FctTransaction.id.desc())
        .all()
    )
    seen: set[str] = set()
    months: list[str] = []
    for (txn_date,) in rows:
        key = txn_date.strftime("%Y-%m")
        if key not in seen:
            seen.add(key)
            months.append(key)
    return TransactionMonthsResponse(months=months)


@router.get("", response_model=TransactionListResponse)
def list_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    category: str | None = None,
    search: str | None = None,
    only_unreviewed: bool = False,
    include_movements: bool = True,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    q = db.query(FctTransaction).filter(FctTransaction.user_id == current_user.id)

    if month and (start_date or end_date):
        raise HTTPException(status_code=400, detail="Use month or date range, not both")

    if month:
        year, mon = [int(x) for x in month.split("-")]
        month_start = date(year, mon, 1)
        if mon == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, mon + 1, 1)
        q = q.filter(FctTransaction.txn_date >= month_start, FctTransaction.txn_date < next_month)
    else:
        if start_date and end_date and start_date > end_date:
            raise HTTPException(status_code=400, detail="Start date must be on or before end date")
        if start_date:
            q = q.filter(FctTransaction.txn_date >= start_date)
        if end_date:
            q = q.filter(FctTransaction.txn_date <= end_date)

    if category:
        q = q.filter(FctTransaction.category == category)

    if search:
        like = f"%{search.strip()}%"
        q = q.filter(
            or_(
                FctTransaction.description_raw.ilike(like),
                FctTransaction.merchant_key.ilike(like),
            )
        )

    if only_unreviewed:
        q = q.filter(FctTransaction.user_confirmed.is_(False))

    if not include_movements:
        q = q.filter(FctTransaction.is_movement.is_(False))

    total = q.with_entities(func.count(FctTransaction.id)).scalar() or 0
    rows = (
        q.order_by(FctTransaction.txn_date.desc(), FctTransaction.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return TransactionListResponse(total=int(total), items=[_tx_list_item(tx) for tx in rows])


@router.post("/bulk", response_model=TransactionBulkUpdateResponse)
def bulk_update_transactions(
    payload: TransactionBulkUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ids = sorted({int(i) for i in payload.transaction_ids})
    if not ids:
        return TransactionBulkUpdateResponse(updated_count=0, transaction_ids=[])
    if payload.category is None and payload.user_confirmed is None:
        raise HTTPException(status_code=400, detail="No update fields provided")

    rows = (
        db.query(FctTransaction)
        .filter(FctTransaction.user_id == current_user.id, FctTransaction.id.in_(ids))
        .all()
    )
    for tx in rows:
        if payload.category is not None:
            tx.category = payload.category
            tx.is_high_impact = abs(tx.amount) >= 100 and payload.category in DISCRETIONARY
            if payload.user_confirmed is None:
                tx.user_confirmed = True
        if payload.user_confirmed is not None:
            tx.user_confirmed = payload.user_confirmed

    db.commit()
    return TransactionBulkUpdateResponse(updated_count=len(rows), transaction_ids=[tx.id for tx in rows])


@router.post("/{transaction_id}", response_model=TransactionUpdateResponse)
def update_transaction(
    transaction_id: int,
    payload: TransactionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    tx = (
        db.query(FctTransaction)
        .filter(FctTransaction.id == transaction_id, FctTransaction.user_id == user_id)
        .first()
    )
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if payload.category is not None:
        tx.category = payload.category
        tx.is_high_impact = abs(tx.amount) >= 100 and payload.category in DISCRETIONARY
        tx.user_confirmed = True if payload.user_confirmed is None else payload.user_confirmed
    elif payload.user_confirmed is not None:
        tx.user_confirmed = payload.user_confirmed

    db.commit()
    db.refresh(tx)
    return TransactionUpdateResponse(id=tx.id, category=tx.category, user_confirmed=tx.user_confirmed)
