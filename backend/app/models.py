import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime, utcnow


def new_id() -> str:
    return str(uuid.uuid4())


class UserRole(StrEnum):
    SYSTEM_ADMIN = "system_admin"
    FACILITY_ADMIN = "facility_admin"
    FACILITY_STAFF = "facility_staff"


class FacilityType(StrEnum):
    PHARMACY = "pharmacy"
    CLINIC = "clinic"
    HEALTH_CENTRE = "health_centre"
    DISPENSARY = "dispensary"
    HOSPITAL = "hospital"


class FacilityStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    SUSPENDED = "suspended"
    REJECTED = "rejected"


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    DISPUTED = "disputed"
    REJECTED = "rejected"


class MovementType(StrEnum):
    INITIAL = "initial"
    RECEIPT = "receipt"
    DISPENSE = "dispense"
    ADJUSTMENT = "adjustment"
    COUNT = "count"


class ReportedStatus(StrEnum):
    AVAILABLE = "available"
    LOW = "low"
    OUT_OF_STOCK = "out_of_stock"


class AlertType(StrEnum):
    STOCKOUT = "stockout"
    LOW_STOCK = "low_stock"
    EARLY_WARNING = "early_warning"
    STALE_REPORT = "stale_report"
    EXPIRING = "expiring"
    RIPPLE = "ripple"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


OPEN_ALERT_STATUSES = (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED, AlertStatus.INVESTIGATING)


class DeliveryStatus(StrEnum):
    QUEUED = "queued"
    SIMULATED = "simulated"  # demo mode, nothing left the server
    ACCEPTED = "accepted"  # provider accepted the request; not yet delivered
    DELIVERED = "delivered"  # provider delivery report confirmed delivery
    FAILED = "failed"
    RETRYING = "retrying"


class Role(Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    description: Mapped[str] = mapped_column(String(255))


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_name: Mapped[str] = mapped_column(ForeignKey("roles.name", ondelete="CASCADE"), primary_key=True)
    permission: Mapped[str] = mapped_column(String(60), primary_key=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(ForeignKey("roles.name"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    memberships: Mapped[list["FacilityMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


class County(Base):
    __tablename__ = "counties"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(3), unique=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("county_id", "name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    county_id: Mapped[int] = mapped_column(ForeignKey("counties.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    county: Mapped[County] = relationship()


class Facility(Base):
    __tablename__ = "facilities"
    __table_args__ = (
        CheckConstraint("latitude IS NULL OR (latitude BETWEEN -90 AND 90)", name="ck_fac_lat"),
        CheckConstraint("longitude IS NULL OR (longitude BETWEEN -180 AND 180)", name="ck_fac_lng"),
        Index("ix_facility_county_status", "county_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    facility_type: Mapped[str] = mapped_column(String(30))
    county_id: Mapped[int] = mapped_column(ForeignKey("counties.id"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    address: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    license_number: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default=FacilityStatus.PENDING)
    status_reason: Mapped[str | None] = mapped_column(String(255))
    public_show_quantity: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    county: Mapped[County] = relationship()
    location: Mapped[Location | None] = relationship()
    memberships: Mapped[list["FacilityMembership"]] = relationship(
        back_populates="facility", cascade="all, delete-orphan"
    )


class FacilityMembership(Base):
    __tablename__ = "facility_memberships"
    __table_args__ = (UniqueConstraint("user_id", "facility_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(30))  # facility_admin | facility_staff
    can_update_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    # Number authorised to send structured SMS stock commands for this facility.
    sms_phone: Mapped[str | None] = mapped_column(String(20), index=True)
    receive_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="memberships")
    facility: Mapped[Facility] = relationship(back_populates="memberships")


class Medicine(Base):
    __tablename__ = "medicines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    generic_name: Mapped[str] = mapped_column(String(150), index=True)
    brand_names: Mapped[str] = mapped_column(String(255), default="")
    strength: Mapped[str] = mapped_column(String(60))
    dosage_form: Mapped[str] = mapped_column(String(40))
    base_unit: Mapped[str] = mapped_column(String(20))
    category: Mapped[str | None] = mapped_column(String(60))
    requires_prescription: Mapped[bool] = mapped_column(Boolean, default=False)
    # Typically collected on a repeating schedule (e.g. monthly). Not a diagnosis.
    is_long_term: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    @property
    def display_name(self) -> str:
        return f"{self.generic_name} {self.strength} {self.dosage_form}"


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("facility_id", "medicine_id", name="uq_inventory_facility_medicine"),
        CheckConstraint("quantity >= 0", name="ck_inventory_qty_nonneg"),
        CheckConstraint("min_threshold >= 0", name="ck_inventory_min_nonneg"),
        Index("ix_inventory_medicine", "medicine_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id", ondelete="CASCADE"), index=True)
    medicine_id: Mapped[str] = mapped_column(ForeignKey("medicines.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit: Mapped[str] = mapped_column(String(20))
    min_threshold: Mapped[int] = mapped_column(Integer, default=0)
    batch_number: Mapped[str | None] = mapped_column(String(60))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    last_updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    last_updated_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    verification_status: Mapped[str] = mapped_column(String(20), default=VerificationStatus.VERIFIED)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)

    facility: Mapped[Facility] = relationship()
    medicine: Mapped[Medicine] = relationship()
    last_updated_by: Mapped[User | None] = relationship()

    __mapper_args__ = {"version_id_col": version}


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity_after >= 0", name="ck_movement_after_nonneg"),
        Index("ix_movement_inventory_created", "inventory_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    inventory_id: Mapped[str] = mapped_column(ForeignKey("inventory_items.id", ondelete="CASCADE"))
    movement_type: Mapped[str] = mapped_column(String(20))
    quantity_delta: Mapped[int] = mapped_column(Integer)
    quantity_before: Mapped[int] = mapped_column(Integer)
    quantity_after: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(20), default="web")  # web | sms | system | demo
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    performed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    inventory: Mapped[InventoryItem] = relationship()
    performed_by: Mapped[User | None] = relationship()


class StockReport(Base):
    """Availability reports from the public, USSD or SMS, pending facility verification."""

    __tablename__ = "stock_reports"
    __table_args__ = (Index("ix_report_med_created", "medicine_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reference: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id", ondelete="CASCADE"), index=True)
    medicine_id: Mapped[str] = mapped_column(ForeignKey("medicines.id"))
    reported_status: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20))  # web | ussd | sms | facility_staff
    reporter_hash: Mapped[str | None] = mapped_column(String(64))
    dedupe_key: Mapped[str | None] = mapped_column(String(120), unique=True)
    comment: Mapped[str | None] = mapped_column(String(280))
    verification_status: Mapped[str] = mapped_column(String(20), default=VerificationStatus.UNVERIFIED)
    verified_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    facility: Mapped[Facility] = relationship()
    medicine: Mapped[Medicine] = relationship()
    verifications: Mapped[list["StockReportVerification"]] = relationship(
        back_populates="report", cascade="all, delete-orphan", order_by="StockReportVerification.created_at"
    )


class StockReportVerification(Base):
    __tablename__ = "stock_report_verifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_id: Mapped[str] = mapped_column(ForeignKey("stock_reports.id", ondelete="CASCADE"), index=True)
    decision: Mapped[str] = mapped_column(String(20))  # verified | rejected | disputed
    note: Mapped[str | None] = mapped_column(String(280))
    decided_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    report: Mapped[StockReport] = relationship(back_populates="verifications")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alert_status_type", "status", "alert_type"),
        Index("ix_alert_dedupe_status", "dedupe_key", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    alert_type: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default=AlertStatus.OPEN)
    dedupe_key: Mapped[str] = mapped_column(String(160))
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("facilities.id", ondelete="CASCADE"), index=True)
    medicine_id: Mapped[str | None] = mapped_column(ForeignKey("medicines.id"))
    county_id: Mapped[int | None] = mapped_column(ForeignKey("counties.id"))
    inventory_id: Mapped[str | None] = mapped_column(ForeignKey("inventory_items.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    assigned_to_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    acknowledged_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    last_notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)

    facility: Mapped[Facility | None] = relationship()
    medicine: Mapped[Medicine | None] = relationship()
    county: Mapped[County | None] = relationship()
    assigned_to: Mapped[User | None] = relationship(foreign_keys=[assigned_to_id])
    ripple_evidence: Mapped[list["RippleEvidence"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )


class RippleEvidence(Base):
    __tablename__ = "ripple_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(20))  # inventory | report
    source_id: Mapped[str] = mapped_column(String(36))
    observed_status: Mapped[str] = mapped_column(String(20))
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    verified: Mapped[bool] = mapped_column(Boolean)
    weight: Mapped[float] = mapped_column(Float)
    counted: Mapped[bool] = mapped_column(Boolean, default=True)
    alert: Mapped[Alert] = relationship(back_populates="ripple_evidence")
    facility: Mapped[Facility] = relationship()


class NotificationSubscription(Base):
    __tablename__ = "notification_subscriptions"
    __table_args__ = (
        UniqueConstraint("phone", "medicine_id", "county_id", name="uq_subscription"),
        Index("ix_subscription_lookup", "medicine_id", "county_id", "is_active"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    medicine_id: Mapped[str] = mapped_column(ForeignKey("medicines.id"))
    county_id: Mapped[int] = mapped_column(ForeignKey("counties.id"))
    channel: Mapped[str] = mapped_column(String(10), default="sms")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    consent_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    consent_source: Mapped[str] = mapped_column(String(20))
    unsubscribed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    medicine: Mapped[Medicine] = relationship()
    county: Mapped[County] = relationship()


class PickupSchedule(Base):
    """Repeating collection reminder. Stores no diagnosis — only medicine, area, dates and consent."""

    __tablename__ = "pickup_schedules"
    __table_args__ = (
        UniqueConstraint("phone", "medicine_id", name="uq_pickup_phone_medicine"),
        Index("ix_pickup_due", "is_active", "next_pickup_on"),
        CheckConstraint("interval_days >= 7 AND interval_days <= 180", name="ck_pickup_interval"),
        CheckConstraint("remind_days_before >= 1 AND remind_days_before <= 14", name="ck_pickup_remind"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    medicine_id: Mapped[str] = mapped_column(ForeignKey("medicines.id"))
    county_id: Mapped[int] = mapped_column(ForeignKey("counties.id"))
    preferred_facility_id: Mapped[str | None] = mapped_column(ForeignKey("facilities.id", ondelete="SET NULL"))
    interval_days: Mapped[int] = mapped_column(Integer, default=30)
    next_pickup_on: Mapped[date] = mapped_column(Date, index=True)
    remind_days_before: Mapped[int] = mapped_column(Integer, default=3)
    channel: Mapped[str] = mapped_column(String(10), default="sms")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    consent_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    consent_source: Mapped[str] = mapped_column(String(20))
    unsubscribed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_reminded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_reminded_for: Mapped[date | None] = mapped_column(Date)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    medicine: Mapped[Medicine] = relationship()
    county: Mapped[County] = relationship()
    preferred_facility: Mapped[Facility | None] = relationship()


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (Index("ix_delivery_status_retry", "status", "next_attempt_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recipient: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(480))
    purpose: Mapped[str] = mapped_column(String(40))
    dedupe_key: Mapped[str | None] = mapped_column(String(160), unique=True)
    status: Mapped[str] = mapped_column(String(20), default=DeliveryStatus.QUEUED, index=True)
    provider: Mapped[str | None] = mapped_column(String(30))
    provider_message_id: Mapped[str | None] = mapped_column(String(100), index=True)
    provider_status: Mapped[str | None] = mapped_column(String(60))
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    alert_id: Mapped[str | None] = mapped_column(ForeignKey("alerts.id", ondelete="SET NULL"))
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("facilities.id", ondelete="CASCADE"))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class InboundMessage(Base):
    """Inbound SMS log for idempotent webhook processing."""

    __tablename__ = "inbound_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider_message_id: Mapped[str] = mapped_column(String(100), unique=True)
    sender_hash: Mapped[str] = mapped_column(String(64))
    command: Mapped[str] = mapped_column(String(20))
    outcome: Mapped[str] = mapped_column(String(30))
    response: Mapped[str | None] = mapped_column(String(480))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class UssdSession(Base):
    __tablename__ = "ussd_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(String(100), unique=True)
    phone_hash: Mapped[str] = mapped_column(String(64))
    service_code: Mapped[str | None] = mapped_column(String(30))
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    last_text: Mapped[str] = mapped_column(String(300), default="")
    last_response: Mapped[str] = mapped_column(String(900), default="")
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    ended: Mapped[bool] = mapped_column(Boolean, default=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SearchRequest(Base):
    """Anonymous search analytics. No phone numbers or identity stored."""

    __tablename__ = "search_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    medicine_id: Mapped[str | None] = mapped_column(ForeignKey("medicines.id", ondelete="SET NULL"))
    query_text: Mapped[str | None] = mapped_column(String(80))
    county_id: Mapped[int | None] = mapped_column(ForeignKey("counties.id"))
    channel: Mapped[str] = mapped_column(String(10))
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    available_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    actor_label: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    facility_id: Mapped[str | None] = mapped_column(String(36), index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class SystemConfig(Base):
    __tablename__ = "system_config"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    updated_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
