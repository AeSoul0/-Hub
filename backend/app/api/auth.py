"""
@file backend/app/api/auth.py
@description Implements auth.py. Core components: general logic modules.

This module manages the internal business logic for general logic modules.
It provides specialized functionality to handle: login, logout, verify_auth.
"""
import os
from fastapi import APIRouter, Request, Response, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import IdentityService
from app.domain.models.identity import User, Workspace, WorkspaceMembership, RoleEnum
from app.core.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

from app.core.cache import CacheService

@router.post("/login")
async def login(request: Request, response: Response, db: Session = Depends(get_db)):

    client_ip = request.client.host if request.client else "unknown"
    is_allowed = await CacheService.check_rate_limit(
        identifier=f"login:{client_ip}",
        limit=5,
        window_seconds=300
    )
    if not is_allowed:
        return JSONResponse(status_code=429, content={"detail": "Too Many Requests. Login rate limit exceeded."})
        
    data = await request.json()
    if data.get("key") == settings.AEHUB_SECRET_KEY:
        # Check if admin user exists, if not create it (LAN-first bootstrapping)
        user = db.query(User).filter(User.username == "admin").first()
        workspace = db.query(Workspace).filter(Workspace.name == "default").first()
        
        if not workspace:
            workspace = Workspace(id="default-workspace", name="default")
            db.add(workspace)
            
        if not user:
            import hashlib
            hashed_pw = hashlib.sha256(settings.AEHUB_SECRET_KEY.encode()).hexdigest()
            user = User(username="admin", hashed_password=hashed_pw)
            db.add(user)
            db.flush()
            member = WorkspaceMembership(user_id=user.id, workspace_id=workspace.id, role=RoleEnum.ADMIN)
            db.add(member)
        db.commit()
        
        session_token = IdentityService.create_session(
            db=db, 
            user_id=user.id, 
            workspace_id=workspace.id, 
            role=RoleEnum.ADMIN
        )
        
        # Set HttpOnly cookie for session
        response_obj = JSONResponse(content={"status": "ok", "session_token": session_token})
        is_prod = os.getenv("ENVIRONMENT", "development") == "production"
        response_obj.set_cookie(key="aehub_session_token", value=session_token, httponly=True, samesite="lax", secure=is_prod)
        return response_obj
    return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

@router.post("/logout")
async def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    cookie_token = request.cookies.get("aehub_session_token")
    if cookie_token:
        IdentityService.invalidate_session(db, cookie_token)
        
    response_obj = JSONResponse(content={"status": "ok"})
    response_obj.delete_cookie("aehub_session_token")
    return response_obj

@router.get("/verify")
async def verify_auth(request: Request):
    """
    Executes verify_auth logic.
    """
    # If it reaches here, the middleware has already approved it.
    return {"status": "ok"}
