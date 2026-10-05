"""Tests for kid-friendly recalculation: group toggle, kid_count change, member join, repair."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense, ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.expense import (
    create_expense_with_splits,
    recalculate_group_splits,
    recalculate_splits_for_new_member,
    repair_missing_splits,
)


@pytest.fixture
async def kid_group(db_session: AsyncSession):
    """Group: Alice(1 share, 0 kids), Bob(2 shares, 0 kids), Charlie(2 shares, 1 kid)."""
    alice = User(email="alice@trip.com", name="Alice", password_hash="h")
    bob = User(email="bob@trip.com", name="Bob", password_hash="h")
    charlie = User(email="charlie@trip.com", name="Charlie", password_hash="h")
    db_session.add_all([alice, bob, charlie])
    await db_session.flush()

    group = Group(
        name="Goa Trip", created_by=alice.id,
        invite_token=f"tok_{uuid.uuid4().hex[:8]}",
        kid_friendly=True,
    )
    db_session.add(group)
    await db_session.flush()

    db_session.add_all([
        GroupMember(group_id=group.id, user_id=alice.id, default_shares=1, kid_count=0),
        GroupMember(group_id=group.id, user_id=bob.id, default_shares=2, kid_count=0),
        GroupMember(group_id=group.id, user_id=charlie.id, default_shares=2, kid_count=1),
    ])
    await db_session.commit()
    return group, alice, bob, charlie


async def _get_splits(db: AsyncSession, expense_id: int) -> dict[int, ExpenseSplit]:
    result = await db.execute(
        select(ExpenseSplit).where(ExpenseSplit.expense_id == expense_id)
    )
    return {s.user_id: s for s in result.scalars().all()}


class TestGroupToggleRecalculation:

    async def test__build_kid_aware_splits_via_toggle_on(self, db_session, kid_group):
        """Toggle ON: _build_kid_aware_splits produces 0.5 per kid."""
        group, alice, bob, charlie = kid_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Dinner",
            amount_paise=110000, split_type="equal", paid_by=alice.id,
            created_by=alice.id,
            member_ids=[alice.id, bob.id, charlie.id],
            kid_friendly=True,
        )

        # Kid-friendly: Alice(1), Bob(2), Charlie(2.5) → denom 5.5
        splits = await _get_splits(db_session, expense.id)
        assert sum(s.owed_amount for s in splits.values()) == 110000
        # Alice gets 1/5.5 * 110000 = 20000
        assert splits[alice.id].owed_amount == 20000

    async def test_toggle_off_recalculates_to_full_shares(self, db_session, kid_group):
        """Toggle OFF: kids count as full shares."""
        group, alice, bob, charlie = kid_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Dinner",
            amount_paise=120000, split_type="equal", paid_by=alice.id,
            created_by=alice.id,
            member_ids=[alice.id, bob.id, charlie.id],
            kid_friendly=True,
        )

        # Now toggle OFF → recalculate with full shares
        member_shares = {alice.id: 1, bob.id: 2, charlie.id: 2}
        kid_data = {alice.id: 0, bob.id: 0, charlie.id: 1}
        count = await recalculate_group_splits(
            db_session, group.id, member_shares,
            kid_data=kid_data, group_kid_friendly=False,
        )
        await db_session.commit()

        # Non-kid: Alice(1), Bob(2), Charlie(3) → denom 6
        splits = await _get_splits(db_session, expense.id)
        assert splits[alice.id].owed_amount == 20000  # 1/6 * 120000
        assert splits[bob.id].owed_amount == 40000   # 2/6
        assert splits[charlie.id].owed_amount == 60000  # 3/6
        assert count == 1

    async def test_toggle_skips_exact_percent_full(self, db_session, kid_group):
        """Exact/percent/full expenses not recalculated."""
        group, alice, bob, charlie = kid_group

        await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Custom",
            amount_paise=10000, split_type="exact", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
            member_values={alice.id: 70.0, bob.id: 30.0},
        )

        member_shares = {alice.id: 1, bob.id: 2, charlie.id: 2}
        kid_data = {charlie.id: 1}
        count = await recalculate_group_splits(
            db_session, group.id, member_shares,
            kid_data=kid_data, group_kid_friendly=True,
        )
        assert count == 0


class TestNewMemberKidAware:

    async def test_new_member_joins_kid_friendly_expense(self, db_session, kid_group):
        """New member with kids joins → kid-friendly expenses use effective shares."""
        group, alice, bob, charlie = kid_group

        dave = User(email="dave@trip.com", name="Dave", password_hash="h")
        db_session.add(dave)
        await db_session.flush()

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Food",
            amount_paise=55000, split_type="equal", paid_by=alice.id,
            created_by=alice.id,
            member_ids=[alice.id, bob.id, charlie.id],
            kid_friendly=True,
        )

        # Dave joins with 2 kids
        db_session.add(GroupMember(
            group_id=group.id, user_id=dave.id, default_shares=1, kid_count=2,
        ))
        await db_session.flush()
        await recalculate_splits_for_new_member(db_session, group.id, dave.id)
        await db_session.commit()

        # Kid-friendly: Alice(1), Bob(2), Charlie(2.5), Dave(1+1=2.0) → denom 7.5
        splits = await _get_splits(db_session, expense.id)
        assert dave.id in splits
        assert sum(s.owed_amount for s in splits.values()) == 55000

    async def test_new_member_joins_non_kid_expense(self, db_session, kid_group):
        """Non-kid expense: new member's kids count as full shares."""
        group, alice, bob, charlie = kid_group

        dave = User(email="dave2@trip.com", name="Dave", password_hash="h")
        db_session.add(dave)
        await db_session.flush()

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Flight",
            amount_paise=60000, split_type="equal", paid_by=alice.id,
            created_by=alice.id,
            member_ids=[alice.id, bob.id, charlie.id],
            kid_friendly=False,
        )

        db_session.add(GroupMember(
            group_id=group.id, user_id=dave.id, default_shares=1, kid_count=1,
        ))
        await db_session.flush()
        await recalculate_splits_for_new_member(db_session, group.id, dave.id)
        await db_session.commit()

        # Non-kid: Alice(1+0=1), Bob(2+0=2), Charlie(2+1=3), Dave(1+1=2) → denom 8
        splits = await _get_splits(db_session, expense.id)
        assert dave.id in splits
        assert sum(s.owed_amount for s in splits.values()) == 60000


class TestRepairKidAware:

    async def test_repair_uses_kid_shares_on_kid_expense(self, db_session, kid_group):
        """Repair adds missing member with kid-adjusted shares."""
        group, alice, bob, charlie = kid_group

        dave = User(email="dave3@trip.com", name="Dave", password_hash="h")
        db_session.add(dave)
        await db_session.flush()

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Lunch",
            amount_paise=35000, split_type="equal", paid_by=alice.id,
            created_by=alice.id,
            member_ids=[alice.id, bob.id, charlie.id],
            kid_friendly=True,
        )

        # Dave joins WITHOUT recalculation (simulates old code path)
        db_session.add(GroupMember(
            group_id=group.id, user_id=dave.id, default_shares=1, kid_count=1,
        ))
        await db_session.commit()

        # Repair should add Dave with kid-adjusted shares
        count = await repair_missing_splits(db_session, group.id)
        await db_session.commit()

        splits = await _get_splits(db_session, expense.id)
        assert dave.id in splits
        assert sum(s.owed_amount for s in splits.values()) == 35000
        assert count == 1
