from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import utcnow
from app.models import (
    Facility,
    FacilityStatus,
    Medicine,
    ReportedStatus,
    StockReport,
    StockReportVerification,
    User,
    VerificationStatus,
)
from app.services.alerts import _prefix, facility_alert_recipients, run_ripple
from app.services.audit import audit
from app.services.inventory import DomainError
from app.services.notifications import queue_sms
from app.utils import short_reference


def create_stock_report(
    db: Session,
    facility: Facility,
    medicine: Medicine,
    reported_status: str,
    source: str,
    reporter_hash: str | None = None,
    dedupe_key: str | None = None,
    comment: str | None = None,
) -> tuple[StockReport, bool]:
    """Returns (report, created). Duplicate submissions (same dedupe key) return the original."""
    if facility.status != FacilityStatus.APPROVED:
        raise DomainError("Facility is not accepting public reports", 404, "not_found")
    try:
        ReportedStatus(reported_status)
    except ValueError as exc:
        raise DomainError("Invalid reported status") from exc
    if dedupe_key:
        existing = db.query(StockReport).filter_by(dedupe_key=dedupe_key).one_or_none()
        if existing:
            return existing, False
    for _ in range(5):
        ref = short_reference("SR")
        if not db.query(StockReport).filter_by(reference=ref).first():
            break
    report = StockReport(reference=ref, facility_id=facility.id, medicine_id=medicine.id,
                         reported_status=reported_status, source=source, reporter_hash=reporter_hash,
                         dedupe_key=dedupe_key, comment=(comment or None),
                         verification_status=VerificationStatus.UNVERIFIED)
    report.facility, report.medicine = facility, medicine
    db.add(report)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        existing = db.query(StockReport).filter_by(dedupe_key=dedupe_key).one_or_none()
        if existing:
            return existing, False
        raise DomainError("Could not save report") from exc
    audit(db, "report.create", "stock_report", report.id, actor_label=f"public:{source}",
          facility_id=facility.id, details={"medicine": medicine.code, "status": reported_status,
                                             "reference": report.reference})
    if reported_status in (ReportedStatus.OUT_OF_STOCK, ReportedStatus.LOW):
        for phone in facility_alert_recipients(db, facility.id):
            queue_sms(db, phone,
                      f"{_prefix(facility.is_demo)}A public report ({report.reference}) says {medicine.display_name} "
                      f"is {reported_status.replace('_', ' ')} at {facility.name}. Please verify in the dashboard.",
                      purpose="verification_request", dedupe_key=f"verify:{report.id}:{phone}",
                      facility_id=facility.id, is_demo=facility.is_demo)
        run_ripple(db, medicine.id, facility.county_id)
    return report, True


def verify_stock_report(db: Session, report: StockReport, decision: str, user: User, note: str | None) -> StockReport:
    if decision not in (VerificationStatus.VERIFIED, VerificationStatus.REJECTED, VerificationStatus.DISPUTED):
        raise DomainError("Decision must be verified, rejected or disputed")
    report.verification_status = decision
    report.verified_by_id = user.id
    report.verified_at = utcnow()
    report.verifications.append(StockReportVerification(decision=decision, note=note, decided_by_id=user.id))
    audit(db, "report.verify", "stock_report", report.id, actor=user, facility_id=report.facility_id,
          details={"decision": decision, "note": note})
    run_ripple(db, report.medicine_id, report.facility.county_id)
    return report
