"""Patch api/database.py to add inline migration support."""
import pathlib

db_path = pathlib.Path("api/database.py")
content = db_path.read_text(encoding="utf-8")

old = (
    '\nasync def init_db() -> None:\n'
    '    """Create all tables (dev/test). In prod, use Alembic migrations."""\n'
    '    async with async_engine.begin() as conn:\n'
    '        await conn.run_sync(Base.metadata.create_all)\n'
)

new = (
    '\nasync def init_db() -> None:\n'
    '    """Create all tables (dev/test). In prod, use Alembic migrations.\n'
    '\n'
    '    Also applies lightweight inline migrations for columns added without a\n'
    '    full Alembic revision, so existing databases (which pre-date those columns)\n'
    '    don\'t crash on SELECT.\n'
    '    """\n'
    '    async with async_engine.begin() as conn:\n'
    '        await conn.run_sync(Base.metadata.create_all)\n'
    '        await conn.run_sync(_apply_inline_migrations)\n'
    '\n'
    '\n'
    'def _safe_add_column(conn, table: str, column: str, col_def: str) -> None:\n'
    '    """ADD COLUMN if it does not already exist (SQLite + Postgres safe)."""\n'
    '    try:\n'
    '        import sqlalchemy\n'
    '        conn.execute(sqlalchemy.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"))\n'
    '        conn.commit()\n'
    '    except Exception:\n'
    '        pass  # column already exists or unsupported\n'
    '\n'
    '\n'
    'def _apply_inline_migrations(conn) -> None:\n'
    '    """Add any missing columns that were introduced without an Alembic migration.\n'
    '    Idempotent: fails silently if the column already exists.\n'
    '    """\n'
    '    _safe_add_column(conn, "clips", "clip_plan_json", "TEXT DEFAULT NULL")\n'
)

if old in content:
    out = content.replace(old, new, 1)
    db_path.write_text(out, encoding="utf-8")
    print("REPLACED OK")
else:
    print("NOT FOUND, dumping snippet:")
    idx = content.find("async def init_db")
    print(repr(content[idx:idx+200]))

