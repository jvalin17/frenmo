"""Tests for group settings updating shares and recalculating existing expenses."""
import uuid

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.middleware.auth import session_serializer
from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.expense import create_expense_with_splits


@pytest.fixture
async def group_with_equal_expenses(db_session: AsyncSession):
    """Group with 3 members and 2 equal expenses."""
    alice = User(email=f"a_{uuid.uuid4().hex[:6]}@test.com", name="Alice", password_hash="h")
    bob = User(email=f"b_{uuid.uuid4().hex[:6]}@test.com", name="Bob", password_hash="h")
    charlie = User(email=f"c_{uuid.uuid4().hex[:6]}@test.com", name="Charlie", password_hash="h")
    db_session.add_all([alice, bob, charlie])
    await db_session.flush()

    group = Group(name="Trip", created_by=alice.id, invite_token=f"tok_{uuid.uuid4().hex[:8]}")
    db_session.add(group)
    await db_session.flush()

    db_session.add_all([
        GroupMember(group_id=group.id, user_id=alice.id),
        GroupMember(group_id=group.id, user_id=bob.id),
        GroupMember(group_id=group.id, user_id=charlie.id),
    ])
    await db_session.commit()

    e1 = await create_expense_with_splits(
        db=db_session, group_id=group.id, description="Hotel",
        amount_paise=9000, split_type="equal", paid_by=alice.id,
        created_by=alice.id, member_ids=[alice.id, bob.id, charlie.id],
    )
    e2 = await create_expense_with_splits(
        db=db_session, group_id=group.id, description="Custom Beer",
        amount_paise=6000, split_type="exact", paid_by=bob.id,
        created_by=bob.id, member_ids=[alice.id, bob.id],
        member_values={alice.id: 40.0, bob.id: 20.0},
    )
    return group, alice, bob, charlie, e1, e2


class TestGroupSettingsRecalculate:

    async def test_settings_update_recalculates_equal_expenses(
        self, db_session, group_with_equal_expenses
    ):
        """POST to /groups/{id}/settings with new shares recalculates equal expenses."""
        group, alice, bob, charlie, e_equal, e_exact = group_with_equal_expenses

        cookie = session_serializer.dumps({"user_id": alice.id})
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
            resp = await client.post(
                f"/groups/{group.id}/settings",
                data={
                    "name": group.name,
                    "currency": group.currency,
                    f"shares_{alice.id}": "1",
                    f"shares_{bob.id}": "1",
                    f"shares_{charlie.id}": "3",
                },
                cookies={"frenmo_session": cookie},
            )
            assert resp.status_code == 303

        # Equal expense should be recalculated: A=1800, B=1800, C=5400
        splits_result = await db_session.execute(
            select(ExpenseSplit).where(ExpenseSplit.expense_id == e_equal.id)
        )
        splits = {s.user_id: s for s in splits_result.scalars().all()}
        assert splits[alice.id].owed_amount == 1800
        assert splits[bob.id].owed_amount == 1800
        assert splits[charlie.id].owed_amount == 5400

    async def test_settings_update_leaves_overridden_expenses(
        self, db_session, group_with_equal_expenses
    ):
        """POST to /groups/{id}/settings does not touch exact-split expenses."""
        group, alice, bob, charlie, e_equal, e_exact = group_with_equal_expenses

        # Record exact splits before
        splits_before = await db_session.execute(
            select(ExpenseSplit).where(ExpenseSplit.expense_id == e_exact.id)
        )
        owed_before = {s.user_id: s.owed_amount for s in splits_before.scalars().all()}

        cookie = session_serializer.dumps({"user_id": alice.id})
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
            await client.post(
                f"/groups/{group.id}/settings",
                data={
                    "name": group.name,
                    "currency": group.currency,
                    f"shares_{alice.id}": "1",
                    f"shares_{bob.id}": "1",
                    f"shares_{charlie.id}": "3",
                },
                cookies={"frenmo_session": cookie},
            )

        # Exact expense should be unchanged
        splits_after = await db_session.execute(
            select(ExpenseSplit).where(ExpenseSplit.expense_id == e_exact.id)
        )
        owed_after = {s.user_id: s.owed_amount for s in splits_after.scalars().all()}
        assert owed_after == owed_before
