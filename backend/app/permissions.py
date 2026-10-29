"""Role -> permission mapping. This is the source of truth; the roles/role_permissions
tables are synchronised from it at seed time so they can be inspected and audited."""

from app.models import UserRole

ROLE_DESCRIPTIONS = {
    UserRole.SYSTEM_ADMIN: "Platform administrator: approves facilities, manages catalog, monitors alerts",
    UserRole.FACILITY_ADMIN: "Manages a facility profile, its staff and inventory",
    UserRole.FACILITY_STAFF: "Records stock for facilities they are a member of",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    UserRole.SYSTEM_ADMIN: {
        "facility.approve",
        "facility.view_all",
        "facility.manage",
        "staff.manage",
        "catalog.manage",
        "inventory.view",
        "inventory.update",
        "reports.verify",
        "alerts.view",
        "alerts.manage",
        "ripple.manage",
        "audit.view",
        "config.manage",
        "notifications.view",
        "notifications.test",
        "demo.reset",
    },
    UserRole.FACILITY_ADMIN: {
        "facility.manage",
        "staff.manage",
        "inventory.view",
        "inventory.update",
        "reports.verify",
        "alerts.view",
        "alerts.manage",
        "notifications.view",
        "inventory.export",
    },
    UserRole.FACILITY_STAFF: {
        "inventory.view",
        "inventory.update",
        "alerts.view",
        "alerts.manage",
    },
}


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())
