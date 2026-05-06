import uuid, re, os, subprocess
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text
from db import engine

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev_secret_change_in_prod')


# ─────────────────────────────────────────────────────────────
#  BEFORE REQUEST
# ─────────────────────────────────────────────────────────────
@app.before_request
def ensure_session_id():
    session.permanent = True
    if 'user_id' not in session and 'guest_id' not in session:
        session['guest_id'] = str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────
def get_untitled_title(conn, user_id=None, guest_id=None):
    if user_id:
        rows = conn.execute(
            text("SELECT title FROM neo_notes WHERE user_id = :uid AND title LIKE 'Untitled%'"),
            {"uid": user_id}
        ).fetchall()
    else:
        rows = conn.execute(
            text("SELECT title FROM neo_notes WHERE session_id = :sid AND title LIKE 'Untitled%'"),
            {"sid": guest_id}
        ).fetchall()
    existing = [r[0] for r in rows]
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


# ─────────────────────────────────────────────────────────────
#  CONTEXT PROCESSOR — sidebar data on every request
# ─────────────────────────────────────────────────────────────
@app.context_processor
def inject_notes():
    notes, folders, all_tags = [], [], set()
    try:
        with engine.connect() as conn:
            if 'user_id' in session:
                uid = session['user_id']
                notes = [dict(r) for r in conn.execute(
                    text("SELECT * FROM neo_notes WHERE user_id = :uid ORDER BY created_at DESC"),
                    {"uid": uid}
                ).mappings().fetchall()]
                folders = [dict(r) for r in conn.execute(
                    text("SELECT * FROM neo_folders WHERE user_id = :uid ORDER BY created_at ASC"),
                    {"uid": uid}
                ).mappings().fetchall()]
            elif 'guest_id' in session:
                sid = session['guest_id']
                notes = [dict(r) for r in conn.execute(
                    text("SELECT * FROM neo_notes WHERE session_id = :sid ORDER BY created_at DESC"),
                    {"sid": sid}
                ).mappings().fetchall()]
                folders = [dict(r) for r in conn.execute(
                    text("SELECT * FROM neo_folders WHERE session_id = :sid ORDER BY created_at ASC"),
                    {"sid": sid}
                ).mappings().fetchall()]
            for note in notes:
                tags = re.findall(r'(?<!\w)#(\w+)', note.get('content') or '')
                all_tags.update(tags)
    except Exception as e:
        print(f"[inject_notes] DB error: {e}")
    return dict(all_notes=notes, all_folders=folders, all_tags=sorted(list(all_tags)))


# ─────────────────────────────────────────────────────────────
#  ROUTES — PUBLIC
# ─────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        try:
            with engine.connect() as conn:
                existing = conn.execute(
                    text("SELECT id FROM neo_users WHERE username = :u"), {"u": username}
                ).fetchone()
                if existing:
                    flash('Username already exists.', 'error')
                    return redirect(url_for('signup'))
            with engine.begin() as conn:
                conn.execute(
                    text("INSERT INTO neo_users (username, password_hash) VALUES (:u, :p)"),
                    {"u": username, "p": generate_password_hash(password)}
                )
            flash('Signup successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Error signing up: {e}', 'error')
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        try:
            with engine.connect() as conn:
                user = conn.execute(
                    text("SELECT * FROM neo_users WHERE username = :u"), {"u": username}
                ).mappings().fetchone()

                if user and check_password_hash(user['password_hash'], password):
                    user = dict(user)
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    # Transfer guest notes on login
                    if 'guest_id' in session:
                        with engine.begin() as wconn:
                            wconn.execute(
                                text("UPDATE neo_notes SET user_id = :uid, session_id = NULL WHERE session_id = :sid"),
                                {"uid": user['id'], "sid": session['guest_id']}
                            )
                        session.pop('guest_id')
                    flash('Logged in successfully!', 'success')
                    return redirect(url_for('index'))
                else:
                    flash('Invalid username or password.', 'error')
        except Exception as e:
            flash(f'Login error: {e}', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))


# ─────────────────────────────────────────────────────────────
#  ROUTES — NOTES CRUD
# ─────────────────────────────────────────────────────────────
@app.route('/create', methods=['GET', 'POST'])
def create():
    if request.method == 'POST':
        title   = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        if not content and not title:
            flash('Cannot save a completely empty note.', 'error')
            return redirect(url_for('create'))
        try:
            with engine.begin() as conn:
                if not title:
                    title = get_untitled_title(conn,
                                               user_id=session.get('user_id'),
                                               guest_id=session.get('guest_id'))
                folder_id = request.form.get('folder_id') or None
                if 'user_id' in session:
                    result = conn.execute(
                        text("INSERT INTO neo_notes (title, content, folder_id, user_id) VALUES (:t, :c, :f, :uid)"),
                        {"t": title, "c": content, "f": folder_id, "uid": session['user_id']}
                    )
                else:
                    result = conn.execute(
                        text("INSERT INTO neo_notes (title, content, folder_id, session_id) VALUES (:t, :c, :f, :sid)"),
                        {"t": title, "c": content, "f": folder_id, "sid": session['guest_id']}
                    )
                new_id = result.lastrowid
            flash('Note created!', 'success')
            return redirect(url_for('edit', id=new_id))
        except Exception as e:
            flash(f'Error creating note: {e}', 'error')
    return render_template('note_form.html', note=None)


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit(id):
    try:
        with engine.connect() as conn:
            if 'user_id' in session:
                note = conn.execute(
                    text("SELECT * FROM neo_notes WHERE id = :id AND user_id = :uid"),
                    {"id": id, "uid": session['user_id']}
                ).mappings().fetchone()
            else:
                note = conn.execute(
                    text("SELECT * FROM neo_notes WHERE id = :id AND session_id = :sid"),
                    {"id": id, "sid": session['guest_id']}
                ).mappings().fetchone()
            if not note:
                flash('Note not found or unauthorized.', 'error')
                return redirect(url_for('index'))
            note = dict(note)

        if request.method == 'POST':
            title   = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            if not content and not title:
                flash('Cannot save a completely empty note.', 'error')
                return redirect(url_for('edit', id=id))
            folder_id = request.form.get('folder_id') or None
            with engine.begin() as conn:
                if not title:
                    title = get_untitled_title(conn,
                                               user_id=session.get('user_id'),
                                               guest_id=session.get('guest_id'))
                conn.execute(
                    text("UPDATE neo_notes SET title = :t, content = :c, folder_id = :f WHERE id = :id"),
                    {"t": title, "c": content, "f": folder_id, "id": id}
                )
            flash('Note updated successfully.', 'success')
            return redirect(url_for('edit', id=id))
    except Exception as e:
        flash(f'Database error: {e}', 'error')
        return redirect(url_for('index'))
    return render_template('note_form.html', note=note)


@app.route('/delete/<int:id>', methods=['POST'])
def delete(id):
    try:
        with engine.begin() as conn:
            if 'user_id' in session:
                result = conn.execute(
                    text("DELETE FROM neo_notes WHERE id = :id AND user_id = :uid"),
                    {"id": id, "uid": session['user_id']}
                )
            else:
                result = conn.execute(
                    text("DELETE FROM neo_notes WHERE id = :id AND session_id = :sid"),
                    {"id": id, "sid": session['guest_id']}
                )
            if result.rowcount == 0:
                flash('Unauthorized or note not found.', 'error')
            else:
                flash('Note deleted.', 'success')
    except Exception as e:
        flash(f'Deletion failed: {e}', 'error')
    return redirect(url_for('index'))


@app.route('/api/autosave/<int:id>', methods=['POST'])
def autosave(id):
    data    = request.get_json()
    title   = data.get('title', '').strip()
    content = data.get('content', '').strip()
    if not content and not title:
        return jsonify({"status": "error", "message": "empty content and title"}), 400
    try:
        with engine.begin() as conn:
            if 'user_id' in session:
                owned = conn.execute(
                    text("SELECT id FROM neo_notes WHERE id = :id AND user_id = :uid FOR UPDATE"),
                    {"id": id, "uid": session['user_id']}
                ).fetchone()
            else:
                owned = conn.execute(
                    text("SELECT id FROM neo_notes WHERE id = :id AND session_id = :sid FOR UPDATE"),
                    {"id": id, "sid": session['guest_id']}
                ).fetchone()
            if not owned:
                return jsonify({"status": "error", "message": "unauthorized"}), 403
            if not title:
                title = get_untitled_title(conn,
                                           user_id=session.get('user_id'),
                                           guest_id=session.get('guest_id'))
            conn.execute(
                text("UPDATE neo_notes SET title = :t, content = :c WHERE id = :id"),
                {"t": title, "c": content, "id": id}
            )
        return jsonify({"status": "success", "title": title})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ─────────────────────────────────────────────────────────────
#  ROUTES — ADMIN
# ─────────────────────────────────────────────────────────────
@app.route('/admin')
def admin():
    if session.get('username') != 'admin':
        flash('ACCESS DENIED: ADMIN PRIVILEGES REQUIRED', 'error')
        return redirect(url_for('index'))
    
    # Query parameters
    search_user = request.args.get('search_user', '').strip()
    filter_user_id = request.args.get('filter_user_id', type=int)
    
    user_page = request.args.get('user_page', 1, type=int)
    note_page = request.args.get('note_page', 1, type=int)
    per_page = 20
    
    users, notes = [], []
    total_users = 0
    total_notes = 0

    try:
        with engine.connect() as conn:
            # Users Query
            user_query_base = "FROM Active_Hackers_View"
            user_params = {}
            if search_user:
                user_query_base += " WHERE username LIKE :search"
                user_params['search'] = f"%{search_user}%"
            
            # Count total users for pagination
            total_users = conn.execute(
                text(f"SELECT COUNT(*) {user_query_base}"), 
                user_params
            ).scalar()
            
            # Fetch users
            user_query = f"SELECT * {user_query_base} ORDER BY note_count DESC LIMIT :limit OFFSET :offset"
            user_params['limit'] = per_page
            user_params['offset'] = (user_page - 1) * per_page
            users = [dict(r) for r in conn.execute(text(user_query), user_params).mappings().fetchall()]

            # Notes Query
            note_query_base = "FROM neo_notes n LEFT JOIN neo_users u ON n.user_id = u.id"
            note_params = {}
            if filter_user_id:
                note_query_base += " WHERE n.user_id = :filter_uid"
                note_params['filter_uid'] = filter_user_id
            
            # Count total notes for pagination
            total_notes = conn.execute(
                text(f"SELECT COUNT(*) {note_query_base}"), 
                note_params
            ).scalar()
            
            # Fetch notes
            note_query = f"SELECT n.*, u.username {note_query_base} ORDER BY n.created_at DESC LIMIT :limit OFFSET :offset"
            note_params['limit'] = per_page
            note_params['offset'] = (note_page - 1) * per_page
            notes = [dict(r) for r in conn.execute(text(note_query), note_params).mappings().fetchall()]
            
    except Exception as e:
        flash(f'DB error: {e}', 'error')
        
    total_user_pages = max(1, (total_users + per_page - 1) // per_page)
    total_note_pages = max(1, (total_notes + per_page - 1) // per_page)
        
    return render_template('admin.html', 
                           users=users, notes=notes,
                           user_page=user_page, note_page=note_page,
                           total_user_pages=total_user_pages, total_note_pages=total_note_pages,
                           total_users=total_users, total_notes=total_notes,
                           per_page=per_page,
                           search_user=search_user, filter_user_id=filter_user_id)


@app.route('/admin/delete_user/<int:id>', methods=['POST'])
def admin_delete_user(id):
    if session.get('username') != 'admin':
        return redirect(url_for('index'))
    try:
        with engine.begin() as conn:
            conn.execute(text("CALL PurgeUser(:id)"), {"id": id})
        flash(f'USER {id} PURGED VIA STORED PROCEDURE.', 'success')
    except Exception as e:
        flash(f'Purge failed: {e}', 'error')
    return redirect(url_for('admin'))


@app.route('/admin/delete_note/<int:id>', methods=['POST'])
def admin_delete_note(id):
    if session.get('username') != 'admin':
        return redirect(url_for('index'))
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM neo_notes WHERE id = :id"), {"id": id})
        flash(f'NOTE {id} DELETED.', 'success')
    except Exception as e:
        flash(f'Delete failed: {e}', 'error')
    return redirect(url_for('admin'))


@app.route('/admin/backup', methods=['POST'])
def backup():
    if session.get('username') != 'admin':
        return redirect(url_for('index'))
    os.makedirs('backups', exist_ok=True)
    backup_path = os.path.join('backups', f'backup_{uuid.uuid4().hex[:8]}.sql')
    try:
        db_user = os.getenv("DB_USER", "root")
        db_pass = os.getenv("DB_PASSWORD", "")
        db_name = os.getenv("DB_NAME", "SEE")
        subprocess.run(
            ['mysqldump', f'-u{db_user}', f'-p{db_pass}', db_name],
            stdout=open(backup_path, 'w'), check=True
        )
        flash(f'Backup successful: {backup_path}', 'success')
    except Exception as e:
        flash(f'Backup failed: {e}', 'error')
    return redirect(url_for('admin'))


# ─────────────────────────────────────────────────────────────
#  ROUTES — ARCHIVE
# ─────────────────────────────────────────────────────────────
@app.route('/archive/<int:id>', methods=['POST'])
def archive(id):
    """
    EXPLICIT TRANSACTION — Archive a note (ACID-compliant).

    This operation requires ATOMICITY: the INSERT into neo_archived_notes and
    the DELETE from neo_notes must BOTH succeed or BOTH fail. If the INSERT
    succeeds but the DELETE fails, we’d have duplicate data. If the DELETE
    succeeds but the INSERT fails, the note is lost forever.

    Transaction behavior (provided by engine.begin()):
      - BEGIN TRANSACTION  ← implicit on entering the `with` block
      - SELECT ... FOR UPDATE  ← acquires a row-level EXCLUSIVE LOCK
        (prevents concurrent reads/writes until COMMIT or ROLLBACK)
      - INSERT INTO neo_archived_notes
      - DELETE FROM neo_notes
      - COMMIT  ← implicit if no exception is raised
      - ROLLBACK  ← implicit if an exception is raised

    ACID Properties demonstrated:
      A (Atomicity):    Both INSERT + DELETE succeed or both roll back.
      C (Consistency):  FK constraints, NOT NULL enforced by MySQL/InnoDB.
      I (Isolation):    FOR UPDATE lock prevents dirty reads.
      D (Durability):   After COMMIT, data is persisted to InnoDB redo log.
    """
    try:
        # BEGIN TRANSACTION (engine.begin() starts an explicit transaction)
        with engine.begin() as conn:
            # Step 1: SELECT ... FOR UPDATE — locks the row to prevent concurrent modification
            if 'user_id' in session:
                note = conn.execute(
                    text("SELECT * FROM neo_notes WHERE id = :id AND user_id = :uid FOR UPDATE"),
                    {"id": id, "uid": session['user_id']}
                ).mappings().fetchone()
            else:
                note = conn.execute(
                    text("SELECT * FROM neo_notes WHERE id = :id AND session_id = :sid FOR UPDATE"),
                    {"id": id, "sid": session['guest_id']}
                ).mappings().fetchone()

            if note:
                note = dict(note)
                # Step 2: INSERT — copy to archive table
                conn.execute(text("""
                    INSERT INTO neo_archived_notes
                        (id, title, content, folder_id, user_id, session_id, created_at)
                    VALUES (:id, :t, :c, :f, :uid, :sid, :ca)
                """), {
                    "id": note['id'], "t": note['title'], "c": note['content'],
                    "f": note['folder_id'], "uid": note['user_id'],
                    "sid": note['session_id'], "ca": note['created_at']
                })
                # Step 3: DELETE — remove from active table
                conn.execute(text("DELETE FROM neo_notes WHERE id = :id"), {"id": id})
                # Step 4: COMMIT — happens automatically when exiting the `with` block
                flash('Note archived successfully.', 'success')
            else:
                flash('Note not found.', 'error')
    except Exception as e:
        # ROLLBACK — happens automatically on exception (both INSERT and DELETE are undone)
        flash(f'Archive failed — transaction rolled back: {e}', 'error')
    return redirect(url_for('index'))


@app.route('/archive_vault')
def archive_vault():
    archived_notes = []
    try:
        with engine.connect() as conn:
            if 'user_id' in session:
                archived_notes = [dict(r) for r in conn.execute(
                    text("SELECT * FROM neo_archived_notes WHERE user_id = :uid ORDER BY archived_at DESC"),
                    {"uid": session['user_id']}
                ).mappings().fetchall()]
            else:
                archived_notes = [dict(r) for r in conn.execute(
                    text("SELECT * FROM neo_archived_notes WHERE session_id = :sid ORDER BY archived_at DESC"),
                    {"sid": session['guest_id']}
                ).mappings().fetchall()]
    except Exception as e:
        flash(f'DB error: {e}', 'error')
    return render_template('archive.html', archived_notes=archived_notes)


@app.route('/restore/<int:id>', methods=['POST'])
def restore(id):
    """
    EXPLICIT TRANSACTION — Restore an archived note (ACID-compliant).

    Mirror of archive(): moves a row from neo_archived_notes back to neo_notes.
    Same transactional guarantees apply — both INSERT + DELETE are atomic.

    Locking: SELECT ... FOR UPDATE prevents another session from restoring
    the same note concurrently (concurrency control via pessimistic locking).
    """
    try:
        # BEGIN TRANSACTION
        with engine.begin() as conn:
            # Acquire exclusive row lock
            note = conn.execute(
                text("SELECT * FROM neo_archived_notes WHERE id = :id FOR UPDATE"),
                {"id": id}
            ).mappings().fetchone()

            if note:
                note = dict(note)
                # INSERT back to active notes
                conn.execute(text("""
                    INSERT INTO neo_notes
                        (id, title, content, folder_id, user_id, session_id, created_at)
                    VALUES (:id, :t, :c, :f, :uid, :sid, :ca)
                """), {
                    "id": note['id'], "t": note['title'], "c": note['content'],
                    "f": note['folder_id'], "uid": note['user_id'],
                    "sid": note['session_id'], "ca": note['created_at']
                })
                # DELETE from archive
                conn.execute(
                    text("DELETE FROM neo_archived_notes WHERE id = :id"), {"id": id}
                )
                # COMMIT (automatic on success)
                flash('Note successfully restored to workspace.', 'success')
            else:
                flash('Note not found in archive.', 'error')
    except Exception as e:
        # ROLLBACK (automatic on exception)
        flash(f'Restore failed — transaction rolled back: {e}', 'error')
    return redirect(url_for('archive_vault'))


# ─────────────────────────────────────────────────────────────
#  ROUTES — FOLDERS
# ─────────────────────────────────────────────────────────────
@app.route('/create_folder', methods=['POST'])
def create_folder():
    name = request.form.get('folder_name', '').strip()
    if not name:
        flash('Folder name cannot be empty.', 'error')
        return redirect(url_for('index'))
    try:
        with engine.begin() as conn:
            if 'user_id' in session:
                conn.execute(
                    text("INSERT INTO neo_folders (name, user_id) VALUES (:n, :uid)"),
                    {"n": name, "uid": session['user_id']}
                )
            else:
                conn.execute(
                    text("INSERT INTO neo_folders (name, session_id) VALUES (:n, :sid)"),
                    {"n": name, "sid": session['guest_id']}
                )
        flash(f'Folder "{name}" created.', 'success')
    except Exception as e:
        flash(f'Error creating folder: {e}', 'error')
    return redirect(url_for('index'))


# ─────────────────────────────────────────────────────────────
#  ROUTES — IMPORT / EXPORT
# ─────────────────────────────────────────────────────────────
@app.route('/export_note/<int:id>')
def export_note(id):
    if 'user_id' not in session:
        flash('Only logged in users can export notes.', 'error')
        return redirect(url_for('index'))
    try:
        with engine.connect() as conn:
            note = conn.execute(
                text("SELECT * FROM neo_notes WHERE id = :id AND user_id = :uid"),
                {"id": id, "uid": session['user_id']}
            ).mappings().fetchone()
        if note:
            note = dict(note)
            content = note['content'] if note['content'] else "# Empty Note"
            content_bytes = content.encode('utf-8')
            return Response(content_bytes, mimetype='text/markdown', headers={
                "Content-Disposition": f'attachment; filename="{note["title"]}.md"',
                "Content-Length": str(len(content_bytes))
            })
        flash('Note not found or unauthorized.', 'error')
    except Exception as e:
        flash(f'Export error: {e}', 'error')
    return redirect(url_for('index'))


@app.route('/import_note', methods=['POST'])
def import_note():
    if 'user_id' not in session:
        flash('Only logged in users can import notes.', 'error')
        return redirect(url_for('index'))
    file = request.files.get('file')
    if file and file.filename.endswith('.md'):
        title   = os.path.splitext(file.filename)[0]
        content = file.read().decode('utf-8')
        try:
            with engine.begin() as conn:
                result = conn.execute(
                    text("INSERT INTO neo_notes (title, content, user_id) VALUES (:t, :c, :uid)"),
                    {"t": title, "c": content, "uid": session['user_id']}
                )
                new_id = result.lastrowid
            flash('Note imported successfully!', 'success')
            return redirect(url_for('edit', id=new_id))
        except Exception as e:
            flash(f'Import error: {e}', 'error')
    else:
        flash('Invalid file format. Please upload a .md file.', 'error')
    return redirect(url_for('index'))


# ─────────────────────────────────────────────────────────────
#  ROUTES — OPEN NOTE (Wikilink resolver)
# ─────────────────────────────────────────────────────────────
@app.route('/open_note/<path:title>')
def open_note(title):
    import urllib.parse
    title = urllib.parse.unquote(title)
    try:
        with engine.connect() as conn:
            if 'user_id' in session:
                note = conn.execute(
                    text("SELECT id FROM neo_notes WHERE title = :t AND user_id = :uid LIMIT 1"),
                    {"t": title, "uid": session['user_id']}
                ).fetchone()
            else:
                note = conn.execute(
                    text("SELECT id FROM neo_notes WHERE title = :t AND session_id = :sid LIMIT 1"),
                    {"t": title, "sid": session['guest_id']}
                ).fetchone()
        if note:
            return redirect(url_for('edit', id=note[0]))
        flash(f"Note '{title}' not found.", 'error')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('index'))


# ─────────────────────────────────────────────────────────────
#  ROUTES — API
# ─────────────────────────────────────────────────────────────
@app.route('/api/graph_data')
def api_graph_data():
    nodes, edges = [], []
    try:
        with engine.connect() as conn:
            if 'user_id' in session:
                notes = conn.execute(
                    text("SELECT id, title, content FROM neo_notes WHERE user_id = :uid"),
                    {"uid": session['user_id']}
                ).mappings().fetchall()
            else:
                notes = conn.execute(
                    text("SELECT id, title, content FROM neo_notes WHERE session_id = :sid"),
                    {"sid": session['guest_id']}
                ).mappings().fetchall()

            title_to_id = {n['title'].strip().lower(): n['id'] for n in notes}
            for note in notes:
                nodes.append({
                    "id":   note['id'],
                    "name": note['title'],
                    "val":  len(note['content'] or '') / 100 + 1
                })
                links = re.findall(r'\[\[(.*?)\]\]', note['content'] or '')
                for link in links:
                    normalized = link.strip().lower()
                    if normalized in title_to_id:
                        edges.append({"source": note['id'], "target": title_to_id[normalized]})
    except Exception as e:
        print(f"[api_graph_data] error: {e}")
    return jsonify({"nodes": nodes, "links": edges})


@app.route('/api/search')
def api_search():
    """Full-text search endpoint (requires FULLTEXT index from db_migrate.py)."""
    if 'user_id' not in session:
        return jsonify([])
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT id, title FROM neo_notes "
                     "WHERE MATCH(title, content) AGAINST(:q IN BOOLEAN MODE) "
                     "AND user_id = :uid AND deleted_at IS NULL"),
                {"q": q + "*", "uid": session['user_id']}
            ).mappings().fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────
#  ROUTES — THE WIRED
# ─────────────────────────────────────────────────────────────
@app.route('/the_wired')
def the_wired():
    return render_template('wired.html')


if __name__ == '__main__':
    app.run(debug=True, port=5000)
