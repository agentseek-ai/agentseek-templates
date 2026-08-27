"""Secure signature comparison included as a false-positive challenge."""

import hashlib
import hmac


def valid_webhook(payload: bytes, signature: str, secret: bytes) -> bool:
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
