from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FacilityMembership, RevokedToken, User, UserRole
from app.permissions import has_permission
from app.security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_token_payload(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    payload = decode_token(creds.credentials)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return payload


def get_current_user(payload: dict = Depends(get_token_payload), db: Session = Depends(get_db)) -> User:
    if db.get(RevokedToken, payload.get("jti", "")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session has been signed out")
    user = db.get(User, payload.get("sub", ""))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found or inactive")
    return user


def require(permission: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission for this action")
        return user

    return checker


def is_system_admin(user: User) -> bool:
    return user.role == UserRole.SYSTEM_ADMIN


def membership_for(db: Session, user: User, facility_id: str) -> FacilityMembership | None:
    return (
        db.query(FacilityMembership)
        .filter(FacilityMembership.user_id == user.id, FacilityMembership.facility_id == facility_id)
        .one_or_none()
    )


def accessible_facility_ids(db: Session, user: User) -> list[str] | None:
    """None means unrestricted (system admin)."""
    if is_system_admin(user):
        return None
    return [m.facility_id for m in db.query(FacilityMembership).filter(FacilityMembership.user_id == user.id)]


def assert_facility_access(db: Session, user: User, facility_id: str, *, need_stock: bool = False,
                           need_admin: bool = False) -> None:
    if is_system_admin(user):
        return
    m = membership_for(db, user, facility_id)
    # 404 rather than 403 so other facilities' existence is not leaked.
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Facility not found")
    if need_admin and m.role != UserRole.FACILITY_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Facility administrator role required")
    if need_stock and not m.can_update_stock:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not permitted to update stock")
