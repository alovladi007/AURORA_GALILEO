from fastapi import Request, Response
from typing import Callable
import json
import logging
from datetime import datetime
from ops.models import SessionLocal, AuditLog
from jose import jwt
import os

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"

async def audit_log_middleware(request: Request, call_next: Callable) -> Response:
    """Middleware to log all API requests for audit trail"""
    
    # Skip logging for health checks and docs
    if request.url.path in ["/health", "/docs", "/openapi.json", "/favicon.ico"]:
        return await call_next(request)
    
    # Extract user info from token if present
    user_id = None
    authorization = request.headers.get("Authorization")
    if authorization and authorization.startswith("Bearer "):
        try:
            token = authorization.split(" ")[1]
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            
            # Get user ID from username
            db = SessionLocal()
            from models import User
            user = db.query(User).filter(User.username == username).first()
            if user:
                user_id = user.id
            db.close()
        except Exception as e:
            logger.debug(f"Could not extract user from token: {e}")
    
    # Get request details
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent", "")
    
    # Process request and response
    start_time = datetime.utcnow()
    response = await call_next(request)
    duration = (datetime.utcnow() - start_time).total_seconds()
    
    # Determine action based on method and path
    action = f"{request.method} {request.url.path}"
    
    # Extract resource info from path (if applicable)
    resource_type = None
    resource_id = None
    
    path_parts = request.url.path.strip("/").split("/")
    if len(path_parts) >= 2:
        if path_parts[0] == "ops":
            resource_type = path_parts[1]
            if len(path_parts) > 2:
                resource_id = path_parts[2]
    
    # Create audit log entry
    try:
        db = SessionLocal()
        audit_log = AuditLog(
            timestamp=start_time,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details={
                "method": request.method,
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "status_code": response.status_code,
                "duration_seconds": duration
            },
            ip_address=client_ip,
            user_agent=user_agent
        )
        db.add(audit_log)
        db.commit()
        db.close()
    except Exception as e:
        logger.error(f"Failed to create audit log: {e}")
    
    return response
