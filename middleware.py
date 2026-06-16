"""
Subscription middleware - Checks payment status before every request
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from database import check_and_block_access, get_subscription, get_user
import jwt
import os

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change_me")
ALGORITHM = "HS256"

PUBLIC_PATHS = ["/health", "/", "/static/", "/auth/signup", "/auth/login", "/setup-create-user", "/store/callback", "/store/initiate"]

async def subscription_middleware(request: Request, call_next):
    """Check subscription status before processing requests"""
    
    # Skip public endpoints
    for path in PUBLIC_PATHS:
        if request.url.path.startswith(path):
            return await call_next(request)
    
    # Check for auth token
    auth_header = request.headers.get("api-key") or request.headers.get("Authorization")
    if not auth_header:
        return await call_next(request)
    
    try:
        token = auth_header.replace("Bearer ", "")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("email")
        
        if email and not check_and_block_access(email):
            user = get_user(email)
            sub = get_subscription(email)
            return JSONResponse(
                status_code=402,
                content={
                    "error": "Payment Required",
                    "message": "Your trial has expired. Please upgrade to continue.",
                    "status": "expired",
                    "renew_url": "/payment/checkout"
                }
            )
    except:
        pass
    
    return await call_next(request)
