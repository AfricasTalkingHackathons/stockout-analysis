"""Runtime-tunable rules stored in the system_config table, with documented defaults."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import SystemConfig


@dataclass(frozen=True)
class ConfigDef:
    default: float
    description: str
    minimum: float = 0
    maximum: float = 1_000_000


def _defaults() -> dict[str, ConfigDef]:
    s = get_settings()
    return {
        "fresh_hours": ConfigDef(s.fresh_hours, "Reports newer than this are treated as current", 1, 24 * 30),
        "unknown_after_days": ConfigDef(
            s.unknown_after_days, "Reports older than this are shown as Unknown instead of Stale", 1, 365
        ),
        "early_warning_days": ConfigDef(7, "Raise an early warning when estimated days of stock fall below this", 1, 90),
        "consumption_window_days": ConfigDef(30, "Look-back window for average daily consumption", 7, 180),
        "min_consumption_history_days": ConfigDef(
            7, "Minimum span of dispensing history required before estimating days remaining", 1, 90
        ),
        "min_consumption_events": ConfigDef(3, "Minimum dispensing records required for an estimate", 1, 100),
        "expiry_warning_days": ConfigDef(60, "Flag stock expiring within this many days", 1, 365),
        "ripple_window_hours": ConfigDef(72, "Time window for grouping reports into a ripple signal", 1, 24 * 14),
        "ripple_min_facilities": ConfigDef(3, "Distinct facilities required for a ripple signal", 2, 50),
        "ripple_min_score": ConfigDef(2.0, "Minimum weighted evidence score for a ripple signal", 0.5, 100),
        "ripple_unverified_weight": ConfigDef(0.3, "Weight of an unverified public report (0-1)", 0, 1),
        "ripple_low_stock_weight": ConfigDef(0.5, "Weight of a low-stock (not zero) signal (0-1)", 0, 1),
        "alert_notify_cooldown_minutes": ConfigDef(240, "Minimum gap between repeat notifications per alert", 1, 10080),
        "escalation_after_hours": ConfigDef(12, "Escalate unacknowledged critical alerts after this many hours", 1, 168),
        "subscriber_cooldown_hours": ConfigDef(24, "Minimum gap between availability SMS per subscription", 1, 720),
    }


CONFIG_DEFS = _defaults()


def get_config(db: Session) -> dict[str, float]:
    values = {k: d.default for k, d in CONFIG_DEFS.items()}
    for row in db.query(SystemConfig).all():
        if row.key in values:
            try:
                values[row.key] = float(row.value)
            except ValueError:
                pass
    return values


def set_config(db: Session, key: str, value: float, user_id: str | None) -> SystemConfig:
    d = CONFIG_DEFS.get(key)
    if d is None:
        raise KeyError(key)
    if not (d.minimum <= value <= d.maximum):
        raise ValueError(f"{key} must be between {d.minimum} and {d.maximum}")
    row = db.get(SystemConfig, key)
    if row is None:
        row = SystemConfig(key=key, description=d.description, value=str(value))
        db.add(row)
    row.value = str(value)
    row.updated_by_id = user_id
    return row
