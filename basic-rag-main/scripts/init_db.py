from db.db import engine
from db.models import Base

def main():
    print("Creating tables in PostgreSQL...")
    try:
        Base.metadata.create_all(bind=engine)
        print("Done.")
    except Exception as exc:
        print("Database initialization failed.")
        print(
            "Check that PostgreSQL is running and that DATABASE_URL in .env "
            "contains the correct username, password, host, port, and database name."
        )
        raise

if __name__ == "__main__":
    main()
