from datetime import timedelta

from app.models import NotificationDelivery, PickupSchedule
from app.services.pickup import _contains_banned, reminder_message, run_due_reminders, today_ke
from tests.conftest import login
from tests.helpers import facility, medicine


def test_refill_search_shows_alternative_when_usual_clinic_is_short(client, db):
    med = medicine(db, "MED016")
    nairobi = facility(db, "FAC-D002").county_id
    res = client.get("/api/availability/search", params={"medicine_id": med.id, "county_id": nairobi}).json()
    by_code = {r["facility"]["code"]: r for r in res["results"]}
    assert by_code["FAC-D002"]["status"] == "low"
    assert by_code["FAC-D001"]["status"] == "available"
    assert by_code["FAC-D003"]["status"] == "available"
    long_term = client.get("/api/medicines", params={"long_term": True, "page_size": 50}).json()["items"]
    assert any(m["code"] == "MED016" and m["is_long_term"] for m in long_term)
    assert all(m["is_long_term"] for m in long_term)


def test_create_lookup_and_privacy_of_reminder_sms(client, db):
    med = medicine(db, "MED016")
    tumaini = facility(db, "FAC-D002")
    body = {
        "phone": "0712000088",
        "medicine_id": med.id,
        "county_id": tumaini.county_id,
        "preferred_facility_id": tumaini.id,
        "next_pickup_on": (today_ke() + timedelta(days=2)).isoformat(),
        "interval_days": 30,
        "remind_days_before": 3,
        "consent": True,
    }
    r = client.post("/api/pickup-schedules", json=body)
    assert r.status_code == 201
    created = r.json()
    assert created["phone"].startswith("+254") and "*" in created["phone"]
    assert created["preferred_status"]["status"] == "low"
    assert any(a["name"].startswith("Baraka") or a["name"].startswith("Mwangaza") for a in created["alternatives"])

    sent = run_due_reminders(db)
    assert sent >= 1
    db.commit()
    db.expire_all()
    sms = db.query(NotificationDelivery).filter_by(purpose="pickup_reminder").all()
    assert sms
    text = sms[0].message.lower()
    assert not _contains_banned(text)
    assert "tenofovir" not in text and "tld" not in text
    assert "do not change how you take your medicine" in text or "do not skip" in text
    assert sms[0].status in ("queued", "simulated")


def test_reminder_sms_builder_never_names_stigmatised_terms(db):
    s = db.query(PickupSchedule).filter_by(is_demo=True).one()
    msg = reminder_message(db, s)
    lowered = msg.lower()
    assert not _contains_banned(lowered)
    assert s.medicine.generic_name.lower() not in lowered
    assert "baraka" in lowered or "mwangaza" in lowered or "jamii" in lowered


def test_stop_cancels_pickup_and_availability(client, db):
    med = medicine(db, "MED003")
    nairobi = facility(db, "FAC-D001").county_id
    client.post("/api/pickup-schedules", json={
        "phone": "0712000099", "medicine_id": med.id, "county_id": nairobi,
        "next_pickup_on": (today_ke() + timedelta(days=7)).isoformat(),
        "interval_days": 30, "remind_days_before": 3, "consent": True,
    })
    client.post("/api/notifications/subscriptions", json={
        "phone": "0712000099", "medicine_id": med.id, "county_id": nairobi, "consent": True,
    })
    r = client.post("/api/webhooks/sms", data={"from": "+254712000099", "to": "12345", "text": "STOP",
                                               "id": "stop-pickup", "date": "2026-10-29 10:00:00"})
    assert r.json()["outcome"] == "unsubscribed"
    db.expire_all()
    assert db.query(PickupSchedule).filter_by(phone="+254712000099", is_active=True).count() == 0


def test_cancel_response_does_not_reveal_whether_subscribed(client):
    a = client.post("/api/pickup-schedules/cancel", json={"phone": "0799999999"}).json()
    b = client.post("/api/notifications/unsubscribe", json={"phone": "0799999999"}).json()
    assert "If this number had" in a["message"]
    assert "If this number had" in b["message"]


def test_staff_see_aggregated_demand_not_phones(client, db, mwangaza_h):
    med = medicine(db, "MED016")
    mw = facility(db, "FAC-D001")
    client.post("/api/pickup-schedules", json={
        "phone": "0712000077", "medicine_id": med.id, "county_id": mw.county_id,
        "preferred_facility_id": mw.id,
        "next_pickup_on": today_ke().isoformat(),
        "interval_days": 28, "remind_days_before": 3, "consent": True,
    })
    d = client.get("/api/pickup-schedules/demand", headers=mwangaza_h).json()
    assert d["total_schedules"] >= 1
    assert all("phone" not in row and "0712" not in str(row) for row in d["items"])
    staff = login(client, "staff.mwangaza")
    other = client.get("/api/pickup-schedules/demand", headers=staff).json()
    assert all(row["facility_id"] == mw.id for row in other["items"])


def test_ussd_pickup_reminder_flow(client, db):
    from tests.test_ussd import ussd, _county_option
    menu = ussd(client, "pk1", "4")
    assert "Enter medicine" in menu
    counties = ussd(client, "pk1", "4*metformin")
    n = _county_option(counties, "Nairobi")
    when = ussd(client, "pk1", f"4*metformin*{n}")
    assert "Next collection" in when
    interval = ussd(client, "pk1", f"4*metformin*{n}*3")
    assert "How often" in interval
    confirm = ussd(client, "pk1", f"4*metformin*{n}*3*3")
    assert "will not name the medicine" in confirm
    end = ussd(client, "pk1", f"4*metformin*{n}*3*3*1")
    assert end.startswith("END Pickup reminder saved")
    db.expire_all()
    assert db.query(PickupSchedule).filter_by(phone="+254712000111", is_active=True).count() == 1
    ussd(client, "pk1", f"4*metformin*{n}*3*3*1")
    assert db.query(PickupSchedule).filter_by(phone="+254712000111").count() == 1


def test_does_not_instruct_underdose(client, db):
    notice = client.get("/api/availability/search", params={
        "medicine_id": medicine(db, "MED019").id,
        "county_id": facility(db, "FAC-D002").county_id,
    }).json()["notice"]
    assert "Do not change prescribed medicines" in notice
    by_code = {r["facility"]["code"]: r["status"]
               for r in client.get("/api/availability/search", params={
                   "medicine_id": medicine(db, "MED019").id,
                   "county_id": facility(db, "FAC-D002").county_id,
               }).json()["results"]}
    assert by_code["FAC-D002"] == "out_of_stock"
    assert by_code["FAC-D003"] == "available"
