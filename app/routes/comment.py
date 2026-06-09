import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import login_required
from app.models.expense import Expense
from app.services.comments import add_comment, delete_comment

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/comments", tags=["comments"])


@router.post("/add/{expense_id}")
@login_required
async def post_comment(request: Request, expense_id: int, db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    text = form_data.get("text", "").strip()

    expense = await db.get(Expense, expense_id)
    if expense is None:
        return RedirectResponse(url="/", status_code=303)

    if text:
        await add_comment(db, expense_id=expense_id, user_id=request.state.user_id, text=text)
        logger.info("Comment added: expense=%d user=%d", expense_id, request.state.user_id)

    return RedirectResponse(url=f"/groups/{expense.group_id}", status_code=303)


@router.post("/delete/{comment_id}")
@login_required
async def remove_comment(request: Request, comment_id: int, db: AsyncSession = Depends(get_db)):
    from app.models.comment import Comment
    comment = await db.get(Comment, comment_id)
    if comment is None:
        return RedirectResponse(url="/", status_code=303)

    expense = await db.get(Expense, comment.expense_id)
    await delete_comment(db, comment_id=comment_id, user_id=request.state.user_id)
    logger.info("Comment deleted: comment=%d user=%d", comment_id, request.state.user_id)

    return RedirectResponse(url=f"/groups/{expense.group_id}", status_code=303)
