import db

def fix():
    conn = db.get_db_connection()
    if not conn:
        print("Could not connect to DB.")
        return
        
    try:
        with conn.cursor() as cursor:
            # Let's see what columns exist in the notes table
            cursor.execute("SHOW COLUMNS FROM notes")
            columns = [col['Field'] for col in cursor.fetchall()]
            print("Existing columns:", columns)
            
            if 'session_id' not in columns:
                print("Adding session_id column...")
                cursor.execute("ALTER TABLE notes ADD COLUMN session_id VARCHAR(255) NULL")
                conn.commit()
                print("session_id added.")
            else:
                print("session_id already exists.")
                
            if 'user_id' not in columns:
                print("Adding user_id column...")
                cursor.execute("ALTER TABLE notes ADD COLUMN user_id INT NULL")
                cursor.execute("ALTER TABLE notes ADD FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE")
                conn.commit()
                print("user_id added.")
            else:
                print("user_id already exists.")
                
    except Exception as e:
        print("Error:", e)
    finally:
        conn.close()

if __name__ == '__main__':
    fix()
