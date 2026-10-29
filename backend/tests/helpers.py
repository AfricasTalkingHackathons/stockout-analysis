from app.models import Facility, InventoryItem, Medicine


def facility(db, code: str) -> Facility:
    return db.query(Facility).filter_by(code=code).one()


def medicine(db, code: str) -> Medicine:
    return db.query(Medicine).filter_by(code=code).one()


def item(db, fcode: str, mcode: str) -> InventoryItem:
    return db.query(InventoryItem).filter_by(facility_id=facility(db, fcode).id,
                                             medicine_id=medicine(db, mcode).id).one()


def set_count(client, headers, inventory_id: str, qty: int, key: str | None = None):
    body = {"movement_type": "count", "quantity": qty}
    if key:
        body["idempotency_key"] = key
    return client.post(f"/api/inventory/{inventory_id}/movements", json=body, headers=headers)
