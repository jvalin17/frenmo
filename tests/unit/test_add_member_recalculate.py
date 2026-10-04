"""Tests: adding a member to a group recalculates existing equal and shares-split expenses."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import ExpenseSplit
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.expense import (
    create_expense_with_splits,
    recalculate_splits_for_new_member,
    repair_missing_splits,
)


@pytest.fixture
async def two_member_group(db_session: AsyncSession):
    """Group with 2 members (Alice, Bob) and a pending new member (Charlie)."""
    alice = User(email="a@test.com", name="Alice", password_hash="h")
    bob = User(email="b@test.com", name="Bob", password_hash="h")
    charlie = User(email="c@test.com", name="Charlie", password_hash="h")
    db_session.add_all([alice, bob, charlie])
    await db_session.flush()

    group = Group(name="Trip", created_by=alice.id, invite_token=f"tok_{uuid.uuid4().hex[:8]}")
    db_session.add(group)
    await db_session.flush()

    db_session.add_all([
        GroupMember(group_id=group.id, user_id=alice.id),
        GroupMember(group_id=group.id, user_id=bob.id),
    ])
    await db_session.commit()
    return group, alice, bob, charlie


async def _get_splits(db: AsyncSession, expense_id: int) -> dict[int, ExpenseSplit]:
    result = await db.execute(
        select(ExpenseSplit).where(ExpenseSplit.expense_id == expense_id)
    )
    return {s.user_id: s for s in result.scalars().all()}


class TestRecalculateSplitsForNewMember:

    async def test_new_member_added_to_equal_splits(self, db_session, two_member_group):
        """When Charlie joins, existing equal expenses should include him."""
        group, alice, bob, charlie = two_member_group

        # Alice adds a $100 expense split equally between Alice and Bob
        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Hotel",
            amount_paise=10000, split_type="equal", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
        )

        # Before: Alice=5000, Bob=5000
        splits = await _get_splits(db_session, expense.id)
        assert splits[alice.id].owed_amount == 5000
        assert splits[bob.id].owed_amount == 5000
        assert charlie.id not in splits

        # Charlie joins the group
        db_session.add(GroupMember(group_id=group.id, user_id=charlie.id))
        await db_session.flush()

        count = await recalculate_splits_for_new_member(db_session, group.id, charlie.id)
        await db_session.commit()

        # After: Alice=3334, Bob=3333, Charlie=3333
        splits = await _get_splits(db_session, expense.id)
        assert charlie.id in splits
        total_owed = sum(s.owed_amount for s in splits.values())
        assert total_owed == 10000
        assert count == 1

    async def test_new_member_payer_keeps_paid_amount(self, db_session, two_member_group):
        """Payer's paid_amount should remain the expense total after recalculation."""
        group, alice, bob, charlie = two_member_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Dinner",
            amount_paise=9000, split_type="equal", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
        )

        db_session.add(GroupMember(group_id=group.id, user_id=charlie.id))
        await db_session.flush()
        await recalculate_splits_for_new_member(db_session, group.id, charlie.id)
        await db_session.commit()

        splits = await _get_splits(db_session, expense.id)
        assert splits[alice.id].paid_amount == 9000  # alice still the payer
        assert splits[bob.id].paid_amount == 0
        assert splits[charlie.id].paid_amount == 0

    async def test_new_member_ignores_exact_splits(self, db_session, two_member_group):
        """Exact-split expenses should NOT be recalculated."""
        group, alice, bob, charlie = two_member_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Custom",
            amount_paise=10000, split_type="exact", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
            member_values={alice.id: 70.0, bob.id: 30.0},
        )

        db_session.add(GroupMember(group_id=group.id, user_id=charlie.id))
        await db_session.flush()
        count = await recalculate_splits_for_new_member(db_session, group.id, charlie.id)
        await db_session.commit()

        splits = await _get_splits(db_session, expense.id)
        assert charlie.id not in splits
        assert count == 0

    async def test_new_member_ignores_settlements(self, db_session, two_member_group):
        """Settlements should NOT be recalculated."""
        group, alice, bob, charlie = two_member_group

        await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Settle",
            amount_paise=5000, split_type="equal", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
            expense_type="settlement",
        )

        db_session.add(GroupMember(group_id=group.id, user_id=charlie.id))
        await db_session.flush()
        count = await recalculate_splits_for_new_member(db_session, group.id, charlie.id)
        assert count == 0

    async def test_new_member_ignores_deleted_expenses(self, db_session, two_member_group):
        """Deleted expenses should NOT be recalculated."""
        group, alice, bob, charlie = two_member_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Old",
            amount_paise=6000, split_type="equal", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
        )
        from app.services.expense import soft_delete_expense
        await soft_delete_expense(db_session, expense.id)

        db_session.add(GroupMember(group_id=group.id, user_id=charlie.id))
        await db_session.flush()
        count = await recalculate_splits_for_new_member(db_session, group.id, charlie.id)
        assert count == 0

    async def test_new_member_balance_nonzero(self, db_session, two_member_group):
        """After joining, new member should have a negative balance (owes money)."""
        group, alice, bob, charlie = two_member_group

        await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Hotel",
            amount_paise=9000, split_type="equal", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
        )

        db_session.add(GroupMember(group_id=group.id, user_id=charlie.id))
        await db_session.flush()
        await recalculate_splits_for_new_member(db_session, group.id, charlie.id)
        await db_session.commit()

        from app.services.balance import get_group_balances
        balances = await get_group_balances(db_session, group.id)

        # Charlie should owe money (negative balance), not be "settled"
        assert charlie.id in balances
        assert balances[charlie.id] < 0

    async def test_respects_member_shares(self, db_session, two_member_group):
        """New member with custom shares should get proportional split."""
        group, alice, bob, charlie = two_member_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Hotel",
            amount_paise=10000, split_type="equal", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
        )

        # Charlie joins with 2 shares
        member = GroupMember(group_id=group.id, user_id=charlie.id, default_shares=2)
        db_session.add(member)
        await db_session.flush()
        await recalculate_splits_for_new_member(db_session, group.id, charlie.id)
        await db_session.commit()

        # Shares: A=1, B=1, C=2, total=4
        # A=2500, B=2500, C=5000
        splits = await _get_splits(db_session, expense.id)
        assert splits[charlie.id].owed_amount == 5000
        assert splits[alice.id].owed_amount == 2500
        assert splits[bob.id].owed_amount == 2500

    async def test_new_member_added_to_shares_splits(self, db_session, two_member_group):
        """When Charlie joins, existing shares-type expenses should include him."""
        group, alice, bob, charlie = two_member_group

        # Expense with shares split: Alice=2, Bob=3
        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Dinner",
            amount_paise=10000, split_type="shares", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
            member_values={alice.id: 2.0, bob.id: 3.0},
        )

        # Before: Alice=4000, Bob=6000
        splits = await _get_splits(db_session, expense.id)
        assert splits[alice.id].owed_amount == 4000
        assert splits[bob.id].owed_amount == 6000
        assert charlie.id not in splits

        # Charlie joins
        db_session.add(GroupMember(group_id=group.id, user_id=charlie.id))
        await db_session.flush()
        count = await recalculate_splits_for_new_member(db_session, group.id, charlie.id)
        await db_session.commit()

        # After: Charlie added with default_shares=1, total shares=2+3+1=6
        # Alice=3333, Bob=5000, Charlie=1667
        splits = await _get_splits(db_session, expense.id)
        assert charlie.id in splits
        total_owed = sum(s.owed_amount for s in splits.values())
        assert total_owed == 10000
        assert count == 1

    async def test_new_member_ignores_percent_splits(self, db_session, two_member_group):
        """Percent-split expenses should NOT be recalculated."""
        group, alice, bob, charlie = two_member_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Taxi",
            amount_paise=10000, split_type="percent", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
            member_values={alice.id: 60.0, bob.id: 40.0},
        )

        db_session.add(GroupMember(group_id=group.id, user_id=charlie.id))
        await db_session.flush()
        count = await recalculate_splits_for_new_member(db_session, group.id, charlie.id)
        await db_session.commit()

        splits = await _get_splits(db_session, expense.id)
        assert charlie.id not in splits
        assert count == 0


class TestRepairMissingSplits:

    async def test_repair_fixes_members_missing_from_splits(self, db_session, two_member_group):
        """Members added without recalculation get fixed on repair."""
        group, alice, bob, charlie = two_member_group

        # Expense created with only Alice and Bob
        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Hotel",
            amount_paise=9000, split_type="equal", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
        )

        # Charlie joins but NO recalculation (simulates old code path)
        db_session.add(GroupMember(group_id=group.id, user_id=charlie.id))
        await db_session.commit()

        # Before repair: charlie not in splits
        splits = await _get_splits(db_session, expense.id)
        assert charlie.id not in splits

        # Repair
        count = await repair_missing_splits(db_session, group.id)
        await db_session.commit()

        # After repair: charlie in splits, total still 9000
        splits = await _get_splits(db_session, expense.id)
        assert charlie.id in splits
        total = sum(s.owed_amount for s in splits.values())
        assert total == 9000
        assert count == 1

    async def test_repair_noop_when_all_members_present(self, db_session, two_member_group):
        """No repair needed when all members already in splits."""
        group, alice, bob, charlie = two_member_group

        await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Hotel",
            amount_paise=9000, split_type="equal", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
        )

        # No charlie in group — nothing to repair
        count = await repair_missing_splits(db_session, group.id)
        assert count == 0

    async def test_repair_fixes_balance_to_nonzero(self, db_session, two_member_group):
        """After repair, previously 'settled' member should have a real balance."""
        group, alice, bob, charlie = two_member_group

        await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Hotel",
            amount_paise=9000, split_type="equal", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
        )

        # Charlie joins without recalculation
        db_session.add(GroupMember(group_id=group.id, user_id=charlie.id))
        await db_session.commit()

        # Before: charlie balance = 0 (settled)
        from app.services.balance import get_group_balances
        balances = await get_group_balances(db_session, group.id)
        assert charlie.id not in balances  # 0 = not in dict

        # Repair
        await repair_missing_splits(db_session, group.id)
        await db_session.commit()

        # After: charlie owes money
        balances = await get_group_balances(db_session, group.id)
        assert charlie.id in balances
        assert balances[charlie.id] < 0

    async def test_repair_fixes_shares_split_expenses(self, db_session, two_member_group):
        """Members missing from shares-type expenses get fixed on repair."""
        group, alice, bob, charlie = two_member_group

        expense = await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Dinner",
            amount_paise=10000, split_type="shares", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
            member_values={alice.id: 2.0, bob.id: 3.0},
        )

        # Charlie joins without recalculation
        db_session.add(GroupMember(group_id=group.id, user_id=charlie.id))
        await db_session.commit()

        # Before: charlie not in splits
        splits = await _get_splits(db_session, expense.id)
        assert charlie.id not in splits

        # Repair
        count = await repair_missing_splits(db_session, group.id)
        await db_session.commit()

        # After: charlie added, total still 10000
        splits = await _get_splits(db_session, expense.id)
        assert charlie.id in splits
        total = sum(s.owed_amount for s in splits.values())
        assert total == 10000
        assert count == 1

    async def test_repair_ignores_percent_splits(self, db_session, two_member_group):
        """Percent-split expenses should NOT be repaired."""
        group, alice, bob, charlie = two_member_group

        await create_expense_with_splits(
            db=db_session, group_id=group.id, description="Taxi",
            amount_paise=10000, split_type="percent", paid_by=alice.id,
            created_by=alice.id, member_ids=[alice.id, bob.id],
            member_values={alice.id: 60.0, bob.id: 40.0},
        )

        db_session.add(GroupMember(group_id=group.id, user_id=charlie.id))
        await db_session.commit()

        count = await repair_missing_splits(db_session, group.id)
        assert count == 0
