select
    user_id,
    date_trunc('month', txn_date)::date as month_start,
    category,
    sum(case when amount < 0 and not is_movement then abs(amount) else 0 end) as expense_total,
    sum(case when amount > 0 and not is_movement then amount else 0 end) as income_total,
    count(*) as txn_count
from {{ ref('stg_transactions') }}
group by 1, 2, 3
