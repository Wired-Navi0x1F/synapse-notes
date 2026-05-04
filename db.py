import pymysql
import os

# DB Credentials based on user input
DB_HOST = 'localhost'
DB_USER = 'root'
DB_PASSWORD = 'root123'
DB_NAME = 'SEE'

def get_db_connection():
    try:
        connection = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            cursorclass=pymysql.cursors.DictCursor
        )
        return connection
    except pymysql.MySQLError as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def init_db():
    connection = get_db_connection()
    if not connection:
        # Try connecting without DB_NAME to see if we need to create it
        try:
            connection = pymysql.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                cursorclass=pymysql.cursors.DictCursor
            )
            with connection.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
            connection.commit()
            connection.select_db(DB_NAME)
        except pymysql.MySQLError as e:
            print(f"Error creating database: {e}")
            return
            
    with connection.cursor() as cursor:
        cursor.execute("DROP TABLE IF EXISTS neo_notes")
        cursor.execute("DROP TABLE IF EXISTS neo_folders")
        cursor.execute("DROP TABLE IF EXISTS neo_users")
        
        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS neo_users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(150) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create folders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS neo_folders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                user_id INT NULL,
                session_id VARCHAR(255) NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES neo_users(id) ON DELETE CASCADE
            )
        """)
        
        # Create notes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS neo_notes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                folder_id INT NULL,
                user_id INT NULL,
                session_id VARCHAR(255) NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES neo_users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES neo_folders(id) ON DELETE SET NULL
            )
        """)
        
        # Create logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS neo_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                action VARCHAR(100) NOT NULL,
                detail TEXT NOT NULL,
                user_id INT NULL,
                session_id VARCHAR(255) NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create archived notes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS neo_archived_notes (
                id INT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                folder_id INT NULL,
                user_id INT NULL,
                session_id VARCHAR(255) NULL,
                created_at TIMESTAMP,
                archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create Indexes
        try:
            cursor.execute("CREATE INDEX idx_user ON neo_notes(user_id)")
            cursor.execute("CREATE INDEX idx_session ON neo_notes(session_id)")
        except Exception:
            pass # Ignore if indexes already exist

        # Create View
        cursor.execute("""
            CREATE OR REPLACE VIEW Active_Hackers_View AS 
            SELECT u.id, u.username, COUNT(n.id) as note_count 
            FROM neo_users u 
            LEFT JOIN neo_notes n ON u.id = n.user_id 
            GROUP BY u.id
        """)

        # Create Trigger
        cursor.execute("DROP TRIGGER IF EXISTS after_note_insert")
        cursor.execute("""
            CREATE TRIGGER after_note_insert
            AFTER INSERT ON neo_notes
            FOR EACH ROW
            BEGIN
                INSERT INTO neo_logs (action, detail, user_id, session_id) 
                VALUES ('CREATE_NOTE', CONCAT('Note created (Trigger): ', NEW.title, ' (ID: ', NEW.id, ')'), NEW.user_id, NEW.session_id);
            END;
        """)

        # Create Stored Procedure
        cursor.execute("DROP PROCEDURE IF EXISTS PurgeUser")
        cursor.execute("""
            CREATE PROCEDURE PurgeUser(IN uid INT)
            BEGIN
                DELETE FROM neo_users WHERE id = uid;
                INSERT INTO neo_logs (action, detail) VALUES ('PURGE_USER', CONCAT('User ', uid, ' purged via Stored Procedure'));
            END;
        """)
    connection.commit()
    connection.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
