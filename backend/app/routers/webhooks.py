"""Africa's Talking callbacks plus a demo simulator that calls the same services.

Africa's Talking does not sign callbacks, so authenticity is enforced by:
  1. a secret token in the callback URL (?token=AT_WEBHOOK_TOKEN), compared in constant time;
  2. an optional source IP allowlist (AT_WEBHOOK_ALLOWED_IPS);
  3. strict payload validation and idempotent processing keyed on provider IDs.
"""

import hmac
import logging
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import require
from app.models import NotificationDelivery, User
from app.ratelimit import client_ip, public_limit
from app.schemas import SmsSimIn, UssdSimIn
from app.serializers import delivery_dict
from app.services.audit import audit
from app.services.notifications import apply_delivery_report, dispatch_in_background
from app.services.sms_commands import process_inbound_sms
from app.services.ussd import handle_ussd
from app.utils import normalize_ke_phone

log = logging.getLogger("stockout.webhooks")
router = APIRouter(tags=["africas-talking"])


def verify_callback(request: Request) -> None:
    s = get_settings()
    allowed = {ip.strip() for ip in s.at_webhook_allowed_ips.split(",") if ip.strip()}
    if allowed and client_ip(request) not in allowed:
        raise HTTPException(403, "Callback source not allowed")
    if not s.at_webhook_token:
        if s.demo_mode:
            return  # documented: demo mode accepts unauthenticated callbacks
        raise HTTPException(503, "Webhook token not configured")
    supplied = request.query_params.get("token", "")
    if not hmac.compare_digest(supplied.encode(), s.at_webhook_token.encode()):
        raise HTTPException(401, "Invalid callback token")


async def _form(request: Request) -> dict[str, str]:
    form = await request.form()
    return {k: str(v)[:500] for k, v in form.items()}


def _require_fields(data: dict, *names: str) -> None:
    missing = [n for n in names if not data.get(n)]
    if missing:
        raise HTTPException(400, f"Missing fields: {', '.join(missing)}")


@router.post("/api/webhooks/ussd", response_class=PlainTextResponse, dependencies=[Depends(verify_callback)])
async def ussd_callback(request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    data = await _form(request)
    _require_fields(data, "sessionId", "phoneNumber")
    response = handle_ussd(db, data["sessionId"][:100], data["phoneNumber"][:20], data.get("serviceCode"),
                           data.get("text", ""))
    background.add_task(dispatch_in_background)
    return PlainTextResponse(response)


@router.post("/api/webhooks/sms", dependencies=[Depends(verify_callback)])
async def sms_callback(request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    data = await _form(request)
    _require_fields(data, "from", "id")
    result = process_inbound_sms(db, data["id"][:100], data["from"][:20], data.get("text", ""))
    background.add_task(dispatch_in_background)
    return {"ok": True, "outcome": result.outcome, "duplicate": result.duplicate}


@router.post("/api/webhooks/delivery-report", dependencies=[Depends(verify_callback)])
async def delivery_report(request: Request, db: Session = Depends(get_db)):
    data = await _form(request)
    _require_fields(data, "id", "status")
    found = apply_delivery_report(db, data["id"][:100], data["status"][:30], data.get("failureReason"))
    db.commit()
    return {"ok": True, "matched": found}


# ---------------------------------------------------------------- simulator (demo mode only)

def _demo_only() -> None:
    if not get_settings().demo_mode:
        raise HTTPException(404, "Simulator is only available in demo mode")


@router.post("/api/simulator/ussd", tags=["simulator"],
             dependencies=[Depends(_demo_only), Depends(public_limit("ussd_sim"))])
def simulate_ussd(body: UssdSimIn, db: Session = Depends(get_db)):
    phone = normalize_ke_phone(body.phone)
    if not phone:
        raise HTTPException(422, "Enter a valid Kenyan mobile number")
    session_id = f"SIM-{body.session_id}"
    response = handle_ussd(db, session_id, phone, "*SIM#", body.text, simulated=True)
    sms = (db.query(NotificationDelivery)
           .filter(NotificationDelivery.dedupe_key.like(f"ussd:{session_id}:%"))
           .order_by(NotificationDelivery.created_at.desc()).limit(3).all())
    # Simulated sessions dispatch inline so the result can be shown immediately.
    from app.services.notifications import attempt_delivery
    for d in sms:
        if d.status == "queued":
            attempt_delivery(db, d)
    db.commit()
    return {"response": response, "continue": response.startswith("CON"), "text": response[4:],
            "simulated": True, "sms": [delivery_dict(d) | {"message": d.message} for d in sms]}


@router.post("/api/simulator/sms", tags=["simulator"], dependencies=[Depends(_demo_only)])
def simulate_inbound_sms(body: SmsSimIn, background: BackgroundTasks,
                         user: User = Depends(require("demo.reset")), db: Session = Depends(get_db)):
    msg_id = body.message_id or f"SIM-IN-{secrets.token_hex(6)}"
    result = process_inbound_sms(db, msg_id, body.phone, body.text)
    audit(db, "simulator.inbound_sms", "inbound_sms", None, actor=user, details={"outcome": result.outcome})
    db.commit()
    background.add_task(dispatch_in_background)
    return {"message_id": msg_id, "outcome": result.outcome, "reply": result.reply, "duplicate": result.duplicate,
            "simulated": True}
