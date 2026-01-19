"""
Webhook Signature Verification

Utilities for verifying HMAC SHA256 signatures from ARRMS webhooks.
Ensures webhook payloads are authentic and haven't been tampered with.
"""

import hashlib
import hmac
import json
from typing import Any, Dict


def verify_webhook_signature(payload: Dict[str, Any], signature: str, secret: str) -> bool:
    """
    Verify HMAC SHA256 signature from ARRMS webhook.

    ARRMS signs webhook payloads using HMAC SHA256 with a shared secret.
    The signature is sent in the X-Webhook-Signature header as "sha256=<hex_digest>".

    Args:
        payload: Webhook payload dictionary
        signature: Signature from X-Webhook-Signature header (e.g., "sha256=abc123...")
        secret: Shared webhook secret configured in ARRMS

    Returns:
        True if signature is valid, False otherwise

    Example:
        >>> payload = {"event_type": "questionnaire.response_approved", ...}
        >>> signature = "sha256=a1b2c3..."
        >>> secret = "my-shared-secret"
        >>> is_valid = verify_webhook_signature(payload, signature, secret)
    """
    if not signature or not secret:
        return False

    # Remove 'sha256=' prefix if present
    if signature.startswith("sha256="):
        signature = signature[7:]

    # Calculate expected signature
    # ARRMS uses compact JSON (no spaces) with sorted keys for consistency
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    expected = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()

    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(expected, signature)


def extract_signature(headers: Dict[str, str]) -> str:
    """
    Extract webhook signature from request headers.

    Handles case-insensitive header lookups for API Gateway events.

    Args:
        headers: Request headers dictionary

    Returns:
        Signature string or empty string if not found
    """
    # Try exact case first
    signature = headers.get("X-Webhook-Signature", "")

    # Try lowercase (API Gateway normalizes headers)
    if not signature:
        signature = headers.get("x-webhook-signature", "")

    return signature
