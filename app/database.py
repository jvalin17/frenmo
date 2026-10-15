import ssl as ssl_module
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# asyncpg doesn't accept sslmode= in URL — convert to ssl connect_arg
database_url = settings.database_url
connect_args = {}
if database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif "sslmode=" in database_url:
    database_url = database_url.split("?")[0]
    ssl_context = ssl_module.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl_module.CERT_NONE
    connect_args = {"ssl": ssl_context}

engine = create_async_engine(database_url, echo=settings.debug, connect_args=connect_args)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


# (table, index) pairs dropped from the ORM models; migrate_schema removes them from existing DBs
# Columns added by ADD COLUMN on older databases carry NULL for existing rows;
# backfill them with the model default so code can rely on a value.
BACKFILL_DEFAULTS = [
    ("groups", "currency", "USD"),
    ("users", "default_currency", "USD"),
]

DROPPED_INDEXES = [("expense_splits", "ix_expense_splits_expense")]

# Indexes added to existing tables after their creation; create_all only covers new tables.
# (table, index name, columns, unique)
ADDED_INDEXES = [("groups", "ux_groups_pair_key", ("pair_key",), True)]


def migrate_schema(connection) -> None:
    """Add any missing columns to existing tables.

    Compares ORM model definitions against the actual DB schema and
    issues ALTER TABLE ADD COLUMN for anything missing. Safe to run
    repeatedly — skips columns that already exist.
    """
    import logging

    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import text, update

    logger = logging.getLogger(__name__)
    inspector = sa_inspect(connection)
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue  # create_all will handle new tables
        existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name not in existing_columns:
                col_type = column.type.compile(dialect=connection.dialect)
                default_clause = ""
                if column.server_default is not None:
                    default_argument = column.server_default.arg
                    default_val = (
                        default_argument.text
                        if hasattr(default_argument, "text")
                        else str(default_argument)
                    )
                    default_clause = f" DEFAULT {default_val}"
                stmt = (
                    f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}{default_clause}"
                )
                logger.info("Auto-migration: %s", stmt)
                connection.execute(text(stmt))

    # Rows that predate a column's ADD COLUMN migration are NULL there
    for table_name, column_name, default_value in BACKFILL_DEFAULTS:
        if inspector.has_table(table_name):
            table = Base.metadata.tables[table_name]
            column = table.c[column_name]
            result = connection.execute(
                update(table).where(column.is_(None)).values({column_name: default_value})
            )
            if result.rowcount:
                logger.info(
                    "Auto-migration: backfilled %d NULL %s.%s with %r",
                    result.rowcount, table_name, column_name, default_value,
                )

    # Indexes added to tables that already existed when the database was created
    for table_name, index_name, columns, unique in ADDED_INDEXES:
        if inspector.has_table(table_name) and not any(
            ix["name"] == index_name for ix in inspector.get_indexes(table_name)
        ):
            unique_sql = "UNIQUE " if unique else ""
            stmt = (
                f"CREATE {unique_sql}INDEX IF NOT EXISTS {index_name} "
                f"ON {table_name} ({', '.join(columns)})"
            )
            logger.info("Auto-migration: %s", stmt)
            connection.execute(text(stmt))

    # Indexes removed from the models that older databases may still carry
    for table_name, index_name in DROPPED_INDEXES:
        if inspector.has_table(table_name) and any(
            ix["name"] == index_name for ix in inspector.get_indexes(table_name)
        ):
            logger.info("Auto-migration: DROP INDEX %s", index_name)
            connection.execute(text(f"DROP INDEX IF EXISTS {index_name}"))


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(migrate_schema)
