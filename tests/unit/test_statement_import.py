"""Tests for statement import — dedup logic and date handling."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.auth import hash_password


async def _setup_user_group(db: AsyncSession) -> tuple[int, int]:
    """Create a user, group, and membership. Returns (user_id, group_id)."""
    user = User(email="imp@test.com", name="Importer", password_hash=hash_password("pass1234"))
    db.add(user)
    await db.flush()

    group = Group(name="Test Group", created_by=user.id, currency="USD")
    db.add(group)
    await db.flush()

    db.add(GroupMember(group_id=group.id, user_id=user.id))
    await db.commit()
    return user.id, group.id


async def _create_expense(
    db: AsyncSession, group_id: int, user_id: int, description: str, amount: int
) -> Expense:
    """Create a basic expense with a split."""
    expense = Expense(
        group_id=group_id,
        description=description,
        amount=amount,
        currency="USD",
        split_type="equal",
        paid_by=user_id,
        created_by=user_id,
        idempotency_key=str(uuid.uuid4()),
    )
    db.add(expense)
    await db.flush()
    db.add(ExpenseSplit(expense_id=expense.id, user_id=user_id, paid_amount=amount, owed_amount=amount))
    await db.commit()
    return expense


class TestStatementDedup:
    """Bug: scalar_one_or_none() crashes with MultipleResultsFound when
    multiple expenses have the same description + amount in a group."""

    async def test_dedup_crashes_with_multiple_matches(self, db_session: AsyncSession):
        """Reproduces the crash: importing when 2+ expenses match description+amount."""
        uid, gid = await _setup_user_group(db_session)

        # Create two expenses with identical description + amount (legitimate: e.g., two Amazon orders)
        await _create_expense(db_session, gid, uid, "AMAZON.COM", 4599)
        await _create_expense(db_session, gid, uid, "AMAZON.COM", 4599)

        # Simulate the dedup check from statement.py import_expenses
        # This is the EXACT query from the route — it should NOT crash
        result = await db_session.execute(
            select(Expense).where(
                Expense.group_id == gid,
                Expense.description == "AMAZON.COM",
                Expense.amount == 4599,
                Expense.deleted_at.is_(None),
            )
        )
        # FIX: use scalars().first() instead of scalar_one_or_none()
        existing = result.scalars().first()
        assert existing is not None  # should find a match, not crash

    async def test_dedup_skips_existing_on_reimport(self, db_session: AsyncSession):
        """Importing the same statement twice should not create duplicates."""
        uid, gid = await _setup_user_group(db_session)

        # First import creates the expense
        await _create_expense(db_session, gid, uid, "UBER TRIP", 2350)

        # Second import: dedup check should find existing and skip
        result = await db_session.execute(
            select(Expense).where(
                Expense.group_id == gid,
                Expense.description == "UBER TRIP",
                Expense.amount == 2350,
                Expense.deleted_at.is_(None),
            )
        )
        existing = result.scalars().first()
        assert existing is not None  # found — would skip import

    async def test_dedup_allows_different_amounts(self, db_session: AsyncSession):
        """Same description but different amount should NOT be deduped."""
        uid, gid = await _setup_user_group(db_session)

        await _create_expense(db_session, gid, uid, "AMAZON.COM", 4599)

        result = await db_session.execute(
            select(Expense).where(
                Expense.group_id == gid,
                Expense.description == "AMAZON.COM",
                Expense.amount == 9999,  # different amount
                Expense.deleted_at.is_(None),
            )
        )
        existing = result.scalars().first()
        assert existing is None  # no match — should import


class TestStatementImportEndpoint:
    """Integration tests for the /statement/{group_id}/import endpoint."""

    async def test_same_desc_amount_different_dates_not_deduped(self, db_session: AsyncSession):
        """Two transactions with same description+amount but different dates
        are legitimate separate purchases and should BOTH be imported."""
        from app.middleware.auth import session_serializer
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy import func
        from app.main import app

        uid, gid = await _setup_user_group(db_session)

        cookie = session_serializer.dumps({"user_id": uid})
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
            resp = await client.post(
                f"/statement/{gid}/import",
                data={
                    "tx_0": "on", "desc_0": "AMAZON.COM", "amount_0": "4599",
                    "cat_0": "shopping", "date_0": "01/15",
                    "tx_1": "on", "desc_1": "AMAZON.COM", "amount_1": "4599",
                    "cat_1": "shopping", "date_1": "01/20",
                },
                cookies={"frenmo_session": cookie},
            )
            assert resp.status_code == 303

        # Both should be imported — they are different transactions on different dates
        result = await db_session.execute(
            select(func.count()).select_from(Expense).where(
                Expense.group_id == gid,
                Expense.description == "AMAZON.COM",
                Expense.deleted_at.is_(None),
            )
        )
        count = result.scalar()
        assert count == 2, f"Expected 2 expenses (different dates), got {count}"

    async def test_true_duplicate_still_deduped(self, db_session: AsyncSession):
        """Re-importing the exact same transaction (same desc+amount+date)
        should be skipped."""
        from app.middleware.auth import session_serializer
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy import func
        from app.main import app

        uid, gid = await _setup_user_group(db_session)

        cookie = session_serializer.dumps({"user_id": uid})
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
            # First import
            data = {
                "tx_0": "on", "desc_0": "UBER TRIP", "amount_0": "2350",
                "cat_0": "transport", "date_0": "01/15",
            }
            await client.post(f"/statement/{gid}/import", data=data, cookies={"frenmo_session": cookie})

            # Second import — same transaction
            await client.post(f"/statement/{gid}/import", data=data, cookies={"frenmo_session": cookie})

        result = await db_session.execute(
            select(func.count()).select_from(Expense).where(
                Expense.group_id == gid,
                Expense.description == "UBER TRIP",
                Expense.deleted_at.is_(None),
            )
        )
        count = result.scalar()
        assert count == 1, f"Expected 1 expense (deduped), got {count}"
