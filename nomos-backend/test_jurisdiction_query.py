import sqlalchemy
from sqlalchemy import create_engine, text
from app.core.config import settings
from app.models import Jurisdiction

engine = create_engine(str(settings.DATABASE_URL).replace("+asyncpg", ""))
with engine.connect() as conn:
    # Test querying with lowercase 'ng' in a fresh transaction
    print("Testing query with lowercase 'ng':")
    try:
        result = conn.execute(text("SELECT * FROM source WHERE jurisdiction = 'ng'"))
        rows = result.fetchall()
        print(f"  Found {len(rows)} rows with jurisdiction = 'ng'")
    except Exception as e:
        print(f"  Error: {e}")

    # Test querying with uppercase 'NG' in a fresh transaction
    print("\nTesting query with uppercase 'NG':")
    try:
        result = conn.execute(text("SELECT * FROM source WHERE jurisdiction = 'NG'"))
        rows = result.fetchall()
        print(f"  Found {len(rows)} rows with jurisdiction = 'NG'")
    except Exception as e:
        print(f"  Error: {e}")

# Now check what's actually in the database using a new connection
print("\nChecking actual values in database:")
engine2 = create_engine(str(settings.DATABASE_URL).replace("+asyncpg", ""))
with engine2.connect() as conn:
    result = conn.execute(text("SELECT jurisdiction FROM source"))
    rows = result.fetchall()
    for i, row in enumerate(rows):
        print(f"  Row {i}: {repr(row[0])} (type: {type(row[0])})")

    # Count total rows
    result2 = conn.execute(text("SELECT COUNT(*) FROM source"))
    count = result2.scalar()
    print(f"Total rows in source table: {count}")

# Test using the enum value directly
print(f"\nTesting with Jurisdiction.NG.value: {repr(Jurisdiction.NG.value)}")
engine3 = create_engine(str(settings.DATABASE_URL).replace("+asyncpg", ""))
with engine3.connect() as conn:
    try:
        result = conn.execute(text("SELECT * FROM source WHERE jurisdiction = :val"),
                            {"val": Jurisdiction.NG.value})
        rows = result.fetchall()
        print(f"  Found {len(rows)} rows with jurisdiction = :val (where val = {repr(Jurisdiction.NG.value)})")
    except Exception as e:
        print(f"  Error: {e}")