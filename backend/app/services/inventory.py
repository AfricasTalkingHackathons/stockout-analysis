from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import utcnow
from app.models import (
    Alert,
    Facility,
    InventoryItem,
    Medicine,
    MovementType,
    StockMovement,
    User,
    VerificationStatus,
)
from app.services.alerts import evaluate_inventory
from app.services.audit import audit


class DomainError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "invalid_request") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


@dataclass
class MovementOutcome:
    movement: StockMovement
    item: InventoryItem
    duplicate: bool = False
    alerts: list[Alert] = field(default_factory=list)


def create_inventory(
    db: Session,
    facility: Facility,
    medicine: Medicine,
    quantity: int,
    min_threshold: int,
    user: User | None,
    unit: str | None = None,
    batch_number: str | None = None,
    expiry_date: date | None = None,
    internal_notes: str | None = None,
    source: str = "web",
) -> MovementOutcome:
    if quantity < 0 or min_threshold < 0:
        raise DomainError("Quantities cannot be negative")
    if unit and unit != medicine.base_unit:
        raise DomainError(
            f"Unit must be the catalog base unit '{medicine.base_unit}' for {medicine.display_name}. "
            "Convert pack sizes to base units before recording.", code="unit_mismatch")
    if not medicine.is_active:
        raise DomainError("Medicine is not active in the catalog")
    exists = db.query(InventoryItem).filter_by(facility_id=facility.id, medicine_id=medicine.id).one_or_none()
    if exists:
        raise DomainError("This medicine already has an inventory record at this facility", 409, "duplicate")
    now = utcnow()
    item = InventoryItem(
        facility_id=facility.id, medicine_id=medicine.id, quantity=quantity, unit=medicine.base_unit,
        min_threshold=min_threshold, batch_number=batch_number, expiry_date=expiry_date,
        internal_notes=internal_notes, last_updated_at=now, last_updated_by_id=user.id if user else None,
        verification_status=VerificationStatus.VERIFIED,
    )
    item.facility, item.medicine = facility, medicine
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise DomainError("This medicine already has an inventory record at this facility", 409, "duplicate") from exc
    mv = StockMovement(inventory_id=item.id, movement_type=MovementType.INITIAL, quantity_delta=quantity,
                       quantity_before=0, quantity_after=quantity, reason="Initial stock record", source=source,
                       performed_by_id=user.id if user else None, created_at=now)
    db.add(mv)
    audit(db, "inventory.create", "inventory", item.id, actor=user, facility_id=facility.id,
          details={"medicine": medicine.code, "quantity": quantity, "min_threshold": min_threshold})
    alerts = evaluate_inventory(db, item, previous_quantity=None)
    return MovementOutcome(mv, item, alerts=alerts)


def record_movement(
    db: Session,
    item: InventoryItem,
    movement_type: str,
    quantity: int,
    user: User | None,
    reason: str | None = None,
    idempotency_key: str | None = None,
    expected_version: int | None = None,
    source: str = "web",
    actor_label: str | None = None,
) -> MovementOutcome:
    if idempotency_key:
        prior = db.query(StockMovement).filter_by(idempotency_key=idempotency_key).one_or_none()
        if prior:
            if prior.inventory_id != item.id:
                raise DomainError("Idempotency key already used for another record", 409, "idempotency_conflict")
            return MovementOutcome(prior, item, duplicate=True)

    if expected_version is not None and expected_version != item.version:
        raise DomainError("This record was changed by someone else. Reload and try again.", 409, "version_conflict")

    try:
        mt = MovementType(movement_type)
    except ValueError as exc:
        raise DomainError(f"Unknown movement type '{movement_type}'") from exc
    if mt == MovementType.INITIAL:
        raise DomainError("Initial movements are created automatically")

    before = item.quantity
    if mt == MovementType.RECEIPT:
        if quantity <= 0:
            raise DomainError("Received quantity must be greater than zero")
        after = before + quantity
    elif mt == MovementType.DISPENSE:
        if quantity <= 0:
            raise DomainError("Dispensed quantity must be greater than zero")
        if quantity > before:
            raise DomainError(f"Cannot dispense {quantity}; only {before} {item.unit} recorded", code="insufficient_stock")
        after = before - quantity
    elif mt == MovementType.ADJUSTMENT:
        if quantity == 0:
            raise DomainError("Adjustment cannot be zero")
        if not reason:
            raise DomainError("A reason is required for adjustments")
        after = before + quantity
        if after < 0:
            raise DomainError("Adjustment would make stock negative", code="negative_stock")
    else:  # COUNT
        if quantity < 0:
            raise DomainError("Counted quantity cannot be negative", code="negative_stock")
        after = quantity

    now = utcnow()
    item.quantity = after
    item.last_updated_at = now
    item.last_updated_by_id = user.id if user else None
    item.verification_status = VerificationStatus.VERIFIED
    mv = StockMovement(inventory_id=item.id, movement_type=mt, quantity_delta=after - before, quantity_before=before,
                       quantity_after=after, reason=reason, source=source, idempotency_key=idempotency_key,
                       performed_by_id=user.id if user else None, created_at=now)
    db.add(mv)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise DomainError("Duplicate stock movement", 409, "duplicate") from exc
    audit(db, f"inventory.{mt.value}", "inventory", item.id, actor=user, actor_label=actor_label,
          facility_id=item.facility_id,
          details={"medicine": item.medicine.code, "before": before, "after": after, "source": source,
                   "reason": reason})
    alerts = evaluate_inventory(db, item, previous_quantity=before)
    return MovementOutcome(mv, item, alerts=alerts)


def lock_inventory(db: Session, inventory_id: str) -> InventoryItem | None:
    """Row lock on PostgreSQL (SELECT ... FOR UPDATE); SQLite serialises writers itself."""
    return db.query(InventoryItem).filter(InventoryItem.id == inventory_id).with_for_update().one_or_none()
