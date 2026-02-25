with monthly as (
    select * from {{ ref('mart_monthly_summary') }}
),
latest_six as (
    select
        user_id,
        net,
        row_number() over (partition by user_id order by month_start desc) as rn
    from monthly
),
historical as (
    select
        user_id,
        percentile_cont(0.5) within group (order by net) as historical_saving
    from latest_six
    where rn <= 6
    group by 1
),
inputs as (
    select
        g.user_id,
        coalesce(up.reported_total_savings, 0) as reported_total_savings,
        g.goal_amount,
        g.target_date
    from goals g
    left join user_profile up on up.user_id = g.user_id
),
calc as (
    select
        i.*,
        greatest(
            ((date_part('year', age(i.target_date, current_date)) * 12)
            + date_part('month', age(i.target_date, current_date)))::int,
            0
        ) as months_remaining,
        greatest(i.goal_amount - i.reported_total_savings, 0) as remaining_amount
    from inputs i
)
select
    c.user_id,
    c.reported_total_savings,
    c.goal_amount,
    c.target_date,
    c.months_remaining,
    case when c.months_remaining > 0 then c.remaining_amount / c.months_remaining else null end as required_monthly,
    h.historical_saving,
    case
        when c.months_remaining > 0
         and c.remaining_amount > 0
         and h.historical_saving is not null
            then h.historical_saving / (c.remaining_amount / c.months_remaining)
        else null
    end as feasibility_ratio
from calc c
left join historical h on h.user_id = c.user_id
