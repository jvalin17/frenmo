import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.email import send_reset_email
from app.services.password_reset import generate_reset_token, reset_password, validate_reset_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["password-reset"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(
        request, "auth/forgot_password.html", {"sent": False, "error": None}
    )


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password(request: Request, db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    email = form_data.get("email", "").strip().lower()

    if not email:
        return templates.TemplateResponse(
            request, "auth/forgot_password.html", {"sent": False, "error": "Email is required."}
        )

    token = await generate_reset_token(db, email)
    if token:
        reset_url = f"{request.base_url}auth/reset-password?token={token}"
        await send_reset_email(email, reset_url)
        logger.info("Password reset requested for %s", email)

    # Always show success (don't reveal if email exists)
    return templates.TemplateResponse(
        request, "auth/forgot_password.html", {"sent": True, "error": None}
    )


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str = ""):
    if not token or validate_reset_token(token) is None:
        return templates.TemplateResponse(
            request, "auth/reset_password.html",
            {"valid": False, "token": "", "success": False, "error": "Invalid or expired reset link."},
        )
    return templates.TemplateResponse(
        request, "auth/reset_password.html",
        {"valid": True, "token": token, "success": False, "error": None},
    )


@router.post("/reset-password", response_class=HTMLResponse)
async def do_reset_password(request: Request, db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    token = form_data.get("token", "")
    new_password = form_data.get("new_password", "")
    confirm_password = form_data.get("confirm_password", "")

    if new_password != confirm_password:
        return templates.TemplateResponse(
            request, "auth/reset_password.html",
            {"valid": True, "token": token, "success": False, "error": "Passwords do not match."},
        )

    result = await reset_password(db, token, new_password)
    if not result:
        return templates.TemplateResponse(
            request, "auth/reset_password.html",
            {"valid": True, "token": token, "success": False, "error": "Invalid token or password too short (min 8 chars)."},
        )

    logger.info("Password reset completed")
    return templates.TemplateResponse(
        request, "auth/reset_password.html",
        {"valid": False, "token": "", "success": True, "error": None},
    )
