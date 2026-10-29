from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import accessible_facility_ids, assert_facility_access, require
from app.models import Facility, Medicine, StockReport, User
from app.ratelimit import client_ip, sensitive_limit
from app.routers import PageQ, SizeQ, paginate
from app.schemas import StockReportIn, VerifyIn
from app.security import hash_identifier
from app.serializers import report_dict
from app.services.inventory import DomainError
from app.services.notifications import dispatch_in_background
from app.services.reports import create_stock_report, verify_stock_report

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("/stockout", status_code=201, dependencies=[Depends(sensitive_limit("report"))])
def submit_report(body: StockReportIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    f = db.get(Facility, body.facility_id)
    m = db.get(Medicine, body.medicine_id)
    if not f or not m:
        raise HTTPException(404, "Facility or medicine not found")
    try:
        r, created = create_stock_report(db, f, m, body.reported_status, "web",
                                         reporter_hash=hash_identifier(client_ip(request)),
                                         dedupe_key=f"web:{body.client_token}" if body.client_token else None,
                                         comment=body.comment)
    except DomainError:
        db.rollback()
        raise
    db.commit()
    background.add_task(dispatch_in_background)
    return {"reference": r.reference, "duplicate": not created, "verification_status": r.verification_status,
            "message": "Thank you. Your report is marked unverified until the facility or an administrator "
                       "confirms it."}


@router.get("/lookup/{reference}")
def lookup(reference: str, db: Session = Depends(get_db)):
    r = db.query(StockReport).filter_by(reference=reference.upper()).one_or_none()
    if not r:
        raise HTTPException(404, "Report not found")
    return report_dict(r, private=False)


@router.get("/stockout")
def list_reports(verification_status: str | None = Query(None, pattern="^(unverified|verified|rejected|disputed)$"),
                 facility_id: str | None = None, page: int = PageQ, page_size: int = SizeQ,
                 user: User = Depends(require("alerts.view")), db: Session = Depends(get_db)):
    q = db.query(StockReport).options(joinedload(StockReport.facility), joinedload(StockReport.medicine))
    ids = accessible_facility_ids(db, user)
    if ids is not None:
        q = q.filter(StockReport.facility_id.in_(ids or ["-"]))
    if facility_id:
        assert_facility_access(db, user, facility_id)
        q = q.filter(StockReport.facility_id == facility_id)
    if verification_status:
        q = q.filter(StockReport.verification_status == verification_status)
    return paginate(q.order_by(StockReport.created_at.desc()), page, page_size, report_dict)


@router.post("/{report_id}/verify")
def verify(report_id: str, body: VerifyIn, background: BackgroundTasks,
           user: User = Depends(require("reports.verify")), db: Session = Depends(get_db)):
    r = db.get(StockReport, report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    assert_facility_access(db, user, r.facility_id)
    verify_stock_report(db, r, body.decision, user, body.note)
    db.commit()
    background.add_task(dispatch_in_background)
    return report_dict(r)
