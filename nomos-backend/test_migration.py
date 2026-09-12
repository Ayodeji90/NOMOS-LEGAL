import sys
sys.path.append('.')
from app.db.session import db_manager
from app.db.init import run_migrations
import asyncio

async def setup():
    # Initialize database (synchronous call)
    db_manager.initialize()
    # Run migrations (synchronous call)
    run_migrations()
    print('Database migrated successfully')

def main():
    asyncio.run(setup())

if __name__ == "__main__":
    main()