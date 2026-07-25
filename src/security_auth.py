"""Authentication utilities."""

import secrets
import hashlib


def generate_api_key() -> str:
    return f"vektor_{secrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token(token: str, stored_hash: str) -> bool:
    return hash_token(token) == stored_hash