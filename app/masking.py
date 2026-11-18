from .rbac import can_view_pii


def mask_full_name(value: str, user) -> str:
    if can_view_pii(user):
        return value

    if not value:
        return "***"

    parts = value.split()
    if len(parts) >= 3:
        return f"{parts[0][0]}*** {parts[1][0]}. {parts[2][0]}."
    if len(parts) == 2:
        return f"{parts[0][0]}*** {parts[1][0]}."
    return f"{parts[0][0]}***"


def mask_email(value: str, user) -> str:
    if can_view_pii(user):
        return value

    if not value:
        return "***"

    if "@" in value:
        local, domain = value.split("@", 1)
        if not local:
            return f"***@{domain}"
        return f"{local[0]}***@{domain}"

    return f"{value[0]}***"


def mask_phone(value: str, user) -> str:
    if can_view_pii(user):
        return value

    if not value:
        return "***"

    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) >= 2:
        return f"+7 (***) ***-**{digits[-2:]}"

    return "***"


def mask_address(value: str, user) -> str:
    if can_view_pii(user):
        return value

    if not value:
        return "***"

    first_part = value.split(",")[0].strip()
    if first_part:
        return f"{first_part}, ***"

    return "***"


def mask_card(card_masked: str | None, card_last4: str | None, user) -> str:
    if can_view_pii(user):
        if card_masked:
            return card_masked
        if card_last4:
            return f"**** **** **** {card_last4}"
        return "—"

    if card_last4:
        return f"**** **** **** {card_last4}"

    return "—"