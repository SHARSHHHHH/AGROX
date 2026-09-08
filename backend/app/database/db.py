"""SQLAlchemy engine. SQLite for dev, PostgreSQL-compatible schema."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema():
    """Add columns that exist in the models but not yet in the database.

    WHY THIS EXISTS
    ---------------
    `Base.metadata.create_all()` creates missing TABLES but never alters
    existing ones. So when a new column is added to a model, an existing
    agri.db keeps the old shape and every query touching that column fails
    with "no such column" — which looks like data corruption.

    Deleting the database would fix it and destroy the farmer's history. This
    adds the missing columns in place instead.

    Scope is deliberately narrow: additive ALTER TABLE ADD COLUMN only. It
    never drops or retypes anything, so it cannot lose data. For renames or
    type changes, use a real migration tool (Alembic).
    """
    import logging
    from sqlalchemy import inspect, text

    log = logging.getLogger("agri.db")
    if not settings.DATABASE_URL.startswith("sqlite"):
        return []                      # Postgres deployments should use Alembic

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    added = []

    with engine.begin() as conn:
        for table_name, table in Base.metadata.tables.items():
            if table_name not in existing_tables:
                continue                # create_all will handle a new table

            have = {c["name"] for c in inspector.get_columns(table_name)}
            for column in table.columns:
                if column.name in have:
                    continue

                col_type = column.type.compile(engine.dialect)
                default = ""
                if column.default is not None and getattr(column.default, "is_scalar", False):
                    value = column.default.arg
                    if isinstance(value, str):
                        default = f" DEFAULT '{value}'"
                    elif isinstance(value, bool):
                        default = f" DEFAULT {int(value)}"
                    elif isinstance(value, (int, float)):
                        default = f" DEFAULT {value}"

                sql = f'ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}{default}'
                try:
                    conn.execute(text(sql))
                    added.append(f"{table_name}.{column.name}")
                    log.info("schema: added %s.%s", table_name, column.name)
                except Exception as exc:
                    log.warning("schema: could not add %s.%s (%s)",
                                table_name, column.name, exc)

    if added:
        log.info("schema migration added %d column(s): %s", len(added), added)
    return added
