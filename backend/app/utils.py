import math
import re
import secrets
import string

_PHONE_RE = re.compile(r"^\+254(7|1)\d{8}$")


def normalize_ke_phone(raw: str | None) -> str | None:
    """Normalise Kenyan mobile numbers to E.164 (+2547XXXXXXXX / +2541XXXXXXXX)."""
    if not raw:
        return None
    digits = re.sub(r"[^\d+]", "", raw.strip())
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if digits.startswith("0") and len(digits) == 10:
        digits = "+254" + digits[1:]
    elif digits.startswith("254") and len(digits) == 12:
        digits = "+" + digits
    elif len(digits) == 9 and digits[0] in "71":
        digits = "+254" + digits
    return digits if _PHONE_RE.match(digits) else None


def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    if len(phone) <= 6:
        return "***"
    return phone[:4] + "*" * (len(phone) - 7) + phone[-3:]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def short_reference(prefix: str = "SR") -> str:
    alphabet = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"
    return f"{prefix}-" + "".join(secrets.choice(alphabet) for _ in range(6))
