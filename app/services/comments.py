from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment


async def add_comment(db: AsyncSession, expense_id: int, user_id: int, text: str) -> Comment | None:
    """Add a comment to an expense. Returns None if text is empty."""
    text = text.strip()
    if not text:
        return None

    comment = Comment(expense_id=expense_id, user_id=user_id, text=text)
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


async def get_comments(db: AsyncSession, expense_id: int) -> list[Comment]:
    """Get all comments for an expense, ordered chronologically."""
    result = await db.execute(
        select(Comment)
        .where(Comment.expense_id == expense_id)
        .order_by(Comment.created_at.asc())
    )
    return list(result.scalars().all())


async def delete_comment(db: AsyncSession, comment_id: int, user_id: int) -> bool:
    """Delete a comment. Only the author can delete."""
    comment = await db.get(Comment, comment_id)
    if comment is None or comment.user_id != user_id:
        return False
    await db.delete(comment)
    await db.commit()
    return True
