"""
db_migrate.py — Safe, incremental schema migrations for NeoNotes.
Run this ONCE on an existing database to apply upgrades.
Usage: python db_migrate.py
"""
import sys
from db import engine
from sqlalchemy import text, inspect


def column_exists(conn, table, column):
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
    ), {"t": table, "c": column})
    return result.scalar() > 0


def index_exists(conn, table, index):
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :i"
    ), {"t": table, "i": index})
    return result.scalar() > 0


def fts_index_exists(conn, table, index):
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t "
        "AND INDEX_NAME = :i AND INDEX_TYPE = 'FULLTEXT'"
    ), {"t": table, "i": index})
    return result.scalar() > 0


migrations = []


def migration(fn):
    migrations.append(fn)
    return fn


# ── Migration 001: Add updated_at to neo_notes ───────────────────────────────
@migration
def m001_add_updated_at(conn):
    if not column_exists(conn, "neo_notes", "updated_at"):
        conn.execute(text(
            "ALTER TABLE neo_notes "
            "ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP "
            "ON UPDATE CURRENT_TIMESTAMP"
        ))
        print("  [001] ✓ Added updated_at to neo_notes")
    else:
        print("  [001] — updated_at already exists, skip")


# ── Migration 002: Add soft-delete column ────────────────────────────────────
@migration
def m002_add_soft_delete(conn):
    if not column_exists(conn, "neo_notes", "deleted_at"):
        conn.execute(text(
            "ALTER TABLE neo_notes ADD COLUMN deleted_at TIMESTAMP NULL DEFAULT NULL"
        ))
        print("  [002] ✓ Added deleted_at (soft-delete) to neo_notes")
    else:
        print("  [002] — deleted_at already exists, skip")


# ── Migration 003: Composite indexes ─────────────────────────────────────────
@migration
def m003_add_indexes(conn):
    indexes = [
        ("neo_notes",          "idx_notes_user_created",    "CREATE INDEX idx_notes_user_created ON neo_notes(user_id, created_at DESC)"),
        ("neo_notes",          "idx_notes_session_created", "CREATE INDEX idx_notes_session_created ON neo_notes(session_id, created_at DESC)"),
        ("neo_folders",        "idx_folders_user",          "CREATE INDEX idx_folders_user ON neo_folders(user_id)"),
        ("neo_archived_notes", "idx_archived_user",         "CREATE INDEX idx_archived_user ON neo_archived_notes(user_id, archived_at DESC)"),
    ]
    for table, idx_name, ddl in indexes:
        if not index_exists(conn, table, idx_name):
            conn.execute(text(ddl))
            print(f"  [003] ✓ Created index {idx_name}")
        else:
            print(f"  [003] — {idx_name} already exists, skip")


# ── Migration 004: Full-Text Search index ────────────────────────────────────
@migration
def m004_fulltext_search(conn):
    if not fts_index_exists(conn, "neo_notes", "ft_notes"):
        conn.execute(text(
            "ALTER TABLE neo_notes ADD FULLTEXT INDEX ft_notes (title, content)"
        ))
        print("  [004] ✓ Added FULLTEXT index ft_notes(title, content)")
    else:
        print("  [004] — FULLTEXT index already exists, skip")


# ── Migration 005: Rebuild Active_Hackers_View to exclude soft-deleted ────────
@migration
def m005_update_view(conn):
    conn.execute(text("""
        CREATE OR REPLACE VIEW Active_Hackers_View AS
        SELECT u.id, u.username, COUNT(n.id) as note_count
        FROM neo_users u
        LEFT JOIN neo_notes n ON u.id = n.user_id AND n.deleted_at IS NULL
        GROUP BY u.id
    """))
    print("  [005] ✓ Rebuilt Active_Hackers_View")


# ── Runner ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== NeoNotes DB Migrations ===")
    try:
        with engine.begin() as conn:
            for fn in migrations:
                fn(conn)
        print("\nAll migrations applied successfully.")
    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        sys.exit(1)
