with base as (
    select * from {{ ref('stg_transactions') }}
),
monthly as (
    select
        user_id,
        date_trunc('month', txn_date)::date as month_start,
        sum(case when amount > 0 and not is_movement then amount else 0 end) as income_total,
        sum(case when amount < 0 and not is_movement then abs(amount) else 0 end) as expense_total,
        sum(case when is_movement then abs(amount) else 0 end) as movement_total,
        count(*) as txn_count,
        sum(case when category = 'Unknown' then 1 else 0 end) as unknown_count
    from base
    group by 1, 2
)
select
    user_id,
    month_start,
    income_total,
    expense_total,
    income_total - expense_total as net,
    case when income_total > 0 then (income_total - expense_total) / income_total else null end as savings_rate,
    movement_total,
    txn_count,
    unknown_count,
    case when txn_count > 0 then (unknown_count::float / txn_count) * 100 else 0 end as unknown_percent
from monthly
