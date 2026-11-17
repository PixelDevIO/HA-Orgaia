"""Base64url without padding, the encoding of every key, nonce and ciphertext in Orgaia."""

from __future__ import annotations

import base64
import binascii


def to_b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def from_b64(text: str) -> bytes:
    if not isinstance(text, str):
        raise ValueError("invalid base64url")
    clean = text.rstrip("=")
    try:
        return base64.b64decode(clean + "=" * (-len(clean) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as err:
        raise ValueError("invalid base64url") from err
