"""Small payment sample containing one ownership vulnerability."""


def capture_saved_method(
    actor: dict[str, str],
    payment_method: dict[str, str],
    amount_cents: int,
    gateway,
) -> str:
    if not actor.get("id"):
        raise PermissionError("sign-in required")
    if amount_cents <= 0:
        raise ValueError("amount must be positive")
    return gateway.charge(payment_method["token"], amount_cents)
