"""Deterministic arithmetic, name-similarity, and date parsing helpers."""
from __future__ import annotations

import re
from datetime import date
from difflib import SequenceMatcher


def money(value: float | None) -> str:
    return "not available" if value is None else f"₹{value:,.2f}"


def name_similarity(first: str | None, second: str | None) -> float:
    if not first or not second:
        return 0.0

    def normalized(value: str) -> str:
        return re.sub(r"[^a-z]", "", value.lower())

    a, b = normalized(first), normalized(second)
    if not a or not b:
        return 0.0
    direct = SequenceMatcher(None, a, b).ratio()
    a_tokens = [token for token in re.findall(r"[a-z]+", first.lower()) if token]
    b_tokens = [token for token in re.findall(r"[a-z]+", second.lower()) if token]
    if not a_tokens or not b_tokens:
        return direct

    def compatible(left: str, right: str) -> bool:
        return left[0] == right[0] if len(left) == 1 or len(right) == 1 else left.startswith(right) or right.startswith(left)

    shorter, longer = (a_tokens, b_tokens) if len(a_tokens) <= len(b_tokens) else (b_tokens, a_tokens)
    matched = sum(any(compatible(token, other) for other in longer) for token in shorter)
    if matched == len(shorter):
        token_score = 0.95 if len(shorter) == len(longer) else 0.86
        return max(direct, token_score)
    return direct


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    candidate = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y"):
        try:
            return date.fromisoformat(candidate) if fmt == "%Y-%m-%d" else __import__("datetime").datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    return None
