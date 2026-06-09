import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.database import create_tables, engine
from app.routes import account, auth, comment, dashboard, expense, friend, group, password_reset, settlement

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(application: FastAPI):
    await create_tables()
    yield


app = FastAPI(title="Rup-Split", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(account.router)
app.include_router(auth.router)
app.include_router(comment.router)
app.include_router(dashboard.router)
app.include_router(group.router)
app.include_router(expense.router)
app.include_router(password_reset.router)
app.include_router(friend.router)
app.include_router(settlement.router)


@app.get("/health")
async def health():
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as exc:
        return {"status": "unhealthy", "database": str(exc)}
