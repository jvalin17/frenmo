"""Tests for expense comments — add, list, delete."""
import pytest

from app.models.comment import Comment
from app.models.expense import Expense
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.comments import add_comment, get_comments, delete_comment


@pytest.fixture
async def group_with_expense_and_users(db_session):
    alice = User(email="alice@test.com", name="Alice", password_hash="h")
    bob = User(email="bob@test.com", name="Bob", password_hash="h")
    db_session.add_all([alice, bob])
    await db_session.flush()

    group = Group(name="Trip", type="trip", created_by=alice.id, invite_token="cmttok")
    db_session.add(group)
    await db_session.flush()

    db_session.add_all([
        GroupMember(group_id=group.id, user_id=alice.id),
        GroupMember(group_id=group.id, user_id=bob.id),
    ])

    expense = Expense(
        group_id=group.id, description="Dinner", amount=10000,
        currency="USD", split_type="equal",
        paid_by=alice.id, created_by=alice.id,
    )
    db_session.add(expense)
    await db_session.commit()
    await db_session.refresh(expense)
    return group, alice, bob, expense


class TestAddComment:
    async def test_add_comment(self, db_session, group_with_expense_and_users):
        group, alice, bob, expense = group_with_expense_and_users
        comment = await add_comment(db_session, expense_id=expense.id, user_id=alice.id, text="Great dinner!")
        assert comment is not None
        assert comment.text == "Great dinner!"
        assert comment.user_id == alice.id
        assert comment.expense_id == expense.id

    async def test_empty_comment_rejected(self, db_session, group_with_expense_and_users):
        group, alice, bob, expense = group_with_expense_and_users
        comment = await add_comment(db_session, expense_id=expense.id, user_id=alice.id, text="  ")
        assert comment is None

    async def test_multiple_comments_on_same_expense(self, db_session, group_with_expense_and_users):
        group, alice, bob, expense = group_with_expense_and_users
        await add_comment(db_session, expense_id=expense.id, user_id=alice.id, text="Comment 1")
        await add_comment(db_session, expense_id=expense.id, user_id=bob.id, text="Comment 2")
        comments = await get_comments(db_session, expense.id)
        assert len(comments) == 2


class TestGetComments:
    async def test_returns_chronological(self, db_session, group_with_expense_and_users):
        group, alice, bob, expense = group_with_expense_and_users
        await add_comment(db_session, expense_id=expense.id, user_id=alice.id, text="First")
        await add_comment(db_session, expense_id=expense.id, user_id=bob.id, text="Second")
        comments = await get_comments(db_session, expense.id)
        assert comments[0].text == "First"
        assert comments[1].text == "Second"

    async def test_empty_list_for_no_comments(self, db_session, group_with_expense_and_users):
        group, alice, bob, expense = group_with_expense_and_users
        comments = await get_comments(db_session, expense.id)
        assert len(comments) == 0


class TestDeleteComment:
    async def test_author_can_delete(self, db_session, group_with_expense_and_users):
        group, alice, bob, expense = group_with_expense_and_users
        comment = await add_comment(db_session, expense_id=expense.id, user_id=alice.id, text="Delete me")
        result = await delete_comment(db_session, comment_id=comment.id, user_id=alice.id)
        assert result is True
        comments = await get_comments(db_session, expense.id)
        assert len(comments) == 0

    async def test_non_author_cannot_delete(self, db_session, group_with_expense_and_users):
        group, alice, bob, expense = group_with_expense_and_users
        comment = await add_comment(db_session, expense_id=expense.id, user_id=alice.id, text="Mine")
        result = await delete_comment(db_session, comment_id=comment.id, user_id=bob.id)
        assert result is False
