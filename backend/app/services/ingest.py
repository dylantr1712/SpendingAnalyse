from io import BytesIO
from datetime import datetime
import re
from dataclasses import dataclass
from typing import Iterable

import pandas as pd
from dateutil import parser
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ImportBatch, RawTransaction, FctTransaction, MerchantMap
from app.services.normalize import normalize_merchant, mask_card_references
from app.services.movement import is_movement
from app.services.hash import transaction_hash

DISCRETIONARY = {
    "Eating Out",
    "Food Delivery",
    "Shopping",
    "Entertainment",
    "Subscriptions",
    "Other",
    "Unknown",
}

RULE_CATEGORY_PATTERNS: list[tuple[str, str]] = [
    # --- Transport ---
    (r"\bTRANSPORTFORNSW\s+OPAL\b", "Transport"),

    # --- Groceries ---
    (r"\bWOOLWORTHS\b", "Groceries"),

    # --- Utilities / Bills ---
    (r"\bSUPERLOOP\b", "Utilities"),
    (r"\bAUSSIE\s+BROADBAND\b", "Utilities"),
    (r"\bORIGIN\s+ENERGY\b", "Utilities"),
    (r"\bGLOBIRD\s+ENERGY\b", "Utilities"),
    (r"\bSYDNEY\s+WATER\b", "Utilities"),
    (r"\bFAIRFIELD\s+COUNCIL\b", "Utilities"),

    # --- Health ---
    (r"\bMEDIBANK\b", "Health"),
    (r"\bCHEMIST\s+WAREHOUSE\b", "Health"),
    (r"\bCHRIS\s+OBRIEN\s+LIFEHOUSE\b", "Health"),

    # --- Subscriptions ---
    (r"\bAMZNPRIMEAU\b|\bAMAZON\s+PRIME\b", "Subscriptions"),
    (r"\bNETFLIX\b", "Subscriptions"),
    (r"\bUBER\s+ONE\b", "Subscriptions"),
    (r"\bOPENAI\b|\bCHATGPT\b", "Subscriptions"),

    # --- Food Delivery / Eating out ---
    (r"\bUBER\s+EATS\b", "Food Delivery"),

    # --- Shopping / Retail ---
    # Amazon purchases (NOT Prime membership) -> Shopping
    (r"\bAMAZON\b.*\b(MARKETPLACE|MKTPLC|RETAIL)\b", "Shopping"),
    (r"\bBUNNINGS\b", "Shopping"),
    (r"\bALIEXPRESS\b", "Shopping"),
    (r"\bIKEA\b", "Shopping"),

    # --- Investments / Brokers ---
    (r"\bRAIZ\b", "Investments"),
    (r"\bSTAKE\b", "Investments"),
    (r"\bBETASHARES\b", "Investments"),
    (r"\bMOOMOO\b", "Investments"),
    (r"\bCOINSPOT\b", "Investments"),

    # --- Fees ---
    (r"\bINTERNATIONAL\s+TRANSACTION\s+FEE\b", "Other"),
]

_CATEGORY_REGEXES = [(re.compile(pat), category) for pat, category in RULE_CATEGORY_PATTERNS]


REQUIRED_COLUMNS = {"txn_date", "amount", "description"}
STANDARD_COLUMNS = ["txn_date", "amount", "description", "balance"]


@dataclass
class IngestResult:
    import_batch: ImportBatch
    total_rows: int
    imported_rows: int
    skipped_duplicates: int


def _parse_date(raw: str) -> datetime.date:
    return parser.parse(raw, dayfirst=True).date()


def _parse_amount(raw: str) -> float:
    return float(str(raw).replace(",", ""))


def _normalize_for_rules(text: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", text.upper())
    return re.sub(r"\s+", " ", cleaned).strip()


def _infer_category(description_raw: str, merchant_key: str, amount: float, movement: bool) -> str:
    if movement:
        return "Movement"
    normalized = _normalize_for_rules(f"{description_raw} {merchant_key}")
    for pattern, category in _CATEGORY_REGEXES:
        if pattern.search(normalized):
            return category
    text = normalized
    if any(k in text for k in ["WOOLWORTHS", "COLES", "ALDI"]):
        return "Groceries"
    if any(k in text for k in ["UBER EATS", "DOORDASH", "MENULOG"]):
        return "Food Delivery"
    if any(k in text for k in ["UBER TRIP", "TRANSPORTFORNSW", "OPAL", "METRO", "RELAY"]):
        return "Transport"
    if any(k in text for k in ["CHEMIST", "PHARMACY", "OPSM", "PRICELINE"]):
        return "Health"
    if any(k in text for k in ["SUPERLOOP", "ENERGY", "ORIGIN", "AGL", "GLOBIRD", "TELSTRA", "OPTUS"]):
        return "Utilities"
    if any(k in text for k in ["NETFLIX", "SPOTIFY", "AMZNPRIME", "PRIME", "OPENAI", "CHATGPT", "UBER ONE"]):
        return "Subscriptions"
    if any(k in text for k in ["STEAM", "CINEMA", "EVENT", "ESCAPE ROOM"]):
        return "Entertainment"
    if any(k in text for k in ["AMAZON", "BUNNINGS", "KMART", "TARGET", "APPLE"]):
        return "Shopping"
    if any(k in text for k in ["RAIZ", "STAKE"]):
        return "Investments"
    if amount > 0:
        return "Other"
    return "Unknown"


def _load_csv(file_bytes: bytes) -> pd.DataFrame:
    # First try the explicit-header format used by the app docs.
    df = pd.read_csv(BytesIO(file_bytes))
    normalized_columns = [str(c).strip() for c in df.columns]
    if REQUIRED_COLUMNS.issubset(set(normalized_columns)):
        return df.rename(columns={c: str(c).strip() for c in df.columns})

    # Commonwealth Bank exports are often headerless: date, amount, description, [balance]
    headerless = pd.read_csv(BytesIO(file_bytes), header=None)
    if headerless.shape[1] not in (3, 4):
        raise ValueError("CSV missing required columns")

    if headerless.shape[1] == 3:
        headerless.columns = STANDARD_COLUMNS[:3]
        headerless["balance"] = None
    else:
        headerless.columns = STANDARD_COLUMNS

    try:
        # Validate the first row looks like transaction data, not random content.
        first = headerless.iloc[0]
        _parse_date(str(first["txn_date"]))
        _parse_amount(str(first["amount"]))
    except Exception as exc:  # pragma: no cover - defensive validation
        raise ValueError("CSV missing required columns") from exc

    return headerless


def ingest_csv(db: Session, user_id: int, file_bytes: bytes) -> IngestResult:
    df = _load_csv(file_bytes)

    import_batch = ImportBatch(user_id=user_id, row_count=len(df))
    db.add(import_batch)
    db.flush()

    existing_map = {
        (m.merchant_key): m.category
        for m in db.query(MerchantMap).filter(MerchantMap.user_id == user_id).all()
    }

    raw_rows: list[RawTransaction] = []
    fct_candidates: list[FctTransaction] = []
    candidate_hashes: list[str] = []
    seen_hashes_in_file: set[str] = set()

    for _, row in df.iterrows():
        txn_date_raw = str(row["txn_date"])
        amount_raw = str(row["amount"])
        description_raw = mask_card_references(str(row["description"]))
        balance_raw = str(row.get("balance", "")) if "balance" in row else None

        raw_rows.append(
            RawTransaction(
                import_batch_id=import_batch.id,
                txn_date_raw=txn_date_raw,
                amount_raw=amount_raw,
                description_raw=description_raw,
                balance_raw=balance_raw,
            )
        )

        txn_date = _parse_date(txn_date_raw)
        amount = _parse_amount(amount_raw)
        merchant_key = normalize_merchant(description_raw)
        movement = is_movement(description_raw)
        category = existing_map.get(merchant_key)
        if category is None:
            category = _infer_category(description_raw, merchant_key, amount, movement)
        income = amount > 0 and not movement
        discretionary = category in DISCRETIONARY
        high_impact = abs(amount) >= 100 and discretionary

        tx_hash = transaction_hash(
            str(user_id),
            txn_date.isoformat(),
            f"{amount:.2f}",
            description_raw,
            balance_raw or "",
        )

        if tx_hash in seen_hashes_in_file:
            continue
        seen_hashes_in_file.add(tx_hash)
        candidate_hashes.append(tx_hash)
        fct_candidates.append(
            FctTransaction(
                user_id=user_id,
                txn_date=txn_date,
                amount=amount,
                description_raw=description_raw,
                merchant_key=merchant_key,
                category=category,
                is_income=income,
                is_movement=movement,
                is_high_impact=high_impact,
                txn_hash=tx_hash,
                user_confirmed=False,
            )
        )

    db.bulk_save_objects(raw_rows)
    existing_hashes = set()
    if candidate_hashes:
        existing_hash_rows = db.execute(
            select(FctTransaction.txn_hash).where(
                FctTransaction.user_id == user_id,
                FctTransaction.txn_hash.in_(candidate_hashes),
            )
        ).all()
        existing_hashes = {h for (h,) in existing_hash_rows}

    new_fct_rows = [row for row in fct_candidates if row.txn_hash not in existing_hashes]
    db.add_all(new_fct_rows)

    db.commit()
    db.refresh(import_batch)
    return IngestResult(
        import_batch=import_batch,
        total_rows=len(df),
        imported_rows=len(new_fct_rows),
        skipped_duplicates=len(df) - len(new_fct_rows),
    )
