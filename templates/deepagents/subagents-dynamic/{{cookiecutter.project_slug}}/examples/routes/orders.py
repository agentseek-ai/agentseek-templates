"""Order lookup with a deliberate object-level authorization defect."""


def get_order(user: dict[str, str], order_id: str, orders: dict[str, dict]) -> dict:
    if not user.get("id"):
        raise PermissionError("sign-in required")
    return orders[order_id]
