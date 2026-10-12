"""Regression tests for the session-8 reviewer findings (see project-state.md Known Issues)."""

from pathlib import Path

import pytest

DETAIL_HTML = (Path(__file__).resolve().parents[2] / "app/templates/group/detail.html").read_text()


class TestRegisterRejectsBlankName:
    """auth.py register strips the name but never checks it is non-empty."""

    async def test_whitespace_name_is_rejected(self, client):
        response = await client.post(
            "/auth/register",
            data={"name": "   ", "email": "priya.nair@outlook.com", "password": "correct-horse-9"},
        )
        assert response.status_code == 400
        assert "Name is required" in response.text

    async def test_valid_name_still_registers(self, client):
        response = await client.post(
            "/auth/register",
            data={
                "name": " Priya Nair ",
                "email": "priya.nair@outlook.com",
                "password": "correct-horse-9",
            },
        )
        assert response.status_code == 303


class TestSettlementFormBuiltWithoutInnerHtml:
    """The slide-to-settle script must not build the POST form via string-concatenated innerHTML."""

    def test_no_innerhtml_concatenation(self):
        assert "form.innerHTML" not in DETAIL_HTML, (
            "Build hidden inputs with createElement + .value, not innerHTML string concatenation"
        )

    def test_hidden_inputs_created_via_dom(self):
        assert "hiddenInput('from_user'" in DETAIL_HTML
        assert "hiddenInput('to_user'" in DETAIL_HTML
        assert "hiddenInput('amount'" in DETAIL_HTML


@pytest.fixture
async def alice_bob_group(db_session):
    """Two-member group; Alice is the viewer."""
    import uuid

    from app.models.group import Group, GroupMember
    from app.models.user import User

    alice = User(email="alice.fernandes@gmail.com", name="Alice", password_hash="h")
    bob = User(email="bob.menon@gmail.com", name="Bob", password_hash="h")
    db_session.add_all([alice, bob])
    await db_session.flush()
    group = Group(name="Goa Trip", created_by=alice.id, invite_token=f"tok_{uuid.uuid4().hex[:8]}")
    db_session.add(group)
    await db_session.flush()
    db_session.add_all(
        [
            GroupMember(group_id=group.id, user_id=alice.id),
            GroupMember(group_id=group.id, user_id=bob.id),
        ]
    )
    await db_session.commit()
    return group, alice, bob


def _session_cookie(user_id: int) -> dict:
    from app.middleware.auth import session_serializer

    return {"frenmo_session": session_serializer.dumps({"user_id": user_id})}


class TestGroupDetailSplitChips:
    async def test_repaired_split_appears_on_first_load(self, client, db_session, alice_bob_group):
        """Equal expense created for Alice only; repair_missing_splits adds Bob.

        Bob's chip must show on the same request, not the next one.
        """
        from app.services.expense import create_expense_with_splits

        group, alice, bob = alice_bob_group
        await create_expense_with_splits(
            db=db_session,
            group_id=group.id,
            description="Beach shack dinner",
            amount_paise=180000,
            split_type="equal",
            paid_by=alice.id,
            created_by=alice.id,
            member_ids=[alice.id],
        )
        await db_session.commit()

        resp = await client.get(f"/groups/{group.id}", cookies=_session_cookie(alice.id))
        assert resp.status_code == 200
        assert 'split-chip__name">Bob<' in resp.text, (
            "Bob's repaired split should render as a chip on first load"
        )
        assert 'split-chip__name">Alice<' in resp.text

    async def test_departed_member_name_still_shown(self, client, db_session, alice_bob_group):
        """A split owed by a user who left the group should show their name, not '?'."""
        from sqlalchemy import delete

        from app.models.group import GroupMember
        from app.services.expense import create_expense_with_splits

        group, alice, bob = alice_bob_group
        await create_expense_with_splits(
            db=db_session,
            group_id=group.id,
            description="Scooter rental",
            amount_paise=90000,
            split_type="equal",
            paid_by=alice.id,
            created_by=alice.id,
            member_ids=[alice.id, bob.id],
        )
        await db_session.execute(delete(GroupMember).where(GroupMember.user_id == bob.id))
        await db_session.commit()

        resp = await client.get(f"/groups/{group.id}", cookies=_session_cookie(alice.id))
        assert resp.status_code == 200
        assert 'split-chip__name">Bob<' in resp.text
        assert 'split-chip__name">?<' not in resp.text


ROOT = Path(__file__).resolve().parents[2]


class TestDeployHygiene:
    def test_dockerignore_excludes_dev_artifacts(self):
        dockerignore = (ROOT / ".dockerignore").read_text().splitlines()
        for entry in [
            ".git",
            ".venv",
            "**/*.db",
            "**/*.sqlite*",
            "tests/",
            ".scratch/",
            "__pycache__/",
            ".env",
            ".env.*",
            "!.env.example",
        ]:
            assert entry in dockerignore, f".dockerignore should list {entry}"

    def test_gitignore_excludes_e2e_screenshots(self):
        assert "tests/e2e/screenshots/" in (ROOT / ".gitignore").read_text().splitlines()

    def test_tailwind_cdn_is_version_pinned(self):
        base_html = (ROOT / "app/templates/base.html").read_text()
        assert 'src="https://cdn.tailwindcss.com"' not in base_html, (
            "Tailwind play CDN must be pinned"
        )
        assert 'src="https://cdn.tailwindcss.com/3.4.17"' in base_html


class TestRedundantSplitIndexDropped:
    """UniqueConstraint(expense_id, user_id) already indexes expense_id.

    The extra single-column index only costs writes.
    """

    def test_model_has_no_redundant_expense_index(self):
        from app.models.expense import ExpenseSplit

        assert "ix_expense_splits_expense" not in {ix.name for ix in ExpenseSplit.__table__.indexes}

    async def test_startup_migration_drops_existing_redundant_index(self):
        from sqlalchemy import inspect as sa_inspect
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.database import Base, migrate_schema

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                text("CREATE INDEX ix_expense_splits_expense ON expense_splits (expense_id)")
            )
            await conn.run_sync(migrate_schema)
            names = await conn.run_sync(
                lambda c: {ix["name"] for ix in sa_inspect(c).get_indexes("expense_splits")}
            )
        await engine.dispose()
        assert "ix_expense_splits_expense" not in names
