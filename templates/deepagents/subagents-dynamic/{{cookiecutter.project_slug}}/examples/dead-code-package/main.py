"""Only these imports make up the live sample path."""

from api import active_handler
from helpers import format_total


def render_order(order_id: str, cents: int) -> str:
    return f"{active_handler(order_id)} · {format_total(cents)}"
