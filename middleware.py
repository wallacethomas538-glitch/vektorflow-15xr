"""
VektorFlow 15xr - Middleware
Authentication and security middleware for FastAPI
"""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional
import os
import logging

logger = logging.getLogger("vektorflow")

# ============ API KEY MIDDLEWARE ============

class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to check for valid API key in request headers.
    Used to protect internal/admin endpoints.
    """
    
    def __init__(self, app, admin_key: str = None):
        super().__init__(app)
        self.admin_key = admin_key or os.environ.get("ADMIN_API_KEY", "vektorflow-admin-2026-secure-key")
    
    async def dispatch(self, request: Request, call_next):
        """
        Process the request and check API key for protected routes.
        """
        # Skip API key check for public endpoints
        public_paths = [
            "/",
            "/health",
            "/wakeup",
            "/docs",
            "/openapi.json",
            "/commander/login",
            "/auth/login",
            "/login",
            "/api/stripe/webhook"
        ]
        
        # Check if the path is public
        if request.url.path in public_paths:
            return await call_next(request)
        
        # Check for API key in headers
        api_key = request.headers.get("X-API-Key")
        
        if not api_key:
            # Also check Authorization header as fallback
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                api_key = auth_header.replace("Bearer ", "")
        
        if not api_key:
            logger.warning(f"Missing API key for {request.url.path}")
            raise HTTPException(status_code=401, detail="API key required")
        
        if api_key != self.admin_key:
            logger.warning(f"Invalid API key for {request.url.path}")
            raise HTTPException(status_code=403, detail="Invalid API key")
        
        # API key is valid, proceed
        return await call_next(request)


# ============ RATE LIMITING MIDDLEWARE ============

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple rate limiting middleware.
    """
    
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests = {}  # IP -> list of timestamps
    
    async def dispatch(self, request: Request, call_next):
        """
        Rate limit requests by IP address.
        """
        # Skip rate limiting for public health endpoints
        if request.url.path in ["/health", "/wakeup"]:
            return await call_next(request)
        
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        
        # Clean up old requests
        import time
        current_time = time.time()
        if client_ip in self.requests:
            # Remove timestamps older than 1 minute
            self.requests[client_ip] = [
                t for t in self.requests[client_ip]
                if current_time - t < 60
            ]
        else:
            self.requests[client_ip] = []
        
        # Check if rate limit exceeded
        if len(self.requests[client_ip]) >= self.requests_per_minute:
            logger.warning(f"Rate limit exceeded for {client_ip}")
            raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
        
        # Add current request timestamp
        self.requests[client_ip].append(current_time)
        
        return await call_next(request)


# ============ CORS MIDDLEWARE (Handled by FastAPI) ============

# This is handled directly in main.py with:
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# ============ LOGGING MIDDLEWARE ============

class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all incoming requests.
    """
    
    async def dispatch(self, request: Request, call_next):
        """
        Log request details and response time.
        """
        import time
        start_time = time.time()
        
        # Log request
        logger.info(f"Request: {request.method} {request.url.path}")
        
        # Process request
        response = await call_next(request)
        
        # Log response
        process_time = time.time() - start_time
        logger.info(f"Response: {response.status_code} - {process_time:.3f}s")
        
        return response
