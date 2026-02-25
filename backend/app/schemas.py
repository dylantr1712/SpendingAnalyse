from datetime import date
from pydantic import BaseModel, Field
from typing import Literal


class ImportResponse(BaseModel):
    import_batch_id: int
    imported_rows: int
    total_rows: int | None = None
    skipped_duplicates: int | None = None


class DashboardCategoryItem(BaseModel):
    category: str
    expense_total: float
    txn_count: int


class DashboardMerchantItem(BaseModel):
    merchant_key: str
    expense_total: float
    txn_count: int


class DashboardInsightItem(BaseModel):
    kind: Literal[
        "category_spike",
        "lifestyle_creep",
        "spend_velocity",
        "unknown_drag",
        "subscription_burden",
        "opportunity_cost",
    ]
    title: str
    detail: str
    severity: Literal["info", "warning", "high"]


class DashboardMonthSummary(BaseModel):
    month: str
    income_total: float
    expense_total: float
    net: float
    savings_rate: float | None
    movement_total: float
    unknown_percent: float


class DashboardResponse(BaseModel):
    month: str
    income_total: float
    expense_total: float
    net: float
    savings_rate: float | None
    movement_total: float
    unknown_percent: float
    previous_month_summary: DashboardMonthSummary | None = None
    category_breakdown: list[DashboardCategoryItem] = Field(default_factory=list)
    top_merchants: list[DashboardMerchantItem] = Field(default_factory=list)
    insights: list[DashboardInsightItem] = Field(default_factory=list)


class DashboardTrendPoint(BaseModel):
    month: str
    income_total: float
    expense_total: float
    net: float
    savings_rate: float | None
    movement_total: float
    unknown_percent: float
    savings_net: float
    investments_net: float
    account_balance_end: float | None
    savings_balance_end: float | None
    investments_balance_end: float | None
    total_balance_end: float | None


class DashboardCategoryTrend(BaseModel):
    category: str
    monthly_totals: list[float]


class DashboardKpis(BaseModel):
    avg_income: float
    avg_expense: float
    avg_net: float
    avg_savings_rate: float | None
    best_savings_month: str | None
    best_savings_value: float | None
    worst_spend_month: str | None
    worst_spend_value: float | None
    last_month_net_change: float | None
    current_account_balance: float | None
    current_savings_balance: float | None
    current_investments_balance: float | None
    current_total_balance: float | None
    account_balance_change_12m: float | None
    total_balance_change_12m: float | None


class DashboardTrendsResponse(BaseModel):
    months: list[str]
    points: list[DashboardTrendPoint]
    category_trends: list[DashboardCategoryTrend] = Field(default_factory=list)
    kpis: DashboardKpis


class BalanceProfileRequest(BaseModel):
    bank_balance: float | None = None
    savings_balance: float | None = None
    investments_balance: float | None = None
    balances_as_of: date | None = None


class BalanceProfileResponse(BaseModel):
    bank_balance: float | None = None
    savings_balance: float | None = None
    investments_balance: float | None = None
    balances_as_of: date | None = None


class ResetResponse(BaseModel):
    ok: bool


class ReviewQueueMerchantItem(BaseModel):
    merchant_key: str
    txn_count: int
    latest_txn_date: date
    sample_description: str
    total_amount: float


class CategoryReviewMerchantItem(BaseModel):
    merchant_key: str
    category: str
    txn_count: int
    latest_txn_date: date
    sample_description: str
    total_amount: float
    is_movement: bool
    user_confirmed_count: int


class ReviewQueueTransactionItem(BaseModel):
    id: int
    txn_date: date
    amount: float
    description_raw: str
    merchant_key: str
    category: str
    is_movement: bool
    is_high_impact: bool
    user_confirmed: bool


class ReviewQueueResponse(BaseModel):
    unknown_merchants: list[ReviewQueueMerchantItem]
    category_review_merchants: list[CategoryReviewMerchantItem] = Field(default_factory=list)
    large_movements: list[ReviewQueueTransactionItem]
    high_impact_spend: list[ReviewQueueTransactionItem]


class MerchantMapUpdateRequest(BaseModel):
    merchant_key: str
    category: str
    apply_to_existing: bool = True


class MerchantMapUpdateResponse(BaseModel):
    merchant_key: str
    category: str
    updated_transactions: int


class TransactionUpdateRequest(BaseModel):
    category: str | None = None
    user_confirmed: bool | None = None


class TransactionUpdateResponse(BaseModel):
    id: int
    category: str
    user_confirmed: bool


class TransactionListItem(BaseModel):
    id: int
    txn_date: date
    amount: float
    description_raw: str
    merchant_key: str
    category: str
    is_income: bool
    is_movement: bool
    is_high_impact: bool
    user_confirmed: bool


class TransactionListResponse(BaseModel):
    total: int
    items: list[TransactionListItem]


class TransactionMonthsResponse(BaseModel):
    months: list[str]


class TransactionBulkUpdateRequest(BaseModel):
    transaction_ids: list[int]
    category: str | None = None
    user_confirmed: bool | None = None


class TransactionBulkUpdateResponse(BaseModel):
    updated_count: int
    transaction_ids: list[int]


class GoalsRequest(BaseModel):
    reported_total_savings: float
    goal_amount: float
    target_date: date


class GoalsResponse(BaseModel):
    reported_total_savings: float
    goal_amount: float
    target_date: date
    months_remaining: int
    required_monthly: float | None
    historical_saving: float | None
    feasibility_ratio: float | None
    feasibility_status: Literal["Comfortable", "On track", "At risk", "Unrealistic", "Unknown"]
    projected_finish_months: int | None
    encouragement: str


class AuthStatusResponse(BaseModel):
    configured: bool
    username: str | None


class AuthSetupRequest(BaseModel):
    username: str
    password: str


class AuthRegisterRequest(BaseModel):
    username: str
    password: str


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class AuthLoginResponse(BaseModel):
    ok: bool
    username: str
