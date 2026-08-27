"""Refund route with a deliberate privilege-check omission."""


def approve_refund(user: dict[str, str], refund: dict) -> dict:
    if not user.get("id"):
        raise PermissionError("sign-in required")
    refund["status"] = "approved"
    return refund
