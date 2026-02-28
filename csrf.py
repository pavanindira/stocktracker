"""
Custom CSRF middleware for Starlette/FastAPI.
This provides CSRF protection for forms when using session-based authentication.
"""
import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, HTMLResponse


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """
    Simple CSRF middleware that:
    1. Generates CSRF token on GET requests
    2. Validates CSRF token on POST/PUT/DELETE requests
    """
    
    def __init__(self, app, secret_key: str):
        super().__init__(app)
        self.secret_key = secret_key
    
    async def dispatch(self, request: Request, call_next):
        # Skip CSRF for GET requests - just ensure token exists
        if request.method == "GET":
            # Generate token if not exists
            if "csrf_token" not in request.session:
                request.session["csrf_token"] = secrets.token_hex(32)
            return await call_next(request)
        
        # For POST/PUT/DELETE, validate CSRF token
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            # Skip for API endpoints that might not have sessions
            if request.url.path.startswith("/api"):
                return await call_next(request)
            
            # Get token from form or header
            form = await request.form()
            csrf_token = form.get("csrf_token") if form else None
            
            # Also check header
            if not csrf_token:
                csrf_token = request.headers.get("X-CSRFToken")
            
            # Validate
            session_token = request.session.get("csrf_token")
            if not csrf_token or csrf_token != session_token:
                # Return CSRF error
                return HTMLResponse(
                    content="<html><body><h1>CSRF Validation Failed</h1><p>Please refresh the page and try again.</p></body></html>",
                    status_code=403
                )
        
        return await call_next(request)
