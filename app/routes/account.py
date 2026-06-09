import logging

import bcrypt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import login_required
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/account", tags=["account"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
@login_required
async def account_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, request.state.user_id)
    return templates.TemplateResponse(
        request, "account/settings.html", {"user": user, "success": None, "error": None}
    )


@router.post("/profile")
@login_required
async def update_profile(request: Request, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, request.state.user_id)
    form_data = await request.form()
    name = form_data.get("name", "").strip()
    email = form_data.get("email", "").strip()
    default_currency = form_data.get("default_currency", "USD")

    if not name or not email:
        return templates.TemplateResponse(
            request, "account/settings.html",
            {"user": user, "success": None, "error": "Nickname and email are required."},
        )

    user.name = name
    user.email = email
    user.default_currency = default_currency
    await db.commit()
    await db.refresh(user)
    logger.info("Profile updated: user=%d", user.id)

    return templates.TemplateResponse(
        request, "account/settings.html",
        {"user": user, "success": "Profile updated.", "error": None},
    )


@router.post("/password")
@login_required
async def change_password(request: Request, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, request.state.user_id)
    form_data = await request.form()
    current_password = form_data.get("current_password", "")
    new_password = form_data.get("new_password", "")
    confirm_password = form_data.get("confirm_password", "")

    if not bcrypt.checkpw(current_password.encode(), user.password_hash.encode()):
        return templates.TemplateResponse(
            request, "account/settings.html",
            {"user": user, "success": None, "error": "Current password is incorrect."},
        )

    if len(new_password) < 8:
        return templates.TemplateResponse(
            request, "account/settings.html",
            {"user": user, "success": None, "error": "New password must be at least 8 characters."},
        )

    if new_password != confirm_password:
        return templates.TemplateResponse(
            request, "account/settings.html",
            {"user": user, "success": None, "error": "Passwords do not match."},
        )

    hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    user.password_hash = hashed
    await db.commit()
    logger.info("Password changed: user=%d", user.id)

    return templates.TemplateResponse(
        request, "account/settings.html",
        {"user": user, "success": "Password changed.", "error": None},
    )
