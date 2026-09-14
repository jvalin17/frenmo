"""Tests for startup migration — ensures missing columns are added automatically."""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import test_engine


def test_migrate_schema():
    """Verify migrate_schema function exists and is callable."""
    from app.database import migrate_schema
    assert callable(migrate_schema)


class TestStartupMigration:
    """The migrate_schema function should add missing columns to existing tables."""

    async def test_migrate_schema_adds_missing_column(self, db_session: AsyncSession):
        """If a column is missing from the DB, migrate_schema should add it."""
        from app.database import migrate_schema

        # Drop theme_color column to simulate a pre-migration DB
        async with test_engine.begin() as conn:
            await conn.execute(text("ALTER TABLE users DROP COLUMN theme_color"))

        # Verify it's gone
        async with test_engine.begin() as conn:
            result = await conn.execute(text("PRAGMA table_info(users)"))
            columns = [row[1] for row in result.fetchall()]
        assert "theme_color" not in columns, "Setup: theme_color should be dropped"

        # Run migration
        async with test_engine.begin() as conn:
            await conn.run_sync(migrate_schema)

        # Verify it's back
        async with test_engine.begin() as conn:
            result = await conn.execute(text("PRAGMA table_info(users)"))
            columns = [row[1] for row in result.fetchall()]
        assert "theme_color" in columns, "migrate_schema should have added theme_color"

    async def test_migrate_is_idempotent(self, db_session: AsyncSession):
        """Running migrate_schema twice should not error."""
        from app.database import migrate_schema

        async with test_engine.begin() as conn:
            await conn.run_sync(migrate_schema)
        async with test_engine.begin() as conn:
            await conn.run_sync(migrate_schema)

    async def test_migrate_preserves_existing_data(self, db_session: AsyncSession):
        """Adding a column should not destroy existing user data."""
        from app.database import migrate_schema
        from app.models.user import User

        # Create a user first
        user = User(email="migrate@test.com", name="Migrator", password_hash="h")
        db_session.add(user)
        await db_session.commit()
        user_id = user.id

        # Drop and re-add the column
        async with test_engine.begin() as conn:
            await conn.execute(text("ALTER TABLE users DROP COLUMN theme_color"))
        async with test_engine.begin() as conn:
            await conn.run_sync(migrate_schema)

        # User data should still be there
        async with test_engine.begin() as conn:
            result = await conn.execute(text(f"SELECT name FROM users WHERE id = {user_id}"))
            row = result.fetchone()
        assert row is not None and row[0] == "Migrator"
