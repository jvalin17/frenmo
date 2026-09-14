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


def migrate_schema(connection) -> None:
    """Add any missing columns to existing tables.

    Compares ORM model definitions against the actual DB schema and
    issues ALTER TABLE ADD COLUMN for anything missing. Safe to run
    repeatedly — skips columns that already exist.
    """
    import logging
    from sqlalchemy import inspect as sa_inspect, text

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
                    default_val = column.server_default.arg.text
                    default_clause = f" DEFAULT {default_val}"
                stmt = f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}{default_clause}"
                logger.info("Auto-migration: %s", stmt)
                connection.execute(text(stmt))


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(migrate_schema)
