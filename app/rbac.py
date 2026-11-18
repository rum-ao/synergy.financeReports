ADMIN = "admin"
SENIOR_FINANCE = "senior_finance"
FINANCE_INTERN = "finance_intern"

ROLE_LABELS = {
    ADMIN: "Администратор",
    SENIOR_FINANCE: "Старший финансист",
    FINANCE_INTERN: "Финансист-практикант",
}

ALLOWED_ROLES = set(ROLE_LABELS.keys())

PII_ROLES = {ADMIN, SENIOR_FINANCE}
EXPORT_ROLES = {ADMIN, SENIOR_FINANCE}
MANAGE_USERS_ROLES = {ADMIN}
AUDIT_ROLES = {ADMIN}


def can_view_pii(user) -> bool:
    return bool(user and user.role in PII_ROLES)


def can_export(user) -> bool:
    return bool(user and user.role in EXPORT_ROLES)


def can_manage_users(user) -> bool:
    return bool(user and user.role in MANAGE_USERS_ROLES)


def can_view_audit(user) -> bool:
    return bool(user and user.role in AUDIT_ROLES)