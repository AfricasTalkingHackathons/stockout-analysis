from datetime import timedelta

from app.database import utcnow
from app.models import InventoryItem, StockReport, VerificationStatus
from app.services.availability import compute_status
from app.services.runtime_config import get_config
from tests.helpers import facility, item, medicine, set_count

CFG = {"fresh_hours": 72, "unknown_after_days": 30}


def _item(qty, minimum, age_hours, verified=True):
    return InventoryItem(quantity=qty, min_threshold=minimum, last_updated_at=utcnow() - timedelta(hours=age_hours),
                         verification_status="verified" if verified else "unverified")


def test_status_categories():
    assert compute_status(_item(100, 10, 1), [], CFG).status == "available"
    assert compute_status(_item(5, 10, 1), [], CFG).status == "low"
    zero = compute_status(_item(0, 10, 1), [], CFG)
    assert zero.status == "out_of_stock" and zero.confirmed
    assert compute_status(_item(100, 10, 100), [], CFG).status == "stale"
    assert compute_status(_item(100, 10, 24 * 40), [], CFG).status == "unknown"
    missing = compute_status(None, [], CFG)
    assert missing.status == "unknown" and missing.last_updated_at is None


def test_zero_is_not_missing_data():
    assert compute_status(_item(0, 0, 1), [], CFG).status == "out_of_stock"
    assert compute_status(None, [], CFG).status == "unknown"


def test_unverified_report_not_presented_as_confirmed():
    r = StockReport(reported_status="available", source="web", verification_status=VerificationStatus.UNVERIFIED,
                    created_at=utcnow())
    st = compute_status(None, [r], CFG)
    assert st.status == "stale" and not st.confirmed
    # Newer unverified "out" doesn't override a confirmed fresh inventory record, but adds a note
    r2 = StockReport(reported_status="out_of_stock", source="ussd", verification_status="unverified",
                     created_at=utcnow())
    st2 = compute_status(_item(100, 10, 5), [r2], CFG)
    assert st2.status == "available" and st2.notes


def test_verified_newer_report_overrides():
    r = StockReport(reported_status="out_of_stock", source="ussd", verification_status="verified",
                    created_at=utcnow())
    assert compute_status(_item(100, 10, 5), [r], CFG).status == "out_of_stock"
    rejected = StockReport(reported_status="out_of_stock", source="ussd", verification_status="rejected",
                           created_at=utcnow())
    assert compute_status(_item(100, 10, 5), [rejected], CFG).status == "available"


def test_search_by_generic_and_brand(client):
    r = client.get("/api/medicines?q=panadol").json()
    assert r["items"][0]["generic_name"] == "Paracetamol"
    r = client.get("/api/medicines?q=amoxi").json()
    assert r["items"][0]["code"] == "MED001"


def test_search_results_order_and_stale(client, db):
    nairobi = facility(db, "FAC-D001").county_id
    med = medicine(db, "MED001")
    body = client.get(f"/api/availability/search?medicine_id={med.id}&county_id={nairobi}").json()
    by_code = {r["facility"]["code"]: r for r in body["results"]}
    assert by_code["FAC-D001"]["status"] == "available"
    assert by_code["FAC-D002"]["status"] == "low"
    assert by_code["FAC-D004"]["status"] == "stale" and not by_code["FAC-D004"]["confirmed"]
    assert "FAC-D006" not in by_code  # pending facility hidden
    assert "FAC-D005" not in by_code  # other county
    statuses = [r["status"] for r in body["results"]]
    assert statuses.index("stale") > statuses.index("low")
    assert "contact the facility" in body["notice"].lower()
    # quantity only shown when facility opted in and data confirmed
    assert by_code["FAC-D001"]["quantity"] == 400
    assert by_code["FAC-D002"]["quantity"] is None
    assert by_code["FAC-D004"]["quantity"] is None


def test_distance_sorting(client, db):
    med = medicine(db, "MED001")
    # A point right next to Baraka (FAC-D003)
    body = client.get(f"/api/availability/search?medicine_id={med.id}&lat=-1.2712&lng=36.8125").json()
    known = [r for r in body["results"] if r["status"] in ("available", "low", "stale")]
    assert known[0]["facility"]["code"] == "FAC-D003"
    assert known[0]["distance_km"] < 0.1


def test_filter_facility_type(client, db):
    med = medicine(db, "MED001")
    body = client.get(f"/api/availability/search?medicine_id={med.id}&facility_type=clinic").json()
    assert {r["facility"]["facility_type"] for r in body["results"]} == {"clinic"}


def test_no_results_offers_alternatives(client, db, mwangaza_h, tumaini_h):
    nairobi = facility(db, "FAC-D001").county_id
    med = medicine(db, "MED001")
    for fcode, h in (("FAC-D001", mwangaza_h), ("FAC-D002", tumaini_h)):
        assert set_count(client, h, item(db, fcode, "MED001").id, 0).status_code == 201
    from tests.conftest import login
    assert set_count(client, login(client, "admin.baraka"), item(db, "FAC-D003", "MED001").id, 0).status_code == 201
    body = client.get(f"/api/availability/search?medicine_id={med.id}&county_id={nairobi}").json()
    assert body["alternatives"]["can_subscribe"]
    assert any(a["county"] == "Kiambu" for a in body["alternatives"]["other_areas"])


def test_unknown_medicine_query(client):
    body = client.get("/api/availability/search?q=zzzzzz").json()
    assert body["results"] == [] and "No matching medicine" in body["notice"]


def test_freshness_configurable(client, db, admin_h):
    med = medicine(db, "MED001")
    r = client.put("/api/admin/config", json={"values": {"fresh_hours": 24 * 12}}, headers=admin_h)
    assert r.status_code == 200
    assert get_config(db)["fresh_hours"] == 288
    body = client.get(f"/api/availability/search?medicine_id={med.id}").json()
    upendo = next(r for r in body["results"] if r["facility"]["code"] == "FAC-D004")
    assert upendo["status"] == "available"
    bad = client.put("/api/admin/config", json={"values": {"fresh_hours": -1}}, headers=admin_h)
    assert bad.status_code == 422
