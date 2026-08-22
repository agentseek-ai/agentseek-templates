"""Administrative route with an explicit role check."""


def list_audit_events(user: dict[str, str], events: list[dict]) -> list[dict]:
    if user.get("role") != "admin":
        raise PermissionError("admin role required")
    return events
