import sqlalchemy
from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(str(settings.DATABASE_URL).replace("+asyncpg", ""))
with engine.connect() as conn:
    # Check the exact column definition
    result = conn.execute(text("""
        SELECT data_type, udt_name
        FROM information_schema.columns
        WHERE table_name = 'source' AND column_name = 'jurisdiction'
    """))
    print("Column info:")
    for row in result:
        print(f"  {row}")

    # Also check if there's any enum associated with this column
    result2 = conn.execute(text("""
        SELECT t.typname, e.enumlabel
        FROM pg_attribute a
        JOIN pg_class c ON a.attrelid = c.oid
        JOIN pg_type t ON a.atttypid = t.oid
        LEFT JOIN pg_enum e ON t.oid = e.enumtypid
        WHERE c.relname = 'source' AND a.attname = 'jurisdiction'
        ORDER BY a.attnum
    """))
    print("Enum values for source.jurisdiction:")
    for row in result2:
        enum_label = row[1] if row[1] else "(NULL)"
        print(f"  {row[0]}: {enum_label}")