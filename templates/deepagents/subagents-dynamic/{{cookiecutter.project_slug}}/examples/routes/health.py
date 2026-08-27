"""Public liveness probe: intentionally anonymous and data-free."""


def get_health() -> dict[str, str]:
    return {"status": "ok"}
