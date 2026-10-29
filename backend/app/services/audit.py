from sqlalchemy.orm import Session

from app.models import AuditLog, User


def audit(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    actor: User | None = None,
    actor_label: str | None = None,
    facility_id: str | None = None,
    details: dict | None = None,
    ip: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_label=actor_label or (actor.email if actor else "system"),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        facility_id=facility_id,
        details=details or {},
        ip_address=ip,
    )
    db.add(entry)
    return entry
