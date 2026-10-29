from datetime import timedelta

from app.database import utcnow
from app.models import County, Location, NotificationDelivery, NotificationSubscription, StockReport, UssdSession

PHONE = "+254712000111"


def ussd(client, session, text, phone=PHONE):
    r = client.post("/api/webhooks/ussd", data={"sessionId": session, "serviceCode": "*384*1#",
                                                "phoneNumber": phone, "text": text})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    return r.text


def _county_option(menu: str, name: str) -> str:
    for line in menu.splitlines():
        if name in line:
            return line.split(".")[0]
    raise AssertionError(f"{name} not in {menu}")


def _path_to_named_item(client, session: str, start: str, name: str) -> str:
    """Follow '9. More' on a paginated USSD list until `name` appears, then include its choice."""
    text = start
    menu = ussd(client, session, text)
    for _ in range(25):
        for line in menu.splitlines():
            if name in line and line[0].isdigit():
                return f"{text}*{line.split('.')[0]}"
        if "9. More" not in menu:
            raise AssertionError(f"{name} not in paginated list:\n{menu}")
        text = f"{text}*9"
        menu = ussd(client, session, text)
    raise AssertionError(f"{name} not found after pagination")


def test_main_menu_and_exit(client):
    first = ussd(client, "s1", "")
    assert first.startswith("CON ") and "1. Find medicine" in first
    assert "4. Pickup reminder" in first
    assert ussd(client, "s1", "5").startswith("END ")


def test_find_medicine_flow_with_sms(client, db):
    menu = ussd(client, "s2", "1")
    assert menu.startswith("CON Select county")
    nairobi = _path_to_named_item(client, "s2", "1", "Nairobi")
    sub = ussd(client, "s2", nairobi)
    assert "Select sub-county" in sub and "All sub-counties" in sub
    assert "Enter medicine" in ussd(client, "s2", f"{nairobi}*1")
    results = ussd(client, "s2", f"{nairobi}*1*amoxicillin")
    assert results.startswith("CON Results") and "AVAIL" in results
    detail = ussd(client, "s2", f"{nairobi}*1*amoxicillin*1")
    assert "Updated" in detail and "1. SMS me this" in detail
    assert len(detail) <= 182
    end = ussd(client, "s2", f"{nairobi}*1*amoxicillin*1*1")
    assert end.startswith("END SMS summary requested") and "Simulated" in end
    db.expire_all()
    sms = db.query(NotificationDelivery).filter_by(purpose="ussd_search_result").all()
    assert len(sms) == 1 and "[DEMO]" in sms[0].message


def test_repeated_request_is_idempotent(client, db):
    ussd(client, "s3", "1")
    nairobi = _path_to_named_item(client, "s3", "1", "Nairobi")
    path = f"{nairobi}*1*amoxicillin*1*1"
    for p in ("1", nairobi, f"{nairobi}*1", f"{nairobi}*1*amoxicillin", f"{nairobi}*1*amoxicillin*1"):
        ussd(client, "s3", p)
    a = ussd(client, "s3", path)
    b = ussd(client, "s3", path)  # provider retry
    assert a == b
    db.expire_all()
    assert db.query(NotificationDelivery).filter_by(purpose="ussd_search_result").count() == 1


def test_invalid_input_and_pagination(client):
    bad = ussd(client, "s4", "7")
    assert bad.startswith("CON Invalid choice")
    menu = ussd(client, "s4", "7*1")
    assert "Select county" in menu
    short = ussd(client, "s4", "7*1*1*a")  # first county list item then too-short name
    assert "CON" in short
    assert "Invalid choice" in ussd(client, "s5", "1*abc")


def test_find_lists_subcounties_for_chosen_county(client):
    nairobi = _path_to_named_item(client, "sc1", "1", "Nairobi")
    sub = ussd(client, "sc1", nairobi)
    assert sub.startswith("CON Select sub-county")
    assert "1. All sub-counties" in sub
    assert any(name in sub for name in ("Westlands", "Kilimani", "Embakasi", "Kasarani", "Kibera", "Dagoretti"))
    mombasa = _path_to_named_item(client, "sc2", "1", "Mombasa")
    msub = ussd(client, "sc2", mombasa)
    assert "Select sub-county" in msub
    assert any(name in msub for name in ("Nyali", "Likoni", "Changamwe", "Mvita", "Kisauni"))


def test_every_county_has_subcounties(db):
    counties = db.query(County).all()
    assert len(counties) == 47
    missing = [c.name for c in counties if db.query(Location).filter_by(county_id=c.id).count() == 0]
    assert missing == []


def test_unknown_session_with_path_replays(client):
    menu = ussd(client, "fresh-session", "1")
    assert "Select county" in menu
    nairobi = _path_to_named_item(client, "fresh-session", "1", "Nairobi")
    # A brand-new session id arriving mid-flow (e.g. after a restart) still resolves correctly
    assert "Results" in ussd(client, "never-seen", f"{nairobi}*1*amoxicillin")


def test_report_unavailable_flow(client, db):
    assert "Enter medicine" in ussd(client, "r1", "2")
    counties = ussd(client, "r1", "2*amoxicillin")
    n = _county_option(counties, "Nairobi")
    fac = ussd(client, "r1", f"2*amoxicillin*{n}")
    assert "Select facility" in fac
    confirm = ussd(client, "r1", f"2*amoxicillin*{n}*1")
    assert "1. Confirm" in confirm
    end = ussd(client, "r1", f"2*amoxicillin*{n}*1*1")
    assert end.startswith("END Report received. Ref SR-")
    ussd(client, "r1", f"2*amoxicillin*{n}*1*1")
    db.expire_all()
    reports = db.query(StockReport).filter_by(source="ussd").all()
    assert len(reports) == 1 and reports[0].verification_status == "unverified"
    assert reports[0].reporter_hash and PHONE not in reports[0].reporter_hash
    sms = db.query(NotificationDelivery).filter_by(purpose="ussd_report_confirm").all()
    assert len(sms) == 1 and reports[0].reference in sms[0].message


def test_cancel_report(client, db):
    counties = ussd(client, "r2", "2*amoxicillin")
    n = _county_option(counties, "Nairobi")
    assert ussd(client, "r2", f"2*amoxicillin*{n}*1*2").startswith("END Cancelled")
    assert db.query(StockReport).count() == 0


def test_subscribe_view_and_stop(client, db):
    assert "Subscribe" in ussd(client, "a1", "3")
    counties = ussd(client, "a1", "3*1*amoxicillin")
    n = _county_option(counties, "Nairobi")
    assert "I agree" in ussd(client, "a1", f"3*1*amoxicillin*{n}")
    assert ussd(client, "a1", f"3*1*amoxicillin*{n}*1").startswith("END Alert set")
    db.expire_all()
    assert db.query(NotificationSubscription).filter_by(phone=PHONE, is_active=True).count() == 1
    confirm = db.query(NotificationDelivery).filter_by(purpose="ussd_subscribe_confirm").all()
    assert len(confirm) == 1 and "Reply STOP" in confirm[0].message
    assert "Amoxicillin" in ussd(client, "a2", "3*2")
    assert ussd(client, "a3", "3*3").startswith("END All availability alerts stopped")
    db.expire_all()
    assert db.query(NotificationSubscription).filter_by(phone=PHONE, is_active=True).count() == 0


def test_session_timeout(client, db):
    ussd(client, "t1", "")
    s = db.query(UssdSession).filter_by(session_id="t1").one()
    s.updated_at = utcnow() - timedelta(minutes=10)
    db.commit()
    assert "timed out" in ussd(client, "t1", "1")


def test_phone_not_stored_in_plain_text(client, db):
    ussd(client, "p1", "")
    s = db.query(UssdSession).filter_by(session_id="p1").one()
    assert PHONE not in s.phone_hash


def test_webhook_missing_fields(client):
    assert client.post("/api/webhooks/ussd", data={"text": ""}).status_code == 400


def test_webhook_token_enforced(client, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "at_webhook_token", "s3cret-token")
    data = {"sessionId": "w1", "phoneNumber": PHONE, "text": ""}
    assert client.post("/api/webhooks/ussd", data=data).status_code == 401
    assert client.post("/api/webhooks/ussd?token=wrong", data=data).status_code == 401
    assert client.post("/api/webhooks/ussd?token=s3cret-token", data=data).status_code == 200


def test_simulator_uses_same_flow(client):
    r = client.post("/api/simulator/ussd", json={"session_id": "abc123", "phone": "0712000111", "text": ""})
    assert r.status_code == 200 and r.json()["continue"] and "Find medicine" in r.json()["text"]
