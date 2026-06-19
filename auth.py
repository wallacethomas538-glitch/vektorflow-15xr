"""
VektorFlow 15xr - Authentication Module
"""

import os
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

# ============ CONFIGURATION ============
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "vektorflow-15xr-super-secret-key-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# ============ TOKEN FUNCTIONS ============

def create_token(data: Dict[str, Any]) -> str:
    """
    Create a JWT token with the given data.
    
    Args:
        data: Dictionary of data to encode in the token
    
    Returns:
        JWT token string
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode a JWT token.
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded token data if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Alias for verify_token - decodes and verifies a JWT token.
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded token data if valid, None otherwise
    """
    return verify_token(token)

# ============ PASSWORD FUNCTIONS ============

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    try:
        import bcrypt
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    except ImportError:
        # Fallback if bcrypt not installed
        return password

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    try:
        import bcrypt
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ImportError:
        # Fallback if bcrypt not installed
        return plain_password == hashed_password