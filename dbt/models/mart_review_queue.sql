with base as (
    select * from {{ ref('stg_transactions') }}
)
select
    id as transaction_id,
    user_id,
    txn_date,
    amount,
    description_raw,
    merchant_key,
    category,
    is_movement,
    is_high_impact,
    case
        when category = 'Unknown' then 'unknown_category'
        when is_movement and abs(amount) >= 500 then 'large_movement'
        when is_high_impact and amount < 0 then 'high_impact_spend'
        else null
    end as review_reason
from base
where
    category = 'Unknown'
    or (is_movement and abs(amount) >= 500)
    or (is_high_impact and amount < 0)
