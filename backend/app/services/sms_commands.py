"""Inbound SMS commands.

  STOCK <MEDICINE_CODE> <QUANTITY>                 e.g. STOCK MED001 12
  STOCK <FACILITY_CODE> <MEDICINE_CODE> <QUANTITY>  when the sender is staff at several facilities
  STOP                                             opt out of all availability alerts
  HELP

STOCK records a physical count (movement type 'count') for the sender's facility. The sender must
match an active staff membership's registered SMS number with stock-update permission at an approved
facility. Each provider message id is processed once.
"""

import re
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import utcnow
from app.models import (
    Facility,
    FacilityMembership,
    FacilityStatus,
    InboundMessage,
    InventoryItem,
    Medicine,
    MovementType,
    NotificationSubscription,
    PickupSchedule,
    User,
)
from app.security import hash_identifier
from app.services.audit import audit
from app.services.inventory import DomainError, record_movement
from app.services.notifications import queue_sms
from app.utils import normalize_ke_phone

STOCK_RE = re.compile(r"^STOCK\s+(?:(?P<fac>FAC-?\w+)\s+)?(?P<med>[A-Z0-9-]+)\s+(?P<qty>-?\d{1,7})$")
HELP_TEXT = "StockOut Alert: send STOCK <MED CODE> <QTY> e.g. STOCK MED001 12. Reply STOP to stop alerts."


def _unit(unit: str, qty: int) -> str:
    if qty == 1 or len(unit) <= 2 or unit.endswith("s"):
        return unit
    return unit + "s"


@dataclass
class CommandResult:
    outcome: str
    reply: str | None
    duplicate: bool = False


def process_inbound_sms(db: Session, provider_message_id: str, sender: str, text: str,
                        reply: bool = True) -> CommandResult:
    prior = db.query(InboundMessage).filter_by(provider_message_id=provider_message_id).one_or_none()
    if prior:
        return CommandResult(prior.outcome, prior.response, duplicate=True)

    phone = normalize_ke_phone(sender) or sender
    body = re.sub(r"\s+", " ", (text or "").strip().upper())
    command = body.split(" ", 1)[0] if body else ""

    if command == "STOP":
        result = _stop(db, phone)
    elif command == "STOCK":
        result = _stock(db, phone, body, provider_message_id)
    elif command in ("HELP", ""):
        result = CommandResult("help", HELP_TEXT)
    else:
        result = CommandResult("unrecognised", "Command not recognised. " + HELP_TEXT)

    db.add(InboundMessage(provider_message_id=provider_message_id, sender_hash=hash_identifier(phone),
                          command=command[:20] or "EMPTY", outcome=result.outcome, response=result.reply))
    if reply and result.reply:
        queue_sms(db, phone, result.reply, purpose="sms_command_reply", dedupe_key=f"inbound:{provider_message_id}")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # concurrent duplicate callback won the race
        prior = db.query(InboundMessage).filter_by(provider_message_id=provider_message_id).one()
        return CommandResult(prior.outcome, prior.response, duplicate=True)
    return result


def _stop(db: Session, phone: str) -> CommandResult:
    subs = db.query(NotificationSubscription).filter_by(phone=phone, is_active=True).all()
    for s in subs:
        s.is_active, s.unsubscribed_at = False, utcnow()
    pickups = db.query(PickupSchedule).filter_by(phone=phone, is_active=True).all()
    for s in pickups:
        s.is_active, s.unsubscribed_at = False, utcnow()
    return CommandResult(
        "unsubscribed",
        f"StockOut Alert: availability alerts ({len(subs)}) and pickup reminders ({len(pickups)}) stopped.",
    )


def _stock(db: Session, phone: str, body: str, msg_id: str) -> CommandResult:
    m = STOCK_RE.match(body)
    if not m:
        return CommandResult("malformed", "Format: STOCK <MED CODE> <QTY>, e.g. STOCK MED001 12")
    qty = int(m["qty"])
    if qty < 0:
        return CommandResult("invalid_quantity", "Quantity cannot be negative.")

    memberships = (
        db.query(FacilityMembership)
        .join(User, User.id == FacilityMembership.user_id)
        .join(Facility, Facility.id == FacilityMembership.facility_id)
        .filter(FacilityMembership.sms_phone == phone, FacilityMembership.can_update_stock.is_(True),
                User.is_active.is_(True), Facility.status == FacilityStatus.APPROVED)
        .all()
    )
    if not memberships:
        audit(db, "sms.stock_rejected", "inbound_sms", None, actor_label="sms:unauthorised",
              details={"sender_hash": hash_identifier(phone)[:12]})
        return CommandResult("unauthorised", "This number is not authorised to update stock.")

    if m["fac"]:
        fac_code = m["fac"] if "-" in m["fac"] else m["fac"].replace("FAC", "FAC-", 1)
        memberships = [x for x in memberships if x.facility.code == fac_code]
        if not memberships:
            return CommandResult("unauthorised", f"You are not authorised for facility {fac_code}.")
    elif len(memberships) > 1:
        codes = ", ".join(x.facility.code for x in memberships[:4])
        return CommandResult("ambiguous", f"You are staff at several facilities. Use STOCK <FAC CODE> <MED> <QTY>. "
                                          f"Codes: {codes}")
    membership = memberships[0]

    medicine = db.query(Medicine).filter_by(code=m["med"]).one_or_none()
    if medicine is None:
        return CommandResult("unknown_medicine", f"Unknown medicine code {m['med']}.")
    item = db.query(InventoryItem).filter_by(facility_id=membership.facility_id,
                                             medicine_id=medicine.id).one_or_none()
    if item is None:
        return CommandResult("no_inventory", f"{medicine.code} has no inventory record at "
                                             f"{membership.facility.name}. Add it in the dashboard first.")
    try:
        out = record_movement(db, item, MovementType.COUNT, qty, membership.user, reason="SMS stock count",
                              idempotency_key=f"sms:{msg_id}", source="sms",
                              actor_label=f"sms:{membership.user.email}")
    except DomainError as e:
        return CommandResult("rejected", f"Not recorded: {e.message}")
    return CommandResult("recorded", f"StockOut Alert: {medicine.code} at {membership.facility.code} recorded as "
                                     f"{out.item.quantity} {_unit(item.unit, out.item.quantity)} "
                                     f"(was {out.movement.quantity_before}).")
