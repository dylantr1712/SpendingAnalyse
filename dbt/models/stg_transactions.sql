select
  id,
  user_id,
  txn_date,
  amount,
  description_raw,
  merchant_key,
  category,
  is_income,
  is_movement,
  is_high_impact,
  txn_hash,
  user_confirmed
from fct_transactions
