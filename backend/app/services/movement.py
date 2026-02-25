MOVEMENT_KEYWORDS = [
    "FAST TRANSFER",
    "TRANSFER TO",
    "TRANSFER FROM",
    "PAYID",
    "OSKO",
    "CASH DEPOSIT",
    "ATM",
]


def is_movement(description: str) -> bool:
    text = description.upper()
    return any(keyword in text for keyword in MOVEMENT_KEYWORDS)
