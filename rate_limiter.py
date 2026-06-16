"""
Rate Limiter - Enforces request limits per user and IP
"""

import time
import os
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

# ========== CONFIG ==========
RATE_LIMITS = {
    "trial": {"requests": 50, "window": 3600},
    "paid": {"requests": 1000, "window": 3600},
    "anonymous": {"requests": 30, "window": 3600},
    "admin": {"requests": 5000, "window": 3600},
}

request_store = defaultdict(list)

def get_user_tier(email: str = None, api_key: str = None) -> str:
    if api_key and api_key == os.environ.get("ADMIN_API_KEY"):
        return "admin"
    return "trial"

def is_rate_limited(key: str, tier: str = "trial") -> tuple:
    now = time.time()
    limit_config = RATE_LIMITS.get(tier, RATE_LIMITS["trial"])
    max_requests = limit_config["requests"]
    window_seconds = limit_config["window"]
    
    request_store[key] = [t for t in request_store[key] if t > now - window_seconds]
    
    if len(request_store[key]) >= max_requests:
        oldest_request = min(request_store[key]) if request_store[key] else now
        retry_after = int((oldest_request + window_seconds) - now)
        if retry_after < 1:
            retry_after = 1
        return True, 0, retry_after
    
    request_store[key].append(now)
    remaining = max_requests - len(request_store[key])
    return False, remaining, 0

def rate_limit(tier: str = None):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if not request and 'request' in kwargs:
                request = kwargs['request']
            
            key = None
            actual_tier = tier or "trial"
            
            if request:
                email = getattr(request.state, 'email', None)
                api_key = request.headers.get('api-key') or request.headers.get('Authorization')
                
                if email:
                    key = f"user_{email}"
                    actual_tier = get_user_tier(email)
                elif api_key:
                    key = f"apikey_{api_key[:10]}"
                    actual_tier = get_user_tier(api_key=api_key)
                else:
                    client_ip = request.client.host if request.client else "unknown"
                    key = f"ip_{client_ip}"
                    actual_tier = "anonymous"
            
            if not key:
                key = "anonymous_default"
                actual_tier = "anonymous"
            
            is_limited, remaining, retry_after = is_rate_limited(key, actual_tier)
            
            if is_limited:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "message": f"Too many requests. Please wait {retry_after} seconds.",
                        "retry_after": retry_after,
                        "tier": actual_tier,
                        "limit": RATE_LIMITS.get(actual_tier, RATE_LIMITS["trial"])["requests"],
                        "window": RATE_LIMITS.get(actual_tier, RATE_LIMITS["trial"])["window"] // 60
                    }
                )
            
            response = await func(*args, **kwargs)
            
            if hasattr(response, 'headers'):
                response.headers['X-RateLimit-Limit'] = str(RATE_LIMITS.get(actual_tier, RATE_LIMITS["trial"])["requests"])
                response.headers['X-RateLimit-Remaining'] = str(remaining)
                response.headers['X-RateLimit-Window'] = str(RATE_LIMITS.get(actual_tier, RATE_LIMITS["trial"])["window"])
            
            return response
        return wrapper
    return decorator

async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/static/") or request.url.path == "/":
        return await call_next(request)
    
    skip_paths = ["/health", "/setup-create-user", "/debug/check-env", "/store/initiate", "/store/callback"]
    if request.url.path in skip_paths:
        return await call_next(request)
    
    email = getattr(request.state, 'email', None)
    api_key = request.headers.get('api-key') or request.headers.get('Authorization')
    
    if email:
        key = f"user_{email}"
        tier = get_user_tier(email)
    elif api_key:
        key = f"apikey_{api_key[:10]}"
        tier = get_user_tier(api_key=api_key)
    else:
        client_ip = request.client.host if request.client else "unknown"
        key = f"ip_{client_ip}"
        tier = "anonymous"
    
    is_limited, remaining, retry_after = is_rate_limited(key, tier)
    
    if is_limited:
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": f"Too many requests. Please wait {retry_after} seconds.",
                "retry_after": retry_after
            }
        )
    
    response = await call_next(request)
    response.headers['X-RateLimit-Limit'] = str(RATE_LIMITS.get(tier, RATE_LIMITS["trial"])["requests"])
    response.headers['X-RateLimit-Remaining'] = str(remaining)
    
    return response
