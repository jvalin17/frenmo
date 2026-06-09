import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import clear_session_cookie, get_current_user_id, set_session_cookie
from app.models.user import User
from app.services.auth import hash_password, verify_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_current_user_id(request) is not None:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "auth/login.html", {"user": None})


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == email.lower().strip()))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        logger.info("Failed login attempt for email=%s", email)
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"user": None, "error": "Invalid email or password"},
            status_code=401,
        )

    logger.info("Successful login for user_id=%d", user.id)
    response = RedirectResponse(url="/", status_code=303)
    set_session_cookie(response, user.id)
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if get_current_user_id(request) is not None:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "auth/register.html", {"user": None})


@router.post("/register")
async def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == email.lower().strip()))
    if existing.scalar_one_or_none() is not None:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"user": None, "error": "Email already registered"},
            status_code=400,
        )

    if len(password) < 8:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"user": None, "error": "Password must be at least 8 characters"},
            status_code=400,
        )

    user = User(
        email=email.lower().strip(),
        name=name.strip(),
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("New user registered: user_id=%d", user.id)
    response = RedirectResponse(url="/", status_code=303)
    set_session_cookie(response, user.id)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/auth/login", status_code=303)
    clear_session_cookie(response)
    return response
