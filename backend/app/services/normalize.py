import re

PUNCT_RE = re.compile(r"[^A-Z0-9\s]")
MULTISPACE_RE = re.compile(r"\s+")
VALUE_DATE_RE = re.compile(r"VALUE\s+DATE[:\s]+\d{2}/\d{2}/\d{4}", re.IGNORECASE)
CARD_DETAIL_RE = re.compile(r"CARD\s+XX(?:\d{4}|####)", re.IGNORECASE)
LONG_REF_RE = re.compile(r"\b(?:[A-F0-9]{10,}|[0-9]{8,})\b")
TRAILING_COUNTRY_RE = re.compile(r"(\s+(AUS|AU|USA|GBR|NSW|VIC|QLD|TAS|SA|WA|NT|ACT|NS|TA))+$", re.IGNORECASE)

STRIP_PATTERNS = [
    CARD_DETAIL_RE,
    VALUE_DATE_RE,
]

PREFIX_PATTERNS = [
    re.compile(r"^PAYPAL\s*\*\s*", re.IGNORECASE),
    re.compile(r"^SQ\s*\*\s*", re.IGNORECASE),
    re.compile(r"^VISA\s+PURCHASE\s*", re.IGNORECASE),
    re.compile(r"^DIRECT\s+DEBIT\s*", re.IGNORECASE),
]

CARD_MASK_RE = CARD_DETAIL_RE


def mask_card_references(description: str) -> str:
    return CARD_MASK_RE.sub("CARD XX####", description)


def normalize_merchant(description: str) -> str:
    text = description.upper()
    text = VALUE_DATE_RE.sub(" ", text)
    text = CARD_DETAIL_RE.sub(" ", text)
    text = PUNCT_RE.sub(" ", text)
    for pattern in PREFIX_PATTERNS:
        text = pattern.sub("", text)
    text = LONG_REF_RE.sub(" ", text)
    text = TRAILING_COUNTRY_RE.sub("", text)
    # Drop trailing standalone numbers/currency fragments commonly left by card descriptors.
    tokens = [t for t in MULTISPACE_RE.sub(" ", text).strip().split(" ") if t]
    while tokens and (
        tokens[-1].isdigit()
        or tokens[-1] in {"USD", "AUD"}
        or (len(tokens[-1]) <= 3 and tokens[-1].isalpha() and tokens[-1] in {"AU", "AUS", "USA", "GBR"})
    ):
        tokens.pop()
    text = " ".join(tokens)
    text = MULTISPACE_RE.sub(" ", text).strip()
    return text or "UNKNOWN"
