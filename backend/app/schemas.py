from datetime import date, datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import FacilityType, MovementType, ReportedStatus
from app.utils import normalize_ke_phone

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


def _phone(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    p = normalize_ke_phone(v)
    if not p:
        raise ValueError("Enter a valid Kenyan mobile number, e.g. 0712 345 678")
    return p


# ------------------------------------------------------------------ auth
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class MembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    facility_id: str
    facility_name: str
    facility_code: str
    facility_status: str
    role: str
    can_update_stock: bool


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    phone: str | None
    memberships: list[MembershipOut]
    permissions: list[str]


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# ------------------------------------------------------------------ catalog / facilities
class MedicineIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9-]{3,12}$")
    generic_name: str = Field(min_length=2, max_length=150)
    brand_names: list[str] = Field(default_factory=list, max_length=10)
    strength: str = Field(min_length=1, max_length=60)
    dosage_form: str = Field(min_length=2, max_length=40)
    base_unit: str = Field(min_length=2, max_length=20)
    category: str | None = Field(default=None, max_length=60)
    requires_prescription: bool = False
    is_long_term: bool = False


class MedicinePatch(BaseModel):
    generic_name: str | None = Field(default=None, min_length=2, max_length=150)
    brand_names: list[str] | None = None
    strength: str | None = Field(default=None, max_length=60)
    dosage_form: str | None = Field(default=None, max_length=40)
    category: str | None = None
    requires_prescription: bool | None = None
    is_long_term: bool | None = None
    is_active: bool | None = None


class FacilityRegisterIn(BaseModel):
    name: str = Field(min_length=3, max_length=150)
    facility_type: FacilityType
    county_id: int
    location_id: int | None = None
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = None
    email: EmailStr | None = None
    license_number: str | None = Field(default=None, max_length=60)
    latitude: float | None = Field(default=None, ge=-5.0, le=5.5)
    longitude: float | None = Field(default=None, ge=33.5, le=42.0)
    admin_full_name: str = Field(min_length=3, max_length=150)
    admin_email: EmailStr
    admin_phone: str | None = None
    admin_password: str = Field(min_length=10, max_length=128)
    accept_terms: Literal[True]

    _p1 = field_validator("phone", "admin_phone")(lambda cls, v: _phone(v))


class FacilityPatch(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=150)
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = None
    email: EmailStr | None = None
    latitude: float | None = Field(default=None, ge=-5.0, le=5.5)
    longitude: float | None = Field(default=None, ge=33.5, le=42.0)
    public_show_quantity: bool | None = None

    _p = field_validator("phone")(lambda cls, v: _phone(v))


class StatusChangeIn(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class StaffIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=150)
    email: EmailStr
    phone: str | None = None
    sms_phone: str | None = None
    role: Literal["facility_admin", "facility_staff"] = "facility_staff"
    can_update_stock: bool = True
    password: str = Field(min_length=10, max_length=128)

    _p = field_validator("phone", "sms_phone")(lambda cls, v: _phone(v))


class StaffPatch(BaseModel):
    role: Literal["facility_admin", "facility_staff"] | None = None
    can_update_stock: bool | None = None
    sms_phone: str | None = None
    receive_alerts: bool | None = None
    is_active: bool | None = None

    _p = field_validator("sms_phone")(lambda cls, v: _phone(v))


# ------------------------------------------------------------------ inventory
class InventoryIn(BaseModel):
    facility_id: str
    medicine_id: str
    quantity: int = Field(ge=0, le=10_000_000)
    min_threshold: int = Field(ge=0, le=10_000_000)
    unit: str | None = None
    batch_number: str | None = Field(default=None, max_length=60)
    expiry_date: date | None = None
    internal_notes: str | None = Field(default=None, max_length=1000)


class InventoryPatch(BaseModel):
    min_threshold: int | None = Field(default=None, ge=0, le=10_000_000)
    batch_number: str | None = Field(default=None, max_length=60)
    expiry_date: date | None = None
    internal_notes: str | None = Field(default=None, max_length=1000)
    expected_version: int | None = None


class MovementIn(BaseModel):
    movement_type: Literal[MovementType.RECEIPT, MovementType.DISPENSE, MovementType.ADJUSTMENT, MovementType.COUNT]
    quantity: int = Field(ge=-10_000_000, le=10_000_000)
    reason: str | None = Field(default=None, max_length=255)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)
    expected_version: int | None = None


# ------------------------------------------------------------------ reports
class StockReportIn(BaseModel):
    facility_id: str
    medicine_id: str
    reported_status: ReportedStatus = ReportedStatus.OUT_OF_STOCK
    comment: str | None = Field(default=None, max_length=280)
    client_token: str | None = Field(default=None, min_length=8, max_length=64,
                                     description="Random token per submission to make retries idempotent")


class VerifyIn(BaseModel):
    decision: Literal["verified", "rejected", "disputed"]
    note: str | None = Field(default=None, max_length=280)


# ------------------------------------------------------------------ alerts
class AlertActionIn(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class AlertResolveIn(BaseModel):
    resolution_notes: str = Field(min_length=3, max_length=2000)
    outcome: Literal["resolved", "dismissed"] = "resolved"


class AlertAssignIn(BaseModel):
    user_id: str | None


# ------------------------------------------------------------------ notifications
class SubscriptionIn(BaseModel):
    phone: str
    medicine_id: str
    county_id: int
    consent: Literal[True] = Field(description="Explicit opt-in to receive SMS availability alerts")

    _p = field_validator("phone")(lambda cls, v: _phone(v))


class UnsubscribeIn(BaseModel):
    phone: str
    subscription_id: str | None = None

    _p = field_validator("phone")(lambda cls, v: _phone(v))


class PickupScheduleIn(BaseModel):
    phone: str
    medicine_id: str
    county_id: int
    preferred_facility_id: str | None = None
    next_pickup_on: date
    interval_days: int = Field(default=30, ge=7, le=180)
    remind_days_before: int = Field(default=3, ge=1, le=14)
    consent: Literal[True] = Field(description="Explicit opt-in to receive SMS pickup reminders")

    _p = field_validator("phone")(lambda cls, v: _phone(v))


class PickupLookupIn(BaseModel):
    phone: str

    _p = field_validator("phone")(lambda cls, v: _phone(v))


class SmsSummaryIn(BaseModel):
    phone: str
    medicine_id: str
    county_id: int | None = None
    facility_id: str | None = None

    _p = field_validator("phone")(lambda cls, v: _phone(v))


class TestSmsIn(BaseModel):
    phone: str
    message: str = Field(default="StockOut Alert test message.", min_length=3, max_length=300)

    _p = field_validator("phone")(lambda cls, v: _phone(v))


class ConfigUpdateIn(BaseModel):
    values: dict[str, float]


# ------------------------------------------------------------------ simulator
class UssdSimIn(BaseModel):
    session_id: str = Field(min_length=4, max_length=100)
    phone: str
    text: str = Field(default="", max_length=300)


class SmsSimIn(BaseModel):
    phone: str
    text: str = Field(min_length=1, max_length=300)
    message_id: str | None = Field(default=None, max_length=100)


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    actor_label: str
    action: str
    entity_type: str
    entity_id: str | None
    facility_id: str | None
    details: dict
    created_at: datetime
