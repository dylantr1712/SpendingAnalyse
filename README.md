# SpendingAnalyse

Spending Leak Detector: a local-first, deterministic personal finance analytics platform. It ingests bank CSV exports, normalizes merchant data, separates movement from spending, and produces explainable monthly analytics, review queues, and savings goal feasibility.

## Purpose
This project is built to answer the question: "Where is my money going each month, and what patterns are quietly eroding my savings?" It emphasizes:
- Deterministic results (same input -> same output).
- Privacy and local control (no external APIs, no cloud services).
- Explainable analytics (no opaque ML decisions).

## Non-Goals
- Not a banking app.
- Not an AI budgeting assistant.
- No online merchant lookups or third-party APIs.
- No automatic ML-based categorization (future optional phase only).

## Scope
The current scope includes:
- CSV ingestion for CommBank exports (supports headerless exports).
- Deterministic merchant normalization and categorization rules.
- Movement detection to separate transfers from consumption.
- Review queue for unknown merchants, large movements, and high-impact spend.
- Monthly analytics and insights (dashboard, trends, category spikes, lifestyle creep).
- Goals engine with feasibility and encouragement output.
- Local username/password auth with HTTP Basic.
- Streamlit UI for upload, review, dashboard, transactions, and goals.
- dbt models for analytics marts (optional, with ORM fallback).

## Architecture Overview
Services (Docker Compose):
- `db`: Postgres 16
- `backend`: FastAPI API (Python 3.11)
- `streamlit`: Streamlit UI

Data flow:
1. CSV upload -> FastAPI `/import`
2. Ingestion -> `raw_transactions` + normalized `fct_transactions`
3. Optional dbt runs -> analytics marts
4. API serves analytics -> Streamlit UI

## Core Implementation Details
### Merchant Normalization
Implemented in `backend/app/services/normalize.py`:
- Uppercase, strip punctuation, collapse whitespace.
- Remove card references, "VALUE DATE", prefixes like `PAYPAL *`, `SQ *`, `VISA PURCHASE`, `DIRECT DEBIT`.
- Strip long reference numbers and trailing location suffixes.
- Result stored as `merchant_key`.

### Movement Detection
- Keyword-based rules (`FAST TRANSFER`, `TRANSFER TO/FROM`, `PAYID`, `OSKO`, `CASH DEPOSIT`, `ATM`).
- Movement is excluded from spending by default and tracked separately.

### Deterministic Categorization
- Rule-based patterns in `backend/app/services/ingest.py`.
- Merchant mappings stored in `merchant_map` override rules.
- Category dictionary includes essentials, lifestyle, financial, and other buckets.

### Review Queue Rules
- Unknown merchants.
- Movements >= 500.
- High-impact discretionary spend (amount >= 100).

### Insights Engine
- Spend velocity (first 7 days).
- Unknown category drag.
- Subscription burden.
- Lifestyle creep (last 3 vs previous 3 months).
- Category spikes (current vs 6-month median).
- Opportunity cost estimate.

### Goals Engine
- Calculates required monthly savings, historical median net savings, feasibility ratio, and status.
- Generates encouragement message based on feasibility.

## Data Model (Core Tables)
Defined in `backend/app/models.py`:
- `users`
- `import_batches`
- `raw_transactions`
- `fct_transactions`
- `merchant_map`
- `user_profile`
- `goals`

## dbt Models
Located in `dbt/models`:
- `stg_transactions`: base staging from `fct_transactions`
- `mart_monthly_summary`: monthly income/expense/net/savings rate
- `mart_category_monthly`: monthly totals by category
- `mart_review_queue`: rule-based review reasons
- `mart_goal_evaluation`: goal feasibility calculations
- `mart_insights`: category spike detection

The backend can use dbt marts when available, with fallback to ORM-based analytics.

## API Endpoints (FastAPI)
Base routes are defined in `backend/app/api/api.py`:
- `POST /import`
- `GET /dashboard`
- `GET /dashboard/trends`
- `GET /review-queue`
- `POST /merchant-map`
- `GET /transaction`
- `GET /transaction/months`
- `POST /transaction/bulk`
- `POST /transaction/{transaction_id}`
- `POST /goals`
- `GET /auth/status`
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/setup`
- `GET /auth/me`
- `GET /profile/balances`
- `POST /profile/balances`
- `POST /profile/reset`
- `GET /health`

## Frontend (Streamlit)
Defined in `frontend/streamlit_app.py` with tabs:
- Upload: CSV ingestion
- Review Queue: merchant mapping and review items
- Dashboard: monthly KPIs, trends, balances, insights
- Transactions: filters, bulk actions, single edits
- Goals: savings target and feasibility

## Running Locally
Start everything with Docker Compose:
```bash
docker compose up --build
```

Service ports:
- Backend API: `http://localhost:8000`
- Streamlit UI: `http://localhost:8501`
- Postgres: `localhost:5432`

## Configuration
Environment variables:
- `DATABASE_URL` (backend, in docker-compose)
- `API_BASE` (streamlit, defaults to `http://backend:8000`)
- `DASHBOARD_ANALYTICS_SOURCE` (backend: `auto` or `dbt`)

## Tests
Current coverage in `tests/`:
- CSV ingestion and headerless CommBank support
- Local auth flows
- Dashboard insights
- Review queue + goals flow
- Startup smoke tests

## Roadmap (Condensed)
See `Roadmap.md` for full phase breakdown. Current work includes:
- dbt marts and validation
- UI polish and expanded test coverage
- Optional future ML-assisted suggestions (never auto-applied)
