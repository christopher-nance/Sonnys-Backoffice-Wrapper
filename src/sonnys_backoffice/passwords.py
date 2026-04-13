"""Password and PIN generators for newly-created users."""

from __future__ import annotations

import secrets
import string

_BO_PASSWORD_LENGTH = 12
_BO_SYMBOLS = "!@#$%^&*()_+=-[]{};:,.<>?"
_BO_ALPHABET = string.ascii_letters + string.digits + _BO_SYMBOLS


def generate_pos_pin() -> int:
    """Return a random 5-digit integer (10000-99999) suitable for POS login."""
    return secrets.randbelow(90000) + 10000


def generate_bo_password() -> str:
    """Return a 12-character password containing letters, digits, and at least one symbol."""
    while True:
        pw = "".join(secrets.choice(_BO_ALPHABET) for _ in range(_BO_PASSWORD_LENGTH))
        if (
            any(c.isalpha() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in _BO_SYMBOLS for c in pw)
        ):
            return pw
