# core/events/text_utils.py
from __future__ import annotations

from typing import Any, Dict, Tuple

from utils.others import ordinal  # ✅ reuse your existing ordinal


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def parse_period_info(event: Dict[str, Any]) -> Tuple[str, int]:
    """
    Normalize period info from an NHL PBP event.
    Returns (period_type, period_number) where:
      period_type ∈ {"REG","OT","SO","UNK"}
      period_number: 1..N when present (4+ often means OT; 5 may be SO in some feeds)
    """
    pd = event.get("periodDescriptor") or {}
    ptype = (pd.get("periodType") or event.get("periodType") or "").upper()
    pnum = _to_int(pd.get("number", event.get("period", 0)), 0)

    if ptype in {"REG", "REGULAR"}:
        return "REG", pnum
    if ptype in {"OT", "OVERTIME"}:
        return "OT", pnum
    if ptype in {"SO", "SHOOTOUT"}:
        return "SO", pnum

    # Fallback: infer from number
    if pnum == 0:
        return "UNK", 0
    if 1 <= pnum <= 3:
        return "REG", pnum
    if pnum >= 4:
        # Many feeds mark OT as 4; sometimes SO comes in as 5 without type
        return "OT", pnum

    return "UNK", pnum


def period_label(event: Dict[str, Any], short: bool = False) -> str:
    """
    Human-friendly label for regular-season:
      short=False → "the 1st period", "overtime", "the shootout"
      short=True  → "1st", "OT", "SO"
    """
    ptype, pnum = parse_period_info(event)

    if ptype == "SO":
        return "SO" if short else "the shootout"
    if ptype == "OT":
        return "OT" if short else "overtime"
    if ptype == "REG":
        return ordinal(pnum) if short else f"the {ordinal(pnum)} period"

    # Unknown → reasonable fallback
    if pnum >= 4:
        return "OT" if short else "overtime"
    return ordinal(pnum) if short and pnum > 0 else ("period" if short else "the period")


def period_label_playoffs(event: Dict[str, Any], short: bool = False) -> str:
    """
    Playoff-aware label:
      short=True  → "1st", "2nd", "3rd", "OT", "2OT", "3OT", "SO"
      short=False → "the 1st period", "double overtime", "triple overtime", "the shootout"
    """
    ptype, pnum = parse_period_info(event)

    if ptype == "SO":
        return "SO" if short else "the shootout"

    if ptype == "OT":
        # 4 → OT (1st OT), 5 → 2OT, 6 → 3OT, etc.
        n = max(1, pnum - 3)
        if short:
            return "OT" if n == 1 else f"{n}OT"
        names = {2: "double", 3: "triple", 4: "quadruple"}
        prefix = names.get(n, f"{n}x")
        return "overtime" if n == 1 else f"{prefix} overtime"

    # REG
    return period_label(event, short=short)
