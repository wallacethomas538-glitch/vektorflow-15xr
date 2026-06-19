"""
VektorFlow 15xr - Authentication Module
Handles JWT token creation, verification, and password management
"""

import os
import jwt
import bcrypt
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, status

# ============ CONFIGURATION ============
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "vektorflow-15xr-super-secret-key-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# ============ TOKEN FUNCTIONS ============

def create_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT token with the given data.
    
    Args:
        data: Dictionary of data to encode in the token
        expires_delta: Optional custom expiration time
    
    Returns:
        JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
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

def get_current_user(token: str) -> Optional[Dict[str, Any]]:
    """
    Get the current user from a token.
    
    Args:
        token: JWT token string
    
    Returns:
        User data from token if valid, None otherwise
    """
    payload = verify_token(token)
    if not payload:
        return None
    
    return {
        "email": payload.get("email"),
        "role": payload.get("role", "user"),
        "permissions": payload.get("permissions", [])
    }

# ============ PASSWORD FUNCTIONS ============

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: Plain text password
    
    Returns:
        Hashed password string
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.
    
    Args:
        plain_password: Plain text password
        hashed_password: Hashed password string
    
    Returns:
        True if password matches, False otherwise
    """
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

# ============ VALIDATION FUNCTIONS ============

def validate_email(email: str) -> bool:
    """
    Validate email format.
    
    Args:
        email: Email address to validate
    
    Returns:
        True if valid, False otherwise
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password_strength(password: str) -> bool:
    """
    Validate password strength.
    
    Args:
        password: Password to validate
    
    Returns:
        True if strong enough, False otherwise
    """
    if len(password) < 8:
        return False
    if not re.search(r'[A-Z]', password):
        return False
    if not re.search(r'[a-z]', password):
        return False
    if not re.search(r'[0-9]', password):
        return False
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False
    return True

# ============ MIDDLEWARE HELPER ============

def get_token_from_header(authorization: Optional[str]) -> Optional[str]:
    """
    Extract JWT token from Authorization header.
    
    Args:
        authorization: Authorization header value (e.g., "Bearer <token>")
    
    Returns:
        Token string if found, None otherwise
    """
    if not authorization:
        return None
    
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    
    return parts[1]

def authenticate_user(email: str, password: str, get_user_func) -> Optional[Dict]:
    """
    Authenticate a user by email and password.
    
    Args:
        email: User's email
        password: User's password (plain text)
        get_user_func: Function to get user from database
    
    Returns:
        User dict if authenticated, None otherwise
    """
    user = get_user_func(email)
    if not user:
        return None
    
    # Check if password is stored as hash or plain text
    stored_password = user.get("password_hash") or user.get("password")
    if not stored_password:
        return None
    
    # Try bcrypt verification first
    if verify_password(password, stored_password):
        return user
    
    # Fallback to plain text comparison (for backward compatibility)
    if password == stored_password:
        return user
    
    return None

# ============ DEPENDENCIES FOR FASTAPI ============

class AuthDependency:
    """Dependency class for FastAPI route authentication"""
    
    @staticmethod
    async def require_auth(token: str = None):
        """
        Dependency that requires a valid JWT token.
        
        Usage:
            @app.get("/protected")
            async def protected_route(user: dict = Depends(AuthDependency.require_auth)):
                return {"user": user}
        """
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        payload = verify_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return payload
    
    @staticmethod
    async def require_admin(token: str = None):
        """
        Dependency that requires an admin JWT token.
        
        Usage:
            @app.get("/admin")
            async def admin_route(user: dict = Depends(AuthDependency.require_admin)):
                return {"user": user}
        """
        payload = await AuthDependency.require_auth(token)
        
        if payload.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required"
            )
        
        return payload

# ============ TOKEN REFRESH ============

def refresh_token(token: str) -> Optional[str]:
    """
    Refresh an expired token if it's still valid (not tampered).
    
    Args:
        token: Expired JWT token
    
    Returns:
        New JWT token if refreshable, None otherwise
    """
    try:
        # Decode without verifying expiration
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
        
        # Check if token is expired
        exp = payload.get("exp")
        if exp and datetime.utcnow().timestamp() > exp:
            # Token is expired, but we can refresh it
            payload.pop("exp", None)
            return create_token(payload)
        
        # Token is not expired, return it as is
        return token
        
    except jwt.InvalidTokenError:
        return None

# ============ TEST HELPERS ============

def generate_test_token(email: str = "test@example.com", role: str = "user") -> str:
    """
    Generate a test token for development.
    
    Args:
        email: Email to encode
        role: Role to assign
    
    Returns:
        JWT token string
    """
    return create_token({
        "email": email,
        "role": role,
        "permissions": ["test_access"]
    })

# ============ INITIALIZATION ============

print("✅ Authentication module loaded successfully")
print(f"   JWT Algorithm: {ALGORITHM}")
print(f"   Token expiry: {ACCESS_TOKEN_EXPIRE_MINUTES} minutes")