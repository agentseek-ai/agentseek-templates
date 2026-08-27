"""Helpers with one live formatter and one abandoned diagnostic."""


def format_total(cents: int) -> str:
    return f"${cents / 100:.2f}"


def debug_dump(order: dict) -> str:
    return repr(sorted(order.items()))
