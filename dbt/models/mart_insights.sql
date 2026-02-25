with category_monthly as (
    select * from {{ ref('mart_category_monthly') }}
),
monthly_summary as (
    select * from {{ ref('mart_monthly_summary') }}
),
latest_month as (
    select user_id, max(month_start) as month_start
    from monthly_summary
    group by 1
),
latest_categories as (
    select c.*
    from category_monthly c
    join latest_month lm
      on lm.user_id = c.user_id
     and lm.month_start = c.month_start
),
category_history as (
    select
        c.user_id,
        c.category,
        c.month_start,
        c.expense_total,
        row_number() over (partition by c.user_id, c.category order by c.month_start desc) as rn
    from category_monthly c
),
category_medians as (
    select
        user_id,
        category,
        percentile_cont(0.5) within group (order by expense_total) as median_last_6
    from category_history
    where rn <= 6
    group by 1,2
)
select
    lc.user_id,
    lc.month_start,
    lc.category,
    lc.expense_total as current_expense,
    cm.median_last_6,
    case
        when cm.median_last_6 > 0 and lc.expense_total > cm.median_last_6 * 1.4 then true
        else false
    end as category_spike
from latest_categories lc
left join category_medians cm
  on cm.user_id = lc.user_id
 and cm.category = lc.category
where lc.expense_total > 0
