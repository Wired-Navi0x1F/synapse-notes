import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

load_dotenv()

DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_USER     = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME     = os.getenv("DB_NAME", "SEE")

# ── Connection Pool ──────────────────────────────────────────────────────────
# pool_pre_ping ensures dead connections are detected before use.
# pool_recycle recycles connections every hour to avoid MySQL's wait_timeout.
engine = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}",
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)


def init_db():
    """
    SAFE schema initialiser — only CREATEs, never DROPs existing tables.
    Run db_migrate.py for schema upgrades on an existing database.
    """
    with engine.begin() as conn:

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS neo_users (
                id            INT AUTO_INCREMENT PRIMARY KEY,
                username      VARCHAR(150) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS neo_folders (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                name       VARCHAR(255) NOT NULL,
                user_id    INT NULL,
                session_id VARCHAR(255) NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES neo_users(id) ON DELETE CASCADE
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS neo_notes (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                title      VARCHAR(255) NOT NULL,
                content    TEXT NOT NULL,
                folder_id  INT NULL,
                user_id    INT NULL,
                session_id VARCHAR(255) NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                deleted_at TIMESTAMP NULL DEFAULT NULL,
                FOREIGN KEY (user_id)   REFERENCES neo_users(id)   ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES neo_folders(id) ON DELETE SET NULL
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS neo_archived_notes (
                id         INT PRIMARY KEY,
                title      VARCHAR(255) NOT NULL,
                content    TEXT NOT NULL,
                folder_id  INT NULL,
                user_id    INT NULL,
                session_id VARCHAR(255) NULL,
                created_at TIMESTAMP,
                archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Indexes (ignore if already exist)
        for ddl in [
            "CREATE INDEX IF NOT EXISTS idx_notes_user_created    ON neo_notes(user_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_notes_session_created ON neo_notes(session_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_folders_user          ON neo_folders(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_archived_user         ON neo_archived_notes(user_id, archived_at DESC)",
        ]:
            try:
                conn.execute(text(ddl))
            except Exception:
                pass

        # View
        conn.execute(text("""
            CREATE OR REPLACE VIEW Active_Hackers_View AS
            SELECT u.id, u.username, COUNT(n.id) as note_count
            FROM neo_users u
            LEFT JOIN neo_notes n ON u.id = n.user_id AND n.deleted_at IS NULL
            GROUP BY u.id
        """))

        # Stored procedure
        conn.execute(text("DROP PROCEDURE IF EXISTS PurgeUser"))
        conn.execute(text("""
            CREATE PROCEDURE PurgeUser(IN uid INT)
            BEGIN
                DELETE FROM neo_users WHERE id = uid;
            END
        """))

    print("Database initialised successfully.")


if __name__ == "__main__":
    init_db()
