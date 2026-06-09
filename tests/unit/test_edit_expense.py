"""Tests for editing expenses — update fields and recompute splits."""
import pytest
from datetime import datetime

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.expense import create_expense_with_splits, update_expense


@pytest.fixture
async def group_with_expense(db_session):
    """Create a group with one expense for edit testing."""
    alice = User(email="alice@test.com", name="Alice", password_hash="h")
    bob = User(email="bob@test.com", name="Bob", password_hash="h")
    db_session.add_all([alice, bob])
    await db_session.flush()

    group = Group(name="Trip", type="trip", created_by=alice.id, invite_token="edittok")
    db_session.add(group)
    await db_session.flush()

    db_session.add_all([
        GroupMember(group_id=group.id, user_id=alice.id),
        GroupMember(group_id=group.id, user_id=bob.id),
    ])
    await db_session.flush()

    expense = await create_expense_with_splits(
        db=db_session,
        group_id=group.id,
        description="Dinner",
        amount_paise=10000,
        currency="USD",
        split_type="equal",
        paid_by=alice.id,
        created_by=alice.id,
        member_ids=[alice.id, bob.id],
    )
    return group, alice, bob, expense


class TestUpdateExpense:
    async def test_update_description(self, db_session, group_with_expense):
        group, alice, bob, expense = group_with_expense
        updated = await update_expense(
            db=db_session,
            expense_id=expense.id,
            user_id=alice.id,
            description="Fancy Dinner",
        )
        assert updated is not None
        assert updated.description == "Fancy Dinner"
        assert updated.amount == 10000  # unchanged

    async def test_update_amount_recomputes_splits(self, db_session, group_with_expense):
        group, alice, bob, expense = group_with_expense
        updated = await update_expense(
            db=db_session,
            expense_id=expense.id,
            user_id=alice.id,
            amount_paise=20000,
        )
        assert updated.amount == 20000

        # Check splits were recomputed
        from sqlalchemy import select
        splits_result = await db_session.execute(
            select(ExpenseSplit).where(ExpenseSplit.expense_id == expense.id)
        )
        splits = {s.user_id: s for s in splits_result.scalars().all()}
        assert splits[alice.id].owed_amount == 10000  # 20000 / 2
        assert splits[bob.id].owed_amount == 10000
        assert splits[alice.id].paid_amount == 20000  # alice paid

    async def test_update_category(self, db_session, group_with_expense):
        group, alice, bob, expense = group_with_expense
        updated = await update_expense(
            db=db_session,
            expense_id=expense.id,
            user_id=alice.id,
            category="food",
        )
        assert updated.category == "food"

    async def test_only_creator_can_edit(self, db_session, group_with_expense):
        group, alice, bob, expense = group_with_expense
        result = await update_expense(
            db=db_session,
            expense_id=expense.id,
            user_id=bob.id,  # bob didn't create it
            description="Hacked",
        )
        assert result is None

    async def test_cannot_edit_deleted_expense(self, db_session, group_with_expense):
        group, alice, bob, expense = group_with_expense
        expense.deleted_at = datetime.utcnow()
        await db_session.commit()

        result = await update_expense(
            db=db_session,
            expense_id=expense.id,
            user_id=alice.id,
            description="Should fail",
        )
        assert result is None

    async def test_update_currency(self, db_session, group_with_expense):
        group, alice, bob, expense = group_with_expense
        updated = await update_expense(
            db=db_session,
            expense_id=expense.id,
            user_id=alice.id,
            currency="EUR",
        )
        assert updated.currency == "EUR"
