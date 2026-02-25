import os
from datetime import date
import pandas as pd
import requests
import streamlit as st
from requests.auth import HTTPBasicAuth

API_BASE = os.getenv("API_BASE", "http://backend:8000")

st.set_page_config(page_title="Spending Leak Detector", layout="wide")

st.title("Spending Leak Detector")

DEFAULT_CATEGORIES = [
    "Housing",
    "Utilities",
    "Groceries",
    "Transport",
    "Health",
    "Eating Out",
    "Food Delivery",
    "Shopping",
    "Entertainment",
    "Subscriptions",
    "Movement",
    "Savings",
    "Investments",
    "Lending",
    "Unknown",
    "Other",
]


def api_get(path: str):
    return requests.get(f"{API_BASE}{path}", timeout=30, auth=_get_auth())


def api_post(path: str, **kwargs):
    return requests.post(f"{API_BASE}{path}", timeout=30, auth=_get_auth(), **kwargs)


def _get_auth():
    username = st.session_state.get("auth_username")
    password = st.session_state.get("auth_password")
    if username and password:
        return HTTPBasicAuth(username, password)
    return None


def _raw_get(path: str):
    return requests.get(f"{API_BASE}{path}", timeout=30)


def _raw_post(path: str, **kwargs):
    return requests.post(f"{API_BASE}{path}", timeout=30, **kwargs)


def _merchant_category_options():
    return ["All", "Unknown", "Movement"] + [c for c in DEFAULT_CATEGORIES if c != "Unknown"]


def _escape_markdown_currency(text: str) -> str:
    return text.replace("$", "\\$")


st.sidebar.header("Local Login")

auth_status_resp = _raw_get("/auth/status")
if not auth_status_resp.ok:
    st.sidebar.error("Auth status unavailable")
    st.stop()

auth_status = auth_status_resp.json()
configured = auth_status["configured"]

if not configured:
    st.sidebar.info("First run: register a local username/password.")
    with st.sidebar.form("register_form"):
        setup_user = st.text_input("Username")
        setup_pass = st.text_input("Password", type="password")
        setup_submit = st.form_submit_button("Register")
    if setup_submit:
        resp = _raw_post("/auth/register", json={"username": setup_user, "password": setup_pass})
        if resp.ok:
            st.session_state["auth_username"] = setup_user
            st.session_state["auth_password"] = setup_pass
            st.sidebar.success("Local account registered.")
            st.rerun()
        else:
            st.sidebar.error(resp.text)
    st.stop()

if st.session_state.get("auth_username") and st.session_state.get("auth_password"):
    me = api_get("/auth/me")
    if me.ok:
        st.sidebar.success(f"Logged in as {me.json().get('username')}")
        if st.sidebar.button("Logout"):
            st.session_state.pop("auth_username", None)
            st.session_state.pop("auth_password", None)
            st.rerun()
    else:
        st.session_state.pop("auth_username", None)
        st.session_state.pop("auth_password", None)
        st.sidebar.warning("Session credentials invalid. Please login again.")

if not (st.session_state.get("auth_username") and st.session_state.get("auth_password")):
    with st.sidebar.form("login_form"):
        login_user = st.text_input("Username", key="login_user")
        login_pass = st.text_input("Password", type="password", key="login_pass")
        login_submit = st.form_submit_button("Login")
    if login_submit:
        resp = _raw_post("/auth/login", json={"username": login_user, "password": login_pass})
        if resp.ok:
            st.session_state["auth_username"] = login_user
            st.session_state["auth_password"] = login_pass
            st.rerun()
        else:
            st.sidebar.error("Invalid credentials")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.subheader("Data Reset")
confirm_reset = st.sidebar.checkbox(
    "I understand this deletes all imported data (keeps merchant mappings).",
    value=False,
    key="confirm_data_reset",
)
if st.sidebar.button("Reset Data", disabled=not confirm_reset, key="reset_data_btn"):
    reset_resp = api_post("/profile/reset")
    if reset_resp.ok:
        st.sidebar.success("Data reset completed.")
        st.rerun()
    else:
        st.sidebar.error(reset_resp.text)


tab_upload, tab_review, tab_dashboard, tab_transactions, tab_goals = st.tabs(
    ["Upload", "Review Queue", "Dashboard", "Transactions", "Goals"]
)

with tab_upload:
    st.header("Upload CSV")
    file = st.file_uploader("CommBank CSV", type=["csv"])
    if file and st.button("Import", key="import_btn"):
        files = {"file": (file.name, file.getvalue(), "text/csv")}
        resp = api_post("/import", files=files)
        if resp.ok:
            st.success(f"Imported {resp.json()['imported_rows']} rows")
        else:
            st.error(resp.text)

with tab_review:
    st.header("Review Queue")
    resp = api_get("/review-queue")
    if not resp.ok:
        st.error(resp.text)
    else:
        data = resp.json()

        st.subheader("Category Review")
        review_rows = data.get("category_review_merchants", [])
        filter_cols = st.columns([2, 2, 1])
        review_filter = filter_cols[0].selectbox(
            "Category / Type",
            _merchant_category_options(),
            key="review_category_filter",
            help="Filter merchants by assigned category or show movement merchants.",
        )
        review_search = filter_cols[1].text_input(
            "Search merchant",
            value=st.session_state.get("review_search", ""),
            key="review_search",
        ).strip()
        only_partially_reviewed = filter_cols[2].checkbox(
            "Needs Review",
            value=st.session_state.get("review_needs_review", False),
            key="review_needs_review",
            help="Show merchants with at least one unreviewed transaction in the grouped summary.",
        )

        filtered_review_rows = []
        for item in review_rows:
            if review_filter == "Unknown" and item["category"] != "Unknown":
                continue
            if review_filter == "Movement" and not item["is_movement"]:
                continue
            if review_filter not in {"All", "Unknown", "Movement"} and item["category"] != review_filter:
                continue
            if review_search and review_search.upper() not in item["merchant_key"].upper():
                continue
            if only_partially_reviewed and item["user_confirmed_count"] >= item["txn_count"]:
                continue
            filtered_review_rows.append(item)

        if not filtered_review_rows:
            st.caption("No merchants match the current category review filters.")
        for item in filtered_review_rows:
            with st.expander(
                f"{item['merchant_key']} | {item['category']} | {item['txn_count']} txns"
            ):
                st.write(item["sample_description"])
                st.write(
                    "Latest: "
                    f"{item['latest_txn_date']} | "
                    f"Total amount: {item['total_amount']:.2f} | "
                    f"Reviewed: {item['user_confirmed_count']}/{item['txn_count']}"
                )
                category = st.selectbox(
                    "Set merchant category",
                    DEFAULT_CATEGORIES,
                    index=DEFAULT_CATEGORIES.index(item["category"])
                    if item["category"] in DEFAULT_CATEGORIES
                    else DEFAULT_CATEGORIES.index("Other"),
                    key=f"merchant_cat_{item['merchant_key']}",
                )
                apply_existing = st.checkbox(
                    "Apply to existing transactions",
                    value=True,
                    key=f"merchant_apply_existing_{item['merchant_key']}",
                    help="Also update all past transactions for this merchant and refresh dashboard/insights.",
                )
                if st.button("Save Merchant Mapping", key=f"save_map_{item['merchant_key']}"):
                    save_resp = api_post(
                        "/merchant-map",
                        json={
                            "merchant_key": item["merchant_key"],
                            "category": category,
                            "apply_to_existing": apply_existing,
                        },
                    )
                    if save_resp.ok:
                        st.success(
                            f"Saved mapping and updated {save_resp.json()['updated_transactions']} transactions."
                        )
                        st.rerun()
                    else:
                        st.error(save_resp.text)

        st.subheader("Large Movements")
        if data["large_movements"]:
            st.dataframe(data["large_movements"], use_container_width=True)
        else:
            st.caption("No large movements.")

        st.subheader("High Impact Spend")
        if data["high_impact_spend"]:
            st.dataframe(data["high_impact_spend"], use_container_width=True)
        else:
            st.caption("No high-impact spend.")

with tab_dashboard:
    st.header("Dashboard")
    months_resp = api_get("/transaction/months")
    dashboard_months = months_resp.json().get("months", []) if months_resp.ok else []
    dash_month_options = ["Latest"] + dashboard_months
    current_dash_month = st.session_state.get("dashboard_month", "Latest")
    if current_dash_month not in dash_month_options:
        current_dash_month = "Latest"
    selected_dash_month = st.selectbox(
        "Select month",
        dash_month_options,
        index=dash_month_options.index(current_dash_month),
        key="dashboard_month_select",
        help="View a specific month (YYYY-MM) and compare it to the previous month.",
    )
    st.session_state["dashboard_month"] = selected_dash_month
    dashboard_path = "/dashboard"
    if selected_dash_month != "Latest":
        dashboard_path = f"/dashboard?month={selected_dash_month}"

    resp = api_get(dashboard_path)
    if resp.ok:
        data = resp.json()
        prev = data.get("previous_month_summary")
        expense_delta = None
        net_delta = None
        savings_rate_delta_pp = None
        if prev:
            expense_delta = data["expense_total"] - prev["expense_total"]
            net_delta = data["net"] - prev["net"]
            if data["savings_rate"] is not None and prev["savings_rate"] is not None:
                savings_rate_delta_pp = (data["savings_rate"] - prev["savings_rate"]) * 100
        cols = st.columns(4)
        cols[0].metric("Income", f"${data['income_total']:.2f}")
        cols[1].metric(
            "Expense",
            f"${data['expense_total']:.2f}",
            None if expense_delta is None else f"{expense_delta:+.2f} vs last month",
            delta_color="inverse",
        )
        cols[2].metric(
            "Net",
            f"${data['net']:.2f}",
            None if net_delta is None else f"{net_delta:+.2f} vs last month",
        )
        sr = data["savings_rate"]
        cols[3].metric(
            "Savings Rate",
            "-" if sr is None else f"{sr*100:.1f}%",
            None if savings_rate_delta_pp is None else f"{savings_rate_delta_pp:+.1f} pp",
        )
        st.write(f"Month: {data['month'] or '-'}")
        if prev:
            st.caption(
                f"Compared to {prev['month']}: Spending {expense_delta:+.2f}, Savings {net_delta:+.2f}"
            )
        else:
            st.caption("No previous month available for comparison.")
        st.write(f"Movement Total: ${data['movement_total']:.2f}")
        st.write(f"Unknown %: {data['unknown_percent']:.1f}%")

        c_left, c_right = st.columns(2)
        with c_left:
            st.subheader("Category Breakdown")
            if data.get("category_breakdown"):
                st.dataframe(data["category_breakdown"], use_container_width=True)
            else:
                st.caption("No expense categories yet.")
        with c_right:
            st.subheader("Top Merchants")
            if data.get("top_merchants"):
                st.dataframe(data["top_merchants"], use_container_width=True)
            else:
                st.caption("No merchant spend yet.")

        st.subheader("Balance Overrides")
        balances_resp = api_get("/profile/balances")
        balances_data = balances_resp.json() if balances_resp.ok else {}
        has_overrides = any(
            balances_data.get(k) is not None
            for k in ("bank_balance", "savings_balance", "investments_balance")
        )
        override_enabled = st.checkbox(
            "Use balance overrides (source of truth)",
            value=has_overrides,
            key="balance_override_enabled",
        )
        with st.form("balance_overrides_form"):
            b1, b2, b3 = st.columns(3)
            bank_default = balances_data.get("bank_balance")
            savings_default = balances_data.get("savings_balance")
            investments_default = balances_data.get("investments_balance")
            bank_balance = b1.number_input(
                "Bank balance",
                value=float(bank_default) if bank_default is not None else 0.0,
                disabled=not override_enabled,
                step=100.0,
                key="balance_bank",
            )
            savings_balance = b2.number_input(
                "Savings balance",
                value=float(savings_default) if savings_default is not None else 0.0,
                disabled=not override_enabled,
                step=100.0,
                key="balance_savings",
            )
            investments_balance = b3.number_input(
                "Investments balance",
                value=float(investments_default) if investments_default is not None else 0.0,
                disabled=not override_enabled,
                step=100.0,
                key="balance_investments",
            )
            as_of_default = balances_data.get("balances_as_of")
            as_of_date = st.date_input(
                "Balances as of",
                value=date.fromisoformat(as_of_default) if as_of_default else date.today(),
                disabled=not override_enabled,
                key="balance_as_of",
            )
            if st.form_submit_button("Save Balances"):
                if override_enabled:
                    payload = {
                        "bank_balance": bank_balance,
                        "savings_balance": savings_balance,
                        "investments_balance": investments_balance,
                        "balances_as_of": str(as_of_date),
                    }
                else:
                    payload = {
                        "bank_balance": None,
                        "savings_balance": None,
                        "investments_balance": None,
                        "balances_as_of": None,
                    }
                save_resp = api_post("/profile/balances", json=payload)
                if save_resp.ok:
                    st.success("Balances updated.")
                    st.rerun()
                else:
                    st.error(save_resp.text)

        st.subheader("Trends (Last 12 Months)")
        trends_resp = api_get("/dashboard/trends?months=12")
        if not trends_resp.ok:
            st.error("Trends unavailable")
        else:
            trends = trends_resp.json()
            points = trends.get("points", [])
            if not points:
                st.caption("No trend data available yet.")
            else:
                df = pd.DataFrame(points).set_index("month")
                kpis = trends.get("kpis", {})

                k1, k2, k3, k4 = st.columns(4)
                k1.metric(
                    "Bank Balance",
                    "-"
                    if kpis.get("current_account_balance") is None
                    else f"${kpis['current_account_balance']:.2f}",
                )
                k2.metric(
                    "Savings Balance",
                    "-"
                    if kpis.get("current_savings_balance") is None
                    else f"${kpis['current_savings_balance']:.2f}",
                )
                k3.metric(
                    "Investments Balance",
                    "-"
                    if kpis.get("current_investments_balance") is None
                    else f"${kpis['current_investments_balance']:.2f}",
                )
                k4.metric(
                    "Total Balance",
                    "-"
                    if kpis.get("current_total_balance") is None
                    else f"${kpis['current_total_balance']:.2f}",
                )

                k5, k6, k7, k8 = st.columns(4)
                k5.metric(
                    "12M Bank Change",
                    "-"
                    if kpis.get("account_balance_change_12m") is None
                    else f"${kpis['account_balance_change_12m']:+.2f}",
                )
                k6.metric(
                    "12M Total Change",
                    "-"
                    if kpis.get("total_balance_change_12m") is None
                    else f"${kpis['total_balance_change_12m']:+.2f}",
                )
                k7.metric("Avg Income", f"${kpis.get('avg_income', 0.0):.2f}")
                avg_sr = kpis.get("avg_savings_rate")
                k8.metric("Avg Savings Rate", "-" if avg_sr is None else f"{avg_sr*100:.1f}%")

                k9, k10 = st.columns(2)
                k9.metric("Avg Expense", f"${kpis.get('avg_expense', 0.0):.2f}")
                k10.metric("Avg Net", f"${kpis.get('avg_net', 0.0):.2f}")

                info_cols = st.columns(3)
                info_cols[0].caption(
                    "Best Savings Month: "
                    + (kpis.get("best_savings_month") or "-")
                    + (f" (${kpis.get('best_savings_value', 0.0):.2f})" if kpis.get("best_savings_month") else "")
                )
                info_cols[1].caption(
                    "Worst Spend Month: "
                    + (kpis.get("worst_spend_month") or "-")
                    + (f" (${kpis.get('worst_spend_value', 0.0):.2f})" if kpis.get("worst_spend_month") else "")
                )
                if kpis.get("last_month_net_change") is not None:
                    info_cols[2].caption(f"Last Month Net Change: {kpis['last_month_net_change']:+.2f}")
                else:
                    info_cols[2].caption("Last Month Net Change: -")

                st.subheader("Income vs Expense")
                st.line_chart(df[["income_total", "expense_total"]])

                st.subheader("Net Savings")
                st.bar_chart(df[["net"]])

                st.subheader("Savings Rate (%)")
                sr_df = df[["savings_rate"]].copy()
                sr_df["savings_rate"] = sr_df["savings_rate"] * 100
                st.line_chart(sr_df)

                st.subheader("Balances")
                st.line_chart(
                    df[
                        [
                            "account_balance_end",
                            "savings_balance_end",
                            "investments_balance_end",
                            "total_balance_end",
                        ]
                    ]
                )

                st.subheader("Movement vs Non-Movement Expense")
                st.bar_chart(df[["expense_total", "movement_total"]])

                category_trends = trends.get("category_trends", [])
                if category_trends:
                    cat_df = pd.DataFrame(
                        {item["category"]: item["monthly_totals"] for item in category_trends},
                        index=trends.get("months", []),
                    )
                    st.subheader("Top Category Trends")
                    st.line_chart(cat_df)
                else:
                    st.caption("No category trend data available.")

        st.subheader("Insights")
        insights = data.get("insights", [])
        if not insights:
            st.caption("No insights yet.")
        for insight in insights:
            prefix = {"info": "Info", "warning": "Warning", "high": "High"}.get(insight["severity"], "Info")
            st.markdown(f"**{prefix}: {insight['title']}**")
            st.markdown(_escape_markdown_currency(insight["detail"]))
    else:
        st.error("Dashboard unavailable")

with tab_transactions:
    st.header("Transactions")
    if "tx_presets" not in st.session_state:
        st.session_state["tx_presets"] = {}

    if "tx_use_range" not in st.session_state:
        st.session_state["tx_use_range"] = True

    r1, r2, r3 = st.columns([1, 1, 1])
    use_range = r1.checkbox("Filter by date range", value=st.session_state["tx_use_range"], key="tx_use_range")
    default_start = st.session_state.get("tx_start_date") or date.today().replace(day=1)
    default_end = st.session_state.get("tx_end_date") or date.today()
    if use_range:
        start_date = r2.date_input("Start date", value=default_start, key="tx_start_date")
        end_date = r3.date_input("End date", value=default_end, key="tx_end_date")
    else:
        start_date = None
        end_date = None

    p1, p2, p3 = st.columns([2, 2, 1])
    preset_name = p1.text_input("Preset name", value="", key="tx_preset_name")
    preset_choices = [""] + sorted(st.session_state["tx_presets"].keys())
    chosen_preset = p2.selectbox("Load preset", preset_choices, key="tx_preset_choice")
    if p3.button("Load", key="tx_preset_load", disabled=not chosen_preset):
        preset = st.session_state["tx_presets"][chosen_preset]
        for k, v in preset.items():
            st.session_state[k] = v
        st.rerun()
    sp1, sp2 = st.columns(2)
    if sp1.button("Save Current Preset", key="tx_preset_save", disabled=not preset_name.strip()):
        st.session_state["tx_presets"][preset_name.strip()] = {
            "tx_use_range": st.session_state.get("tx_use_range", True),
            "tx_start_date": st.session_state.get("tx_start_date"),
            "tx_end_date": st.session_state.get("tx_end_date"),
            "tx_category": st.session_state.get("tx_category", ""),
            "tx_search": st.session_state.get("tx_search", ""),
            "tx_only_unreviewed": st.session_state.get("tx_only_unreviewed", False),
            "tx_include_movements": st.session_state.get("tx_include_movements", True),
            "tx_limit": st.session_state.get("tx_limit", 50),
        }
        st.success(f"Saved preset '{preset_name.strip()}'.")
    if sp2.button("Delete Preset", key="tx_preset_delete", disabled=not chosen_preset):
        st.session_state["tx_presets"].pop(chosen_preset, None)
        st.success(f"Deleted preset '{chosen_preset}'.")
        st.rerun()

    if use_range and start_date and end_date and start_date > end_date:
        st.error("Start date must be on or before end date.")
        st.stop()

    f1, f2 = st.columns(2)
    category_filter = f1.selectbox("Category Filter", [""] + DEFAULT_CATEGORIES, key="tx_category")
    search_filter = f2.text_input(
        "Search merchant/description",
        value=st.session_state.get("tx_search", ""),
        key="tx_search",
    )

    g1, g2, g3 = st.columns(3)
    only_unreviewed = g1.checkbox("Only Unreviewed", value=False, key="tx_only_unreviewed")
    include_movements = g2.checkbox("Include Movements", value=True, key="tx_include_movements")
    limit = int(g3.selectbox("Rows", [25, 50, 100], index=1, key="tx_limit"))
    page = st.number_input("Page", min_value=1, value=1, step=1, key="tx_page")
    offset = (int(page) - 1) * limit

    params = {
        "limit": limit,
        "offset": offset,
        "only_unreviewed": str(only_unreviewed).lower(),
        "include_movements": str(include_movements).lower(),
    }
    if use_range and start_date:
        params["start_date"] = start_date.isoformat()
    if use_range and end_date:
        params["end_date"] = end_date.isoformat()
    if category_filter:
        params["category"] = category_filter
    if search_filter.strip():
        params["search"] = search_filter.strip()

    resp = api_get("/transaction?" + "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items()))
    if not resp.ok:
        st.error(resp.text)
    else:
        data = resp.json()
        st.caption(f"Showing {len(data['items'])} of {data['total']} transactions")
        if data["items"]:
            table_rows = [
                {
                    "id": tx["id"],
                    "date": tx["txn_date"],
                    "amount": tx["amount"],
                    "category": tx["category"],
                    "merchant": tx["merchant_key"],
                    "movement": tx["is_movement"],
                    "reviewed": tx["user_confirmed"],
                }
                for tx in data["items"]
            ]
            st.dataframe(table_rows, use_container_width=True)

            st.subheader("Bulk Actions (Current Page)")
            selectable_ids = [tx["id"] for tx in data["items"]]
            bulk_ids = st.multiselect(
                "Select transactions",
                options=selectable_ids,
                default=[],
                key="tx_bulk_ids",
            )
            b1, b2, b3 = st.columns(3)
            bulk_category = b1.selectbox("Bulk category", [""] + DEFAULT_CATEGORIES, key="tx_bulk_category")
            bulk_reviewed = b2.selectbox("Bulk reviewed", ["No change", "Mark reviewed", "Mark unreviewed"], key="tx_bulk_reviewed")
            if b3.button("Apply Bulk Update", key="tx_bulk_apply", disabled=not bulk_ids):
                payload = {"transaction_ids": bulk_ids}
                if bulk_category:
                    payload["category"] = bulk_category
                if bulk_reviewed == "Mark reviewed":
                    payload["user_confirmed"] = True
                elif bulk_reviewed == "Mark unreviewed":
                    payload["user_confirmed"] = False
                u = api_post("/transaction/bulk", json=payload)
                if u.ok:
                    st.success(f"Updated {u.json()['updated_count']} transactions.")
                    st.rerun()
                else:
                    st.error(u.text)

            st.subheader("Edit Transaction")
            selected_id = st.selectbox(
                "Select transaction",
                [tx["id"] for tx in data["items"]],
                format_func=lambda tx_id: f"#{tx_id}",
                key="tx_selected_id",
            )
            selected_tx = next(tx for tx in data["items"] if tx["id"] == selected_id)
            st.write(selected_tx["description_raw"])
            edit_col1, edit_col2 = st.columns(2)
            new_category = edit_col1.selectbox(
                "New category",
                DEFAULT_CATEGORIES,
                index=DEFAULT_CATEGORIES.index(selected_tx["category"])
                if selected_tx["category"] in DEFAULT_CATEGORIES
                else DEFAULT_CATEGORIES.index("Other"),
                key=f"tx_edit_category_{selected_id}",
            )
            new_reviewed = edit_col2.checkbox(
                "Reviewed",
                value=selected_tx["user_confirmed"],
                key=f"tx_edit_reviewed_{selected_id}",
            )

            btn1, btn2 = st.columns(2)
            save_as_merchant_default = st.checkbox(
                "Also save as default for this merchant (future imports + existing merchant transactions)",
                value=True,
                key=f"tx_save_default_{selected_id}",
                help=f"Future {selected_tx['merchant_key']} transactions will use this category until changed.",
            )
            if btn1.button("Save Category + Review", key=f"tx_save_both_{selected_id}"):
                u = api_post(
                    f"/transaction/{selected_id}",
                    json={"category": new_category, "user_confirmed": new_reviewed},
                )
                if u.ok:
                    if save_as_merchant_default:
                        map_resp = api_post(
                            "/merchant-map",
                            json={
                                "merchant_key": selected_tx["merchant_key"],
                                "category": new_category,
                                "apply_to_existing": True,
                            },
                        )
                        if map_resp.ok:
                            st.success(
                                "Transaction updated and merchant default saved "
                                f"({map_resp.json()['updated_transactions']} transactions updated)."
                            )
                            st.rerun()
                        else:
                            st.error(
                                "Transaction updated, but saving merchant default failed: "
                                f"{map_resp.text}"
                            )
                    else:
                        st.success("Transaction updated.")
                        st.rerun()
                else:
                    st.error(u.text)
            if btn2.button("Mark Reviewed Only", key=f"tx_mark_reviewed_{selected_id}"):
                u = api_post(f"/transaction/{selected_id}", json={"user_confirmed": True})
                if u.ok:
                    st.success("Transaction marked reviewed.")
                    st.rerun()
                else:
                    st.error(u.text)
        else:
            st.caption("No transactions match the current filters.")

with tab_goals:
    st.header("Goals")
    with st.form("goals_form"):
        reported_total_savings = st.number_input("Current total savings", min_value=0.0, step=100.0)
        goal_amount = st.number_input("Goal amount", min_value=0.0, step=100.0)
        target_date = st.date_input("Target date")
        submit = st.form_submit_button("Save Goals")

    if submit:
        resp = api_post(
            "/goals",
            json={
                "reported_total_savings": reported_total_savings,
                "goal_amount": goal_amount,
                "target_date": str(target_date),
            },
        )
        if not resp.ok:
            st.error(resp.text)
        else:
            g = resp.json()
            c1, c2, c3 = st.columns(3)
            c1.metric("Required Monthly", "-" if g["required_monthly"] is None else f"${g['required_monthly']:.2f}")
            c2.metric("Historical Saving", "-" if g["historical_saving"] is None else f"${g['historical_saving']:.2f}")
            c3.metric("Feasibility", g["feasibility_status"])
            st.write(f"Months remaining: {g['months_remaining']}")
            if g["feasibility_ratio"] is not None:
                st.write(f"Feasibility ratio: {g['feasibility_ratio']:.2f}")
            if g["projected_finish_months"] is not None:
                st.write(f"Projected finish in ~{g['projected_finish_months']} months at current pace")
            st.info(g["encouragement"])
