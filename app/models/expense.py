from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[int] = mapped_column(nullable=False)  # cents/paise
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    split_type: Mapped[str] = mapped_column(String(10), nullable=False)  # equal, exact, percent
    expense_type: Mapped[str] = mapped_column(
        String(10), default="expense"
    )  # expense or settlement
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    paid_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)

    __table_args__ = (
        CheckConstraint("amount > 0", name="positive_amount"),
        Index("ix_expenses_group_deleted", "group_id", "deleted_at"),
    )


class ExpenseSplit(Base):
    __tablename__ = "expense_splits"

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("expenses.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    paid_amount: Mapped[int] = mapped_column(nullable=False, default=0)  # cents
    owed_amount: Mapped[int] = mapped_column(nullable=False, default=0)  # cents

    __table_args__ = (
        UniqueConstraint("expense_id", "user_id"),
        Index("ix_expense_splits_expense", "expense_id"),
    )
