"""Public API with one used and one unused function."""


def active_handler(order_id: str) -> str:
    return f"order:{order_id}"


def legacy_export(rows: list[dict]) -> str:
    return "\n".join(str(row) for row in rows)
