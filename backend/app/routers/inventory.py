import csv
import io
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import StaleDataError

from app.database import get_db, utcnow
from app.deps import accessible_facility_ids, assert_facility_access, require
from app.models import Facility, InventoryItem, Medicine, StockMovement, User
from app.permissions import has_permission
from app.routers import PageQ, SizeQ, paginate
from app.schemas import InventoryIn, InventoryPatch, MovementIn
from app.serializers import alert_dict, inventory_dict, movement_dict
from app.services.alerts import estimate_days_remaining
from app.services.audit import audit
from app.services.inventory import DomainError, create_inventory, lock_inventory, record_movement
from app.services.notifications import dispatch_in_background
from app.services.runtime_config import get_config

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


def _scoped_query(db: Session, user: User):
    q = db.query(InventoryItem).join(Facility).join(Medicine).options(
        joinedload(InventoryItem.facility), joinedload(InventoryItem.medicine),
        joinedload(InventoryItem.last_updated_by))
    ids = accessible_facility_ids(db, user)
    if ids is not None:
        q = q.filter(InventoryItem.facility_id.in_(ids or ["-"]))
    return q


def _filtered(db, user, facility_id, medicine_id, county_id, status, q):
    query = _scoped_query(db, user)
    if facility_id:
        query = query.filter(InventoryItem.facility_id == facility_id)
    if medicine_id:
        query = query.filter(InventoryItem.medicine_id == medicine_id)
    if county_id:
        query = query.filter(Facility.county_id == county_id)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(or_(func.lower(Medicine.generic_name).like(like), func.lower(Medicine.code).like(like),
                                 func.lower(Medicine.brand_names).like(like)))
    if status == "out_of_stock":
        query = query.filter(InventoryItem.quantity == 0)
    elif status == "low":
        query = query.filter(InventoryItem.quantity > 0, InventoryItem.quantity <= InventoryItem.min_threshold)
    elif status == "available":
        query = query.filter(InventoryItem.quantity > InventoryItem.min_threshold)
    elif status == "stale":
        cutoff = utcnow() - timedelta(hours=get_config(db)["fresh_hours"])
        query = query.filter(InventoryItem.last_updated_at < cutoff)
    elif status == "expiring":
        horizon = utcnow().date() + timedelta(days=get_config(db)["expiry_warning_days"])
        query = query.filter(InventoryItem.expiry_date.isnot(None), InventoryItem.expiry_date <= horizon)
    return query.order_by(Facility.name, Medicine.generic_name)


StatusQ = Query(None, pattern="^(available|low|out_of_stock|stale|expiring)$")


@router.get("")
def list_inventory(facility_id: str | None = None, medicine_id: str | None = None, county_id: int | None = None,
                   status: str | None = StatusQ, q: str | None = Query(None, max_length=60),
                   page: int = PageQ, page_size: int = SizeQ,
                   user: User = Depends(require("inventory.view")), db: Session = Depends(get_db)):
    if facility_id:
        assert_facility_access(db, user, facility_id)
    return paginate(_filtered(db, user, facility_id, medicine_id, county_id, status, q), page, page_size,
                    inventory_dict)


@router.get("/export.csv")
def export_csv(facility_id: str | None = None, status: str | None = StatusQ,
               user: User = Depends(require("inventory.view")), db: Session = Depends(get_db)):
    if not (has_permission(user.role, "inventory.export") or has_permission(user.role, "facility.view_all")):
        raise HTTPException(403, "You do not have permission to export inventory")
    if facility_id:
        assert_facility_access(db, user, facility_id)
    rows = _filtered(db, user, facility_id, None, None, status, None).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["facility_code", "facility", "medicine_code", "medicine", "quantity", "unit", "min_threshold",
                "stock_status", "batch_number", "expiry_date", "last_updated_at_utc", "verification_status"])
    for i in rows:
        d = inventory_dict(i)
        w.writerow([i.facility.code, i.facility.name, i.medicine.code, i.medicine.display_name, i.quantity, i.unit,
                    i.min_threshold, d["stock_status"], i.batch_number or "", i.expiry_date or "",
                    i.last_updated_at.isoformat(), i.verification_status])
    audit(db, "inventory.export", "inventory", None, actor=user, facility_id=facility_id,
          details={"rows": len(rows)})
    db.commit()
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="inventory-{stamp}.csv"'})


@router.get("/movements")
def recent_movements(facility_id: str | None = None, medicine_id: str | None = None,
                     date_from: datetime | None = None, date_to: datetime | None = None,
                     page: int = PageQ, page_size: int = SizeQ,
                     user: User = Depends(require("inventory.view")), db: Session = Depends(get_db)):
    q = db.query(StockMovement).join(InventoryItem).options(
        joinedload(StockMovement.inventory).joinedload(InventoryItem.medicine),
        joinedload(StockMovement.inventory).joinedload(InventoryItem.facility),
        joinedload(StockMovement.performed_by))
    ids = accessible_facility_ids(db, user)
    if ids is not None:
        q = q.filter(InventoryItem.facility_id.in_(ids or ["-"]))
    if facility_id:
        assert_facility_access(db, user, facility_id)
        q = q.filter(InventoryItem.facility_id == facility_id)
    if medicine_id:
        q = q.filter(InventoryItem.medicine_id == medicine_id)
    if date_from:
        q = q.filter(StockMovement.created_at >= date_from)
    if date_to:
        q = q.filter(StockMovement.created_at <= date_to)
    return paginate(q.order_by(StockMovement.created_at.desc()), page, page_size, movement_dict)


def _get_item(db: Session, user: User, inventory_id: str, need_stock=False) -> InventoryItem:
    item = db.get(InventoryItem, inventory_id)
    if not item:
        raise HTTPException(404, "Inventory record not found")
    assert_facility_access(db, user, item.facility_id, need_stock=need_stock)
    return item


@router.post("", status_code=201)
def add_inventory(body: InventoryIn, background: BackgroundTasks,
                  user: User = Depends(require("inventory.update")), db: Session = Depends(get_db)):
    assert_facility_access(db, user, body.facility_id, need_stock=True)
    facility = db.get(Facility, body.facility_id)
    medicine = db.get(Medicine, body.medicine_id)
    if not facility or not medicine:
        raise HTTPException(404, "Facility or medicine not found")
    try:
        out = create_inventory(db, facility, medicine, body.quantity, body.min_threshold, user, unit=body.unit,
                               batch_number=body.batch_number, expiry_date=body.expiry_date,
                               internal_notes=body.internal_notes)
    except DomainError:
        db.rollback()
        raise
    db.commit()
    background.add_task(dispatch_in_background)
    return {"item": inventory_dict(out.item), "alerts": [alert_dict(a) for a in out.alerts]}


@router.get("/{inventory_id}")
def get_inventory(inventory_id: str, user: User = Depends(require("inventory.view")), db: Session = Depends(get_db)):
    item = _get_item(db, user, inventory_id)
    return inventory_dict(item, estimate=estimate_days_remaining(db, item))


@router.patch("/{inventory_id}")
def update_inventory(inventory_id: str, body: InventoryPatch, background: BackgroundTasks,
                     user: User = Depends(require("inventory.update")), db: Session = Depends(get_db)):
    item = _get_item(db, user, inventory_id, need_stock=True)
    if body.expected_version is not None and body.expected_version != item.version:
        raise DomainError("This record was changed by someone else. Reload and try again.", 409, "version_conflict")
    changes = body.model_dump(exclude_unset=True, exclude={"expected_version"})
    for k, v in changes.items():
        setattr(item, k, v)
    audit(db, "inventory.update", "inventory", item.id, actor=user, facility_id=item.facility_id,
          details={k: str(v) for k, v in changes.items() if k != "internal_notes"})
    if "min_threshold" in changes:
        from app.services.alerts import evaluate_inventory
        evaluate_inventory(db, item, previous_quantity=item.quantity)
    try:
        db.commit()
    except StaleDataError as exc:
        db.rollback()
        raise DomainError("This record was changed by someone else. Reload and try again.", 409,
                          "version_conflict") from exc
    background.add_task(dispatch_in_background)
    return inventory_dict(item)


@router.post("/{inventory_id}/movements", status_code=201)
def add_movement(inventory_id: str, body: MovementIn, background: BackgroundTasks,
                 user: User = Depends(require("inventory.update")), db: Session = Depends(get_db)):
    _get_item(db, user, inventory_id, need_stock=True)
    item = lock_inventory(db, inventory_id)
    try:
        out = record_movement(db, item, body.movement_type, body.quantity, user, reason=body.reason,
                              idempotency_key=body.idempotency_key, expected_version=body.expected_version)
        db.commit()
    except StaleDataError as exc:
        db.rollback()
        raise DomainError("This record was changed by someone else. Reload and try again.", 409,
                          "version_conflict") from exc
    except DomainError:
        db.rollback()
        raise
    background.add_task(dispatch_in_background)
    return {"movement": movement_dict(out.movement), "item": inventory_dict(out.item), "duplicate": out.duplicate,
            "alerts": [alert_dict(a) for a in out.alerts]}


@router.get("/{inventory_id}/history")
def history(inventory_id: str, days: int = Query(30, ge=1, le=365), page: int = PageQ,
            page_size: int = Query(50, ge=1, le=200),
            user: User = Depends(require("inventory.view")), db: Session = Depends(get_db)):
    item = _get_item(db, user, inventory_id)
    q = db.query(StockMovement).filter_by(inventory_id=item.id).order_by(StockMovement.created_at.desc())
    movements = paginate(q, page, page_size, movement_dict)
    since = utcnow() - timedelta(days=days)
    series_rows = (db.query(StockMovement).filter(StockMovement.inventory_id == item.id,
                                                  StockMovement.created_at >= since)
                   .order_by(StockMovement.created_at).all())
    levels = [{"at": m.created_at, "quantity": m.quantity_after} for m in series_rows]
    est = estimate_days_remaining(db, item)
    return {"item": inventory_dict(item, estimate=est), "movements": movements, "levels": levels}
