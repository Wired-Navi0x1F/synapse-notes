import uuid, re, os, subprocess, io, zipfile, csv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db_connection

app = Flask(__name__)
app.secret_key = 'super_secret_neo_mythic_key' # In production, use os.urandom(24)

@app.before_request
def ensure_session_id():
    session.permanent = True
    if 'user_id' not in session and 'guest_id' not in session:
        session['guest_id'] = str(uuid.uuid4())

def log_event(action, detail):
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cursor:
            user_id = session.get('user_id')
            guest_id = session.get('guest_id')
            cursor.execute("INSERT INTO neo_logs (action, detail, user_id, session_id) VALUES (%s, %s, %s, %s)",
                           (action, detail, user_id, guest_id))
        conn.commit()
        conn.close()

def get_untitled_title(cursor, user_id=None, guest_id=None):
    if user_id:
        cursor.execute("SELECT title FROM neo_notes WHERE user_id = %s AND title LIKE 'Untitled%%'", (user_id,))
    else:
        cursor.execute("SELECT title FROM neo_notes WHERE session_id = %s AND title LIKE 'Untitled%%'", (guest_id,))
    existing = [row['title'] for row in cursor.fetchall()]
    if not existing:
        return "Untitled"
    nums = []
    for t in existing:
        if t == 'Untitled':
            nums.append(0)
        else:
            parts = t.split('Untitled ')
            if len(parts) == 2 and parts[1].isdigit():
                nums.append(int(parts[1]))
    next_num = max(nums) + 1 if nums else 0
    return f"Untitled {next_num}" if next_num > 0 else "Untitled"

@app.context_processor
def inject_notes():
    notes = []
    folders = []
    all_tags = set()
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cursor:
            if 'user_id' in session:
                cursor.execute("SELECT * FROM neo_notes WHERE user_id = %s ORDER BY created_at DESC", (session['user_id'],))
                notes = cursor.fetchall()
                cursor.execute("SELECT * FROM neo_folders WHERE user_id = %s ORDER BY created_at ASC", (session['user_id'],))
                folders = cursor.fetchall()
            elif 'guest_id' in session:
                cursor.execute("SELECT * FROM neo_notes WHERE session_id = %s ORDER BY created_at DESC", (session['guest_id'],))
                notes = cursor.fetchall()
                cursor.execute("SELECT * FROM neo_folders WHERE session_id = %s ORDER BY created_at ASC", (session['guest_id'],))
                folders = cursor.fetchall()
                
            for note in notes:
                # Extract #tags
                tags = re.findall(r'(?<!\w)#(\w+)', note['content'])
                all_tags.update(tags)
        conn.close()
    return dict(all_notes=notes, all_folders=folders, all_tags=sorted(list(all_tags)))

@app.route('/')
def index():
    conn = get_db_connection()
    notes = []
    if conn:
        with conn.cursor() as cursor:
            if 'user_id' in session:
                cursor.execute("SELECT * FROM neo_notes WHERE user_id = %s ORDER BY created_at DESC", (session['user_id'],))
            else:
                cursor.execute("SELECT * FROM neo_notes WHERE session_id = %s ORDER BY created_at DESC", (session['guest_id'],))
            notes = cursor.fetchall()
        conn.close()
    return render_template('index.html', notes=notes)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cursor:
                    # Check if username exists
                    cursor.execute("SELECT * FROM neo_users WHERE username = %s", (username,))
                    if cursor.fetchone():
                        flash('Username already exists.', 'error')
                        return redirect(url_for('signup'))
                    
                    hashed_pw = generate_password_hash(password)
                    cursor.execute("INSERT INTO neo_users (username, password_hash) VALUES (%s, %s)", (username, hashed_pw))
                    conn.commit()
                    log_event('SIGNUP', f'User registered: {username}')
                    flash('Signup successful! Please log in.', 'success')
                    return redirect(url_for('login'))
            except Exception as e:
                flash(f'Error signing up: {e}', 'error')
            finally:
                conn.close()
                
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM neo_users WHERE username = %s", (username,))
                    user = cursor.fetchone()
                    
                    if user and check_password_hash(user['password_hash'], password):
                        session['user_id'] = user['id']
                        session['username'] = user['username']
                        # Optional: transfer guest notes to user account
                        if 'guest_id' in session:
                            cursor.execute("UPDATE neo_notes SET user_id = %s, session_id = NULL WHERE session_id = %s", (user['id'], session['guest_id']))
                            conn.commit()
                            session.pop('guest_id')
                        
                        log_event('LOGIN', f'User logged in: {username}')
                        flash('Logged in successfully!', 'success')
                        return redirect(url_for('index'))
                    else:
                        flash('Invalid username or password.', 'error')
            finally:
                conn.close()
                
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))

@app.route('/create', methods=['GET', 'POST'])
def create():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        
        if not content:
            flash('Cannot save an empty note.', 'error')
            return redirect(url_for('create'))
        
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cursor:
                    if not title:
                        title = get_untitled_title(cursor, user_id=session.get('user_id'), guest_id=session.get('guest_id'))
                        
                    folder_id = request.form.get('folder_id')
                    folder_id = folder_id if folder_id else None
                    if 'user_id' in session:
                        cursor.execute("INSERT INTO neo_notes (title, content, folder_id, user_id) VALUES (%s, %s, %s, %s)", 
                                       (title, content, folder_id, session['user_id']))
                    else:
                        cursor.execute("INSERT INTO neo_notes (title, content, folder_id, session_id) VALUES (%s, %s, %s, %s)", 
                                       (title, content, folder_id, session['guest_id']))
                    new_id = cursor.lastrowid
                    conn.commit()
                    flash('Note created!', 'success')
                    return redirect(url_for('edit', id=new_id))
            finally:
                conn.close()
    return render_template('note_form.html', note=None)

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit(id):
    conn = get_db_connection()
    if not conn:
        flash('Database connection error.', 'error')
        return redirect(url_for('index'))
        
    try:
        with conn.cursor() as cursor:
            # Fetch note to ensure it belongs to the current user/guest
            if 'user_id' in session:
                cursor.execute("SELECT * FROM neo_notes WHERE id = %s AND user_id = %s", (id, session['user_id']))
            else:
                cursor.execute("SELECT * FROM neo_notes WHERE id = %s AND session_id = %s", (id, session['guest_id']))
            
            note = cursor.fetchone()
            
            if not note:
                flash('Note not found or unauthorized.', 'error')
                return redirect(url_for('index'))
                
            if request.method == 'POST':
                title = request.form.get('title', '').strip()
                content = request.form.get('content', '').strip()
                
                if not content:
                    flash('Cannot save an empty note.', 'error')
                    return redirect(url_for('edit', id=id))
                    
                if not title:
                    title = get_untitled_title(cursor, user_id=session.get('user_id'), guest_id=session.get('guest_id'))
                    
                folder_id = request.form.get('folder_id')
                folder_id = folder_id if folder_id else None
                cursor.execute("UPDATE neo_notes SET title = %s, content = %s, folder_id = %s WHERE id = %s", (title, content, folder_id, id))
                conn.commit()
                log_event('EDIT_NOTE', f'Note updated: {title} (ID: {id})')
                flash('Note updated successfully.', 'success')
                return redirect(url_for('edit', id=id))
    finally:
        conn.close()
        
    return render_template('note_form.html', note=note)

@app.route('/delete/<int:id>', methods=['POST'])
def delete(id):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                if 'user_id' in session:
                    cursor.execute("DELETE FROM neo_notes WHERE id = %s AND user_id = %s", (id, session['user_id']))
                else:
                    cursor.execute("DELETE FROM neo_notes WHERE id = %s AND session_id = %s", (id, session['guest_id']))
                conn.commit()
                log_event('DELETE_NOTE', f'Note deleted: ID {id}')
                flash('Note deleted.', 'success')
        finally:
            conn.close()
    return redirect(url_for('index'))

@app.route('/api/autosave/<int:id>', methods=['POST'])
def autosave(id):
    data = request.get_json()
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()
    
    if not content:
        return jsonify({"status": "error", "message": "empty content"}), 400
        
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                # Security check and Row-Level Lock
                if 'user_id' in session:
                    cursor.execute("SELECT id FROM neo_notes WHERE id = %s AND user_id = %s FOR UPDATE", (id, session['user_id']))
                else:
                    cursor.execute("SELECT id FROM neo_notes WHERE id = %s AND session_id = %s FOR UPDATE", (id, session['guest_id']))
                
                if not cursor.fetchone():
                    return jsonify({"status": "error", "message": "unauthorized"}), 403
                    
                if not title:
                    title = get_untitled_title(cursor, user_id=session.get('user_id'), guest_id=session.get('guest_id'))
                    
                cursor.execute("UPDATE neo_notes SET title = %s, content = %s WHERE id = %s", (title, content, id))
                conn.commit()
                return jsonify({"status": "success", "title": title})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
        finally:
            conn.close()
    return jsonify({"status": "error"}), 500

@app.route('/admin')
def admin():
    if session.get('username') != 'admin':
        flash('ACCESS DENIED: ADMIN PRIVILEGES REQUIRED', 'error')
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    all_db_users = []
    all_db_notes = []
    all_db_logs = []
    if conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM Active_Hackers_View ORDER BY note_count DESC")
            all_db_users = cursor.fetchall()
            cursor.execute("SELECT * FROM neo_notes ORDER BY created_at DESC")
            all_db_notes = cursor.fetchall()
            cursor.execute("SELECT * FROM neo_logs ORDER BY timestamp DESC LIMIT 100")
            all_db_logs = cursor.fetchall()
        conn.close()
    return render_template('admin.html', users=all_db_users, notes=all_db_notes, logs=all_db_logs)

@app.route('/admin/delete_user/<int:id>', methods=['POST'])
def admin_delete_user(id):
    if session.get('username') != 'admin':
        return redirect(url_for('index'))
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cursor:
            cursor.execute("CALL PurgeUser(%s)", (id,))
        conn.commit()
        conn.close()
    flash(f'USER {id} PURGED VIA STORED PROCEDURE.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/delete_note/<int:id>', methods=['POST'])
def admin_delete_note(id):
    if session.get('username') != 'admin':
        return redirect(url_for('index'))
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM neo_notes WHERE id = %s", (id,))
        conn.commit()
        conn.close()
    flash(f'NOTE {id} DELETED.', 'success')
    return redirect(url_for('admin'))

@app.route('/archive/<int:id>', methods=['POST'])
def archive(id):
    conn = get_db_connection()
    if conn:
        try:
            conn.begin() # Start ACID Transaction
            with conn.cursor() as cursor:
                if 'user_id' in session:
                    cursor.execute("SELECT * FROM neo_notes WHERE id = %s AND user_id = %s FOR UPDATE", (id, session['user_id']))
                else:
                    cursor.execute("SELECT * FROM neo_notes WHERE id = %s AND session_id = %s FOR UPDATE", (id, session['guest_id']))
                note = cursor.fetchone()
                
                if note:
                    cursor.execute("""
                        INSERT INTO neo_archived_notes (id, title, content, folder_id, user_id, session_id, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (note['id'], note['title'], note['content'], note['folder_id'], note['user_id'], note['session_id'], note['created_at']))
                    
                    cursor.execute("DELETE FROM neo_notes WHERE id = %s", (id,))
            conn.commit()
            log_event('ARCHIVE_NOTE', f'Note {id} archived using ACID transaction.')
            flash('Note archived successfully.', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Transaction failed: {e}', 'error')
        finally:
            conn.close()
    return redirect(url_for('index'))

@app.route('/archive_vault')
def archive_vault():
    conn = get_db_connection()
    archived_notes = []
    if conn:
        with conn.cursor() as cursor:
            if 'user_id' in session:
                cursor.execute("SELECT * FROM neo_archived_notes WHERE user_id = %s ORDER BY archived_at DESC", (session['user_id'],))
            else:
                cursor.execute("SELECT * FROM neo_archived_notes WHERE session_id = %s ORDER BY archived_at DESC", (session['guest_id'],))
            archived_notes = cursor.fetchall()
        conn.close()
    return render_template('archive.html', archived_notes=archived_notes)

@app.route('/restore/<int:id>', methods=['POST'])
def restore(id):
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cursor:
            try:
                conn.begin()
                cursor.execute("SELECT * FROM neo_archived_notes WHERE id = %s FOR UPDATE", (id,))
                note = cursor.fetchone()
                
                if note:
                    cursor.execute("INSERT INTO neo_notes (id, title, content, folder_id, user_id, session_id, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)", 
                                   (note['id'], note['title'], note['content'], note['folder_id'], note['user_id'], note['session_id'], note['created_at']))
                    cursor.execute("DELETE FROM neo_archived_notes WHERE id = %s", (id,))
                    conn.commit()
                    log_event('RESTORE_NOTE', f'Note restored: {note["title"]} (ID: {id})')
                    flash('Note successfully restored to workspace.', 'success')
                else:
                    conn.rollback()
                    flash('Note not found in archive.', 'error')
            except Exception as e:
                conn.rollback()
                flash('Restore failed: ' + str(e), 'error')
            finally:
                conn.close()
    return redirect(url_for('archive_vault'))

@app.route('/admin/backup', methods=['POST'])
def backup():
    if session.get('username') != 'admin':
        return redirect(url_for('index'))
        
    os.makedirs('backups', exist_ok=True)
    backup_path = os.path.join('backups', f'backup_{uuid.uuid4().hex[:8]}.sql')
    
    # Run mysqldump
    try:
        subprocess.run(['mysqldump', '-uroot', '-proot123', 'SEE'], stdout=open(backup_path, 'w'), check=True)
        log_event('BACKUP', f'Database backup generated at {backup_path}')
        flash(f'Backup successful: {backup_path}', 'success')
    except Exception as e:
        flash(f'Backup failed: {e}', 'error')
        
    return redirect(url_for('admin'))

@app.route('/create_folder', methods=['POST'])
def create_folder():
    name = request.form.get('folder_name', '').strip()
    if not name:
        flash('Folder name cannot be empty.', 'error')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cursor:
            if 'user_id' in session:
                cursor.execute("INSERT INTO neo_folders (name, user_id) VALUES (%s, %s)", (name, session['user_id']))
            else:
                cursor.execute("INSERT INTO neo_folders (name, session_id) VALUES (%s, %s)", (name, session['guest_id']))
            conn.commit()
            log_event('CREATE_FOLDER', f'Folder created: {name}')
        conn.close()
        flash(f'Folder "{name}" created.', 'success')
    return redirect(url_for('index'))

@app.route('/open_note/<path:title>')
def open_note(title):
    import urllib.parse
    title = urllib.parse.unquote(title)
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cursor:
            if 'user_id' in session:
                cursor.execute("SELECT id FROM neo_notes WHERE title = %s AND user_id = %s LIMIT 1", (title, session['user_id']))
            else:
                cursor.execute("SELECT id FROM neo_notes WHERE title = %s AND session_id = %s LIMIT 1", (title, session['guest_id']))
            note = cursor.fetchone()
        conn.close()
        
        if note:
            return redirect(url_for('edit', id=note['id']))
        else:
            flash(f"Note '{title}' not found.", 'error')
    return redirect(url_for('index'))

@app.route('/admin/export_logs')
def admin_export_logs():
    if session.get('username') != 'admin':
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM neo_logs ORDER BY timestamp DESC")
            logs = cursor.fetchall()
        conn.close()
        
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Action', 'Detail', 'User ID', 'Session ID', 'Timestamp'])
    for log in logs:
        writer.writerow([log['id'], log['action'], log['detail'], log['user_id'], log['session_id'], log['timestamp']])
        
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=system_logs.csv"}
    )

@app.route('/api/graph_data')
def api_graph_data():
    conn = get_db_connection()
    nodes = []
    edges = []
    if conn:
        with conn.cursor() as cursor:
            if 'user_id' in session:
                cursor.execute("SELECT id, title, content FROM neo_notes WHERE user_id = %s", (session['user_id'],))
            else:
                cursor.execute("SELECT id, title, content FROM neo_notes WHERE session_id = %s", (session['guest_id'],))
            notes = cursor.fetchall()
            
            # Map normalized titles to IDs for creating edge links (case-insensitive, whitespace stripped)
            title_to_id = {note['title'].strip().lower(): note['id'] for note in notes}
            
            for note in notes:
                nodes.append({
                    "id": note['id'],
                    "name": note['title'],
                    "val": len(note['content'] or '') / 100 + 1  # Node size based on content length
                })
                
                # Extract [[Links]]
                links = re.findall(r'\[\[(.*?)\]\]', note['content'])
                for link in links:
                    normalized_link = link.strip().lower()
                    if normalized_link in title_to_id:
                        edges.append({
                            "source": note['id'],
                            "target": title_to_id[normalized_link]
                        })
        conn.close()
    return jsonify({"nodes": nodes, "links": edges})

@app.route('/the_wired')
def the_wired():
    return render_template('wired.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
