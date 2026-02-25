from __future__ import annotations

from collections import defaultdict
from datetime import date
import os
from statistics import median

from dateutil import parser
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import FctTransaction, ImportBatch, RawTransaction, UserProfile
from app.schemas import (
    DashboardCategoryItem,
    DashboardCategoryTrend,
    DashboardInsightItem,
    DashboardKpis,
    DashboardMerchantItem,
    DashboardMonthSummary,
    DashboardResponse,
    DashboardTrendPoint,
    DashboardTrendsResponse,
)


DISCRETIONARY_CATEGORIES = {
    "Eating Out",
    "Food Delivery",
    "Shopping",
    "Entertainment",
    "Subscriptions",
    "Other",
    "Unknown",
}


def _month_key(txn_date) -> str:
    return txn_date.strftime("%Y-%m")


def _severity_for_ratio(ratio: float) -> str:
    if ratio >= 0.5:
        return "high"
    if ratio >= 0.2:
        return "warning"
    return "info"


def _parse_month_string(month: str | None) -> tuple[int, int] | None:
    if not month:
        return None
    try:
        year_s, mon_s = month.split("-", 1)
        year = int(year_s)
        mon = int(mon_s)
        if mon < 1 or mon > 12:
            return None
        return year, mon
    except (ValueError, AttributeError):
        return None


def _parse_raw_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return parser.parse(str(raw), dayfirst=True).date()
    except (ValueError, TypeError, parser.ParserError):
        return None


def _parse_balance(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return float(text.replace(",", "").replace("$", ""))
    except ValueError:
        return None


def _month_stats_from_transactions(txs: list[FctTransaction], month: str) -> DashboardMonthSummary:
    month_txs = [tx for tx in txs if _month_key(tx.txn_date) == month]
    non_movement_month_txs = [tx for tx in month_txs if not tx.is_movement]
    non_movement_expense_txs = [tx for tx in non_movement_month_txs if tx.amount < 0]

    income_total = float(sum(tx.amount for tx in non_movement_month_txs if tx.amount > 0))
    expense_total = float(sum(abs(tx.amount) for tx in non_movement_expense_txs))
    movement_total = float(sum(abs(tx.amount) for tx in month_txs if tx.is_movement))
    net = income_total - expense_total
    savings_rate = (net / income_total) if income_total else None
    unknown_count = sum(1 for tx in month_txs if tx.category == "Unknown")
    unknown_percent = (unknown_count / len(month_txs)) * 100 if month_txs else 0.0

    return DashboardMonthSummary(
        month=month,
        income_total=round(income_total, 2),
        expense_total=round(expense_total, 2),
        net=round(net, 2),
        savings_rate=savings_rate,
        movement_total=round(movement_total, 2),
        unknown_percent=round(unknown_percent, 1),
    )


def build_dashboard(db: Session, user_id: int, month: str | None = None) -> DashboardResponse:
    source = os.getenv("DASHBOARD_ANALYTICS_SOURCE", "auto").lower()
    if source in {"auto", "dbt"}:
        dbt_result = _build_dashboard_from_dbt(db=db, user_id=user_id, month=month)
        if dbt_result is not None:
            return dbt_result
        if source == "dbt":
            # Explicit dbt mode requested, but marts are unavailable; fall back to ORM to keep app usable.
            pass
    return _build_dashboard_from_transactions(db=db, user_id=user_id, month=month)


def build_dashboard_trends(db: Session, user_id: int, months: int = 12) -> DashboardTrendsResponse:
    txs = (
        db.query(FctTransaction)
        .filter(FctTransaction.user_id == user_id)
        .order_by(FctTransaction.txn_date.asc(), FctTransaction.id.asc())
        .all()
    )

    if not txs:
        return DashboardTrendsResponse(
            months=[],
            points=[],
            category_trends=[],
            kpis=DashboardKpis(
                avg_income=0.0,
                avg_expense=0.0,
                avg_net=0.0,
                avg_savings_rate=None,
                best_savings_month=None,
                best_savings_value=None,
                worst_spend_month=None,
                worst_spend_value=None,
                last_month_net_change=None,
                current_account_balance=None,
                current_total_balance=None,
                account_balance_change_12m=None,
                total_balance_change_12m=None,
            ),
        )

    months_sorted: list[str] = []
    seen: set[str] = set()
    for tx in txs:
        key = _month_key(tx.txn_date)
        if key not in seen:
            seen.add(key)
            months_sorted.append(key)

    if months <= 0:
        months = 12
    months_window = months_sorted[-months:]
    months_window_set = set(months_window)

    monthly_totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {"income": 0.0, "expense": 0.0, "movement": 0.0}
    )
    monthly_unknown: dict[str, int] = defaultdict(int)
    monthly_txn_count: dict[str, int] = defaultdict(int)
    monthly_category_expense: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    monthly_savings_net: dict[str, float] = defaultdict(float)
    monthly_investments_net: dict[str, float] = defaultdict(float)
    monthly_account_delta: dict[str, float] = defaultdict(float)

    for tx in txs:
        m = _month_key(tx.txn_date)
        monthly_txn_count[m] += 1
        if tx.category == "Unknown":
            monthly_unknown[m] += 1
        amt = float(tx.amount)
        monthly_account_delta[m] += amt
        if tx.is_movement:
            monthly_totals[m]["movement"] += abs(amt)
        else:
            if amt > 0:
                monthly_totals[m]["income"] += amt
            elif amt < 0:
                monthly_totals[m]["expense"] += abs(amt)
                monthly_category_expense[m][tx.category] += abs(amt)
            if tx.category == "Savings":
                monthly_savings_net[m] += amt
            elif tx.category == "Investments":
                monthly_investments_net[m] += amt

    raw_rows = (
        db.query(RawTransaction.txn_date_raw, RawTransaction.balance_raw, RawTransaction.id)
        .join(ImportBatch, RawTransaction.import_batch_id == ImportBatch.id)
        .filter(ImportBatch.user_id == user_id)
        .all()
    )
    parsed_balances: list[tuple[date, int, float]] = []
    for txn_date_raw, balance_raw, row_id in raw_rows:
        txn_date = _parse_raw_date(txn_date_raw)
        balance = _parse_balance(balance_raw)
        if txn_date is None or balance is None:
            continue
        parsed_balances.append((txn_date, int(row_id), balance))
    parsed_balances.sort(key=lambda item: (item[0], item[1]))

    balance_by_month: dict[str, float] = {}
    for txn_date, _, balance in parsed_balances:
        balance_by_month[_month_key(txn_date)] = balance

    filled_balance_by_month: dict[str, float | None] = {}
    last_balance: float | None = None
    for month in months_sorted:
        if month in balance_by_month:
            last_balance = balance_by_month[month]
        filled_balance_by_month[month] = last_balance

    if not balance_by_month:
        running_balance = 0.0
        filled_balance_by_month = {}
        for month in months_sorted:
            running_balance += monthly_account_delta.get(month, 0.0)
            filled_balance_by_month[month] = running_balance

    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    as_of_month = months_sorted[-1]
    if profile and profile.balances_as_of:
        as_of_month = profile.balances_as_of.strftime("%Y-%m")

    as_of_index = 0
    for idx, month in enumerate(months_sorted):
        if month <= as_of_month:
            as_of_index = idx
        else:
            break
    as_of_effective = months_sorted[as_of_index] if months_sorted else as_of_month

    account_offset = 0.0
    if profile and profile.bank_balance_override is not None:
        base_balance = filled_balance_by_month.get(as_of_effective)
        if base_balance is None:
            base_balance = 0.0
        account_offset = profile.bank_balance_override - base_balance

    savings_series: dict[str, float] = {}
    investments_series: dict[str, float] = {}
    cumulative_savings = 0.0
    cumulative_investments = 0.0
    for month in months_sorted:
        cumulative_savings += monthly_savings_net.get(month, 0.0)
        cumulative_investments += monthly_investments_net.get(month, 0.0)
        savings_series[month] = cumulative_savings
        investments_series[month] = cumulative_investments

    savings_offset = 0.0
    if profile and profile.savings_balance_override is not None:
        savings_offset = profile.savings_balance_override - savings_series.get(as_of_effective, 0.0)

    investments_offset = 0.0
    if profile and profile.investments_balance_override is not None:
        investments_offset = profile.investments_balance_override - investments_series.get(
            as_of_effective, 0.0
        )

    points: list[DashboardTrendPoint] = []
    for month in months_sorted:
        if month not in months_window_set:
            continue
        income_total = monthly_totals[month]["income"]
        expense_total = monthly_totals[month]["expense"]
        net = income_total - expense_total
        savings_rate = (net / income_total) if income_total else None
        txn_count = monthly_txn_count.get(month, 0)
        unknown_count = monthly_unknown.get(month, 0)
        unknown_percent = (unknown_count / txn_count) * 100 if txn_count else 0.0
        account_balance = filled_balance_by_month.get(month)
        if account_balance is not None:
            account_balance += account_offset
        savings_balance = savings_series.get(month, 0.0) + savings_offset
        investments_balance = investments_series.get(month, 0.0) + investments_offset
        total_balance = (
            account_balance + savings_balance + investments_balance if account_balance is not None else None
        )
        points.append(
            DashboardTrendPoint(
                month=month,
                income_total=round(income_total, 2),
                expense_total=round(expense_total, 2),
                net=round(net, 2),
                savings_rate=savings_rate,
                movement_total=round(monthly_totals[month]["movement"], 2),
                unknown_percent=round(unknown_percent, 1),
                savings_net=round(monthly_savings_net.get(month, 0.0), 2),
                investments_net=round(monthly_investments_net.get(month, 0.0), 2),
                account_balance_end=round(account_balance, 2) if account_balance is not None else None,
                savings_balance_end=round(savings_balance, 2) if savings_balance is not None else None,
                investments_balance_end=round(investments_balance, 2)
                if investments_balance is not None
                else None,
                total_balance_end=round(total_balance, 2) if total_balance is not None else None,
            )
        )

    category_totals_window: dict[str, float] = defaultdict(float)
    for month in months_window:
        for category, total in monthly_category_expense.get(month, {}).items():
            category_totals_window[category] += total

    top_categories = [
        category
        for category, _ in sorted(category_totals_window.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]

    category_trends: list[DashboardCategoryTrend] = []
    for category in top_categories:
        category_trends.append(
            DashboardCategoryTrend(
                category=category,
                monthly_totals=[
                    round(monthly_category_expense.get(month, {}).get(category, 0.0), 2)
                    for month in months_window
                ],
            )
        )

    def _avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 2) if values else 0.0

    avg_income = _avg([p.income_total for p in points])
    avg_expense = _avg([p.expense_total for p in points])
    avg_net = _avg([p.net for p in points])
    avg_savings_rate = None
    sr_values = [p.savings_rate for p in points if p.savings_rate is not None]
    if sr_values:
        avg_savings_rate = sum(sr_values) / len(sr_values)

    best_savings_month = None
    best_savings_value = None
    worst_spend_month = None
    worst_spend_value = None
    if points:
        best = max(points, key=lambda p: p.net)
        best_savings_month = best.month
        best_savings_value = best.net
        worst = max(points, key=lambda p: p.expense_total)
        worst_spend_month = worst.month
        worst_spend_value = worst.expense_total

    last_month_net_change = None
    if len(points) >= 2:
        last_month_net_change = round(points[-1].net - points[-2].net, 2)

    current_account_balance = points[-1].account_balance_end if points else None
    current_savings_balance = points[-1].savings_balance_end if points else None
    current_investments_balance = points[-1].investments_balance_end if points else None
    current_total_balance = points[-1].total_balance_end if points else None

    account_balance_change_12m = None
    total_balance_change_12m = None
    if len(points) >= 2:
        if points[0].account_balance_end is not None and points[-1].account_balance_end is not None:
            account_balance_change_12m = round(
                points[-1].account_balance_end - points[0].account_balance_end, 2
            )
        if points[0].total_balance_end is not None and points[-1].total_balance_end is not None:
            total_balance_change_12m = round(
                points[-1].total_balance_end - points[0].total_balance_end, 2
            )

    return DashboardTrendsResponse(
        months=months_window,
        points=points,
        category_trends=category_trends,
        kpis=DashboardKpis(
            avg_income=avg_income,
            avg_expense=avg_expense,
            avg_net=avg_net,
            avg_savings_rate=avg_savings_rate,
            best_savings_month=best_savings_month,
            best_savings_value=best_savings_value,
            worst_spend_month=worst_spend_month,
            worst_spend_value=worst_spend_value,
            last_month_net_change=last_month_net_change,
            current_account_balance=current_account_balance,
            current_savings_balance=current_savings_balance,
            current_investments_balance=current_investments_balance,
            current_total_balance=current_total_balance,
            account_balance_change_12m=account_balance_change_12m,
            total_balance_change_12m=total_balance_change_12m,
        ),
    )


def _build_dashboard_from_transactions(db: Session, user_id: int, month: str | None = None) -> DashboardResponse:
    txs = (
        db.query(FctTransaction)
        .filter(FctTransaction.user_id == user_id)
        .order_by(FctTransaction.txn_date.asc(), FctTransaction.id.asc())
        .all()
    )

    if not txs:
        return DashboardResponse(
            month="",
            income_total=0.0,
            expense_total=0.0,
            net=0.0,
            savings_rate=None,
            movement_total=0.0,
            unknown_percent=0.0,
        )

    months = []
    seen_months: set[str] = set()
    for tx in txs:
        m = _month_key(tx.txn_date)
        if m not in seen_months:
            seen_months.add(m)
            months.append(m)
    selected_month = month if month in seen_months else months[-1]
    prev_month = None
    selected_idx = months.index(selected_month)
    if selected_idx > 0:
        prev_month = months[selected_idx - 1]

    current_summary = _month_stats_from_transactions(txs, selected_month)
    previous_summary = _month_stats_from_transactions(txs, prev_month) if prev_month else None

    month_txs = [tx for tx in txs if _month_key(tx.txn_date) == selected_month]
    non_movement_month_txs = [tx for tx in month_txs if not tx.is_movement]
    non_movement_expense_txs = [tx for tx in non_movement_month_txs if tx.amount < 0]

    category_totals: dict[str, float] = defaultdict(float)
    category_counts: dict[str, int] = defaultdict(int)
    merchant_totals: dict[str, float] = defaultdict(float)
    merchant_counts: dict[str, int] = defaultdict(int)
    for tx in non_movement_expense_txs:
        amount = abs(float(tx.amount))
        category_totals[tx.category] += amount
        category_counts[tx.category] += 1
        merchant_totals[tx.merchant_key] += amount
        merchant_counts[tx.merchant_key] += 1

    category_breakdown = [
        DashboardCategoryItem(
            category=category,
            expense_total=round(total, 2),
            txn_count=category_counts[category],
        )
        for category, total in sorted(category_totals.items(), key=lambda x: (-x[1], x[0]))
    ]

    top_merchants = [
        DashboardMerchantItem(
            merchant_key=merchant,
            expense_total=round(total, 2),
            txn_count=merchant_counts[merchant],
        )
        for merchant, total in sorted(merchant_totals.items(), key=lambda x: (-x[1], x[0]))[:8]
    ]

    insights = _build_insights(
        txs=txs,
        current_month=selected_month,
        income_total=current_summary.income_total,
        expense_total=current_summary.expense_total,
        unknown_percent=current_summary.unknown_percent,
    )

    return DashboardResponse(
        month=current_summary.month,
        income_total=current_summary.income_total,
        expense_total=current_summary.expense_total,
        net=current_summary.net,
        savings_rate=current_summary.savings_rate,
        movement_total=current_summary.movement_total,
        unknown_percent=current_summary.unknown_percent,
        previous_month_summary=previous_summary,
        category_breakdown=category_breakdown,
        top_merchants=top_merchants,
        insights=insights,
    )


def _build_dashboard_from_dbt(db: Session, user_id: int, month: str | None = None) -> DashboardResponse | None:
    parsed_month = _parse_month_string(month)
    requested_month_start = date(parsed_month[0], parsed_month[1], 1) if parsed_month else None

    try:
        if requested_month_start is not None:
            monthly_row = db.execute(
                text(
                    """
                    select month_start, income_total, expense_total, net, savings_rate, movement_total, unknown_percent
                    from mart_monthly_summary
                    where user_id = :user_id and month_start = :month_start
                    limit 1
                    """
                ),
                {"user_id": user_id, "month_start": requested_month_start},
            ).mappings().first()
            if monthly_row is None:
                monthly_row = db.execute(
                    text(
                        """
                        select month_start, income_total, expense_total, net, savings_rate, movement_total, unknown_percent
                        from mart_monthly_summary
                        where user_id = :user_id
                        order by month_start desc
                        limit 1
                        """
                    ),
                    {"user_id": user_id},
                ).mappings().first()
        else:
            monthly_row = db.execute(
                text(
                    """
                    select month_start, income_total, expense_total, net, savings_rate, movement_total, unknown_percent
                    from mart_monthly_summary
                    where user_id = :user_id
                    order by month_start desc
                    limit 1
                    """
                ),
                {"user_id": user_id},
            ).mappings().first()
    except SQLAlchemyError:
        db.rollback()
        return None

    if monthly_row is None:
        return None

    month_start = monthly_row["month_start"]
    month = month_start.strftime("%Y-%m") if hasattr(month_start, "strftime") else str(month_start)[:7]

    try:
        previous_row = db.execute(
            text(
                """
                select month_start, income_total, expense_total, net, savings_rate, movement_total, unknown_percent
                from mart_monthly_summary
                where user_id = :user_id and month_start < :month_start
                order by month_start desc
                limit 1
                """
            ),
            {"user_id": user_id, "month_start": month_start},
        ).mappings().first()
    except SQLAlchemyError:
        db.rollback()
        return None

    try:
        category_rows = db.execute(
            text(
                """
                select category, expense_total, txn_count
                from mart_category_monthly
                where user_id = :user_id and month_start = :month_start
                  and expense_total > 0
                order by expense_total desc, category asc
                """
            ),
            {"user_id": user_id, "month_start": month_start},
        ).mappings().all()
    except SQLAlchemyError:
        db.rollback()
        return None

    # Top merchants and detailed insight phrasing are not fully present in current marts; compute from fct for now.
    txs = (
        db.query(FctTransaction)
        .filter(FctTransaction.user_id == user_id)
        .order_by(FctTransaction.txn_date.asc(), FctTransaction.id.asc())
        .all()
    )
    if not txs:
        return None

    month_txs = [tx for tx in txs if _month_key(tx.txn_date) == month]
    non_movement_expense_txs = [tx for tx in month_txs if (not tx.is_movement and tx.amount < 0)]
    merchant_totals: dict[str, float] = defaultdict(float)
    merchant_counts: dict[str, int] = defaultdict(int)
    for tx in non_movement_expense_txs:
        amt = abs(float(tx.amount))
        merchant_totals[tx.merchant_key] += amt
        merchant_counts[tx.merchant_key] += 1

    top_merchants = [
        DashboardMerchantItem(
            merchant_key=merchant,
            expense_total=round(total, 2),
            txn_count=merchant_counts[merchant],
        )
        for merchant, total in sorted(merchant_totals.items(), key=lambda x: (-x[1], x[0]))[:8]
    ]

    insights = _build_insights(
        txs=txs,
        current_month=month,
        income_total=float(monthly_row["income_total"] or 0.0),
        expense_total=float(monthly_row["expense_total"] or 0.0),
        unknown_percent=float(monthly_row["unknown_percent"] or 0.0),
    )

    return DashboardResponse(
        month=month,
        income_total=round(float(monthly_row["income_total"] or 0.0), 2),
        expense_total=round(float(monthly_row["expense_total"] or 0.0), 2),
        net=round(float(monthly_row["net"] or 0.0), 2),
        savings_rate=float(monthly_row["savings_rate"]) if monthly_row["savings_rate"] is not None else None,
        movement_total=round(float(monthly_row["movement_total"] or 0.0), 2),
        unknown_percent=round(float(monthly_row["unknown_percent"] or 0.0), 1),
        previous_month_summary=(
            DashboardMonthSummary(
                month=(
                    previous_row["month_start"].strftime("%Y-%m")
                    if hasattr(previous_row["month_start"], "strftime")
                    else str(previous_row["month_start"])[:7]
                ),
                income_total=round(float(previous_row["income_total"] or 0.0), 2),
                expense_total=round(float(previous_row["expense_total"] or 0.0), 2),
                net=round(float(previous_row["net"] or 0.0), 2),
                savings_rate=float(previous_row["savings_rate"]) if previous_row["savings_rate"] is not None else None,
                movement_total=round(float(previous_row["movement_total"] or 0.0), 2),
                unknown_percent=round(float(previous_row["unknown_percent"] or 0.0), 1),
            )
            if previous_row is not None
            else None
        ),
        category_breakdown=[
            DashboardCategoryItem(
                category=row["category"],
                expense_total=round(float(row["expense_total"] or 0.0), 2),
                txn_count=int(row["txn_count"] or 0),
            )
            for row in category_rows
        ],
        top_merchants=top_merchants,
        insights=insights,
    )


def _build_insights(
    *,
    txs: list[FctTransaction],
    current_month: str,
    income_total: float,
    expense_total: float,
    unknown_percent: float,
) -> list[DashboardInsightItem]:
    insights: list[DashboardInsightItem] = []

    monthly_expense_by_category: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    monthly_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    first_week_expense = 0.0
    current_subscriptions = 0.0
    current_discretionary = 0.0

    for tx in txs:
        m = _month_key(tx.txn_date)
        if tx.is_movement:
            continue
        if tx.amount > 0:
            monthly_totals[m]["income"] += float(tx.amount)
            continue

        amt = abs(float(tx.amount))
        monthly_totals[m]["expense"] += amt
        monthly_expense_by_category[m][tx.category] += amt

        if m == current_month:
            if tx.txn_date.day <= 7:
                first_week_expense += amt
            if tx.category == "Subscriptions":
                current_subscriptions += amt
            if tx.category in DISCRETIONARY_CATEGORIES:
                current_discretionary += amt

    months_sorted = sorted(monthly_totals.keys())
    if current_month in monthly_totals and monthly_totals[current_month]["expense"] > 0:
        velocity = first_week_expense / monthly_totals[current_month]["expense"]
        if velocity >= 0.45:
            insights.append(
                DashboardInsightItem(
                    kind="spend_velocity",
                    title="High Early-Month Spend Velocity",
                    detail=f"First 7 days used {velocity*100:.1f}% of this month's non-movement expenses.",
                    severity="warning" if velocity < 0.6 else "high",
                )
            )

    if unknown_percent >= 10:
        insights.append(
            DashboardInsightItem(
                kind="unknown_drag",
                title="Unknown Category Drag",
                detail=f"{unknown_percent:.1f}% of this month's transactions are still uncategorized.",
                severity="warning" if unknown_percent < 25 else "high",
            )
        )

    if current_subscriptions > 0:
        subscription_share = (current_subscriptions / income_total) if income_total else 0.0
        insights.append(
            DashboardInsightItem(
                kind="subscription_burden",
                title="Subscription Burden",
                detail=(
                    f"Subscriptions are ${current_subscriptions:.2f} this month"
                    + (f" ({subscription_share*100:.1f}% of income)." if income_total else ".")
                ),
                severity="info" if subscription_share < 0.1 else "warning",
            )
        )

    if len(months_sorted) >= 4:
        expense_series = [monthly_totals[m]["expense"] for m in months_sorted]
        last3 = expense_series[-3:]
        prev3 = expense_series[-6:-3] if len(expense_series) >= 6 else expense_series[:-3]
        if prev3:
            avg_last3 = sum(last3) / len(last3)
            avg_prev3 = sum(prev3) / len(prev3)
            delta = avg_last3 - avg_prev3
            if delta > 0:
                severity = "high" if avg_prev3 and delta / avg_prev3 > 0.2 else "warning"
                insights.append(
                    DashboardInsightItem(
                        kind="lifestyle_creep",
                        title="Lifestyle Creep Signal",
                        detail=f"Average monthly expenses are up ${delta:.2f} versus the previous period.",
                        severity=severity,
                    )
                )

    current_categories = monthly_expense_by_category.get(current_month, {})
    spike_extras: list[tuple[str, float]] = []
    for category, current_total in current_categories.items():
        prior_vals = [
            monthly_expense_by_category[m].get(category, 0.0)
            for m in months_sorted
            if m < current_month
        ][-6:]
        if len(prior_vals) < 2:
            continue
        med = float(median(prior_vals))
        if med > 0 and current_total > med * 1.4:
            extra = current_total - med
            spike_extras.append((category, extra))
            insights.append(
                DashboardInsightItem(
                    kind="category_spike",
                    title=f"{category} Spike",
                    detail=f"{category} spend is ${current_total:.2f} vs median ${med:.2f} (last 6 months).",
                    severity="warning" if current_total <= med * 2 else "high",
                )
            )

    if spike_extras:
        extra_total = sum(extra for _, extra in spike_extras)
        opportunity_cost = extra_total * 12 * 0.06
        insights.append(
            DashboardInsightItem(
                kind="opportunity_cost",
                title="Opportunity Cost of Current Spikes",
                detail=(
                    f"Current category spikes total ${extra_total:.2f}; redirecting that yearly could add "
                    f"about ${opportunity_cost:.2f} at 6%."
                ),
                severity=_severity_for_ratio((extra_total / expense_total) if expense_total else 0.0),
            )
        )

    if not insights and expense_total > 0:
        insights.append(
            DashboardInsightItem(
                kind="spend_velocity",
                title="Stable Spending Pattern",
                detail="No major spike or risk signals detected this month from current rules.",
                severity="info",
            )
        )

    return insights[:8]
