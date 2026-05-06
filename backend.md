# NeoNotes — Backend Architecture Deep-Dive

> A complete explanation of every backend file, every route, every database decision, and how they all wire together.

---

## 1. Project File Map (Backend Only)

```
notes_app/
├── .env                 # Environment variables (DB creds, secret key)
├── .gitignore           # Keeps secrets & junk out of Git
├── app.py               # The Flask application — ALL routes live here
├── db.py                # Database engine, connection pool, schema init
├── db_migrate.py        # Incremental schema migrations
├── fix_db.py            # Legacy one-off script (old PyMySQL era)
├── requirements.txt     # Python dependencies
├── templates/           # Jinja2 HTML templates (server-rendered)
└── static/              # CSS, audio assets
```

---

## 2. Technology Stack

| Layer | Technology | Why |
|---|---|---|
| **Web Framework** | Flask 3.1.3 | Lightweight, gives full control over routing and request handling |
| **ORM / DB Driver** | SQLAlchemy 2.0.36 + PyMySQL 1.1.3 | SQLAlchemy provides connection pooling and parameterized queries; PyMySQL is the pure-Python MySQL driver underneath |
| **Database** | MySQL (database name: `SEE`) | Relational DB with support for views, stored procedures, full-text search |
| **Templating** | Jinja2 3.1.6 | Server-side HTML rendering, comes bundled with Flask |
| **Password Security** | Werkzeug 3.1.8 | `generate_password_hash` / `check_password_hash` for bcrypt-style hashing |
| **Config Management** | python-dotenv 1.0.1 | Loads `.env` file into `os.getenv()` so secrets stay out of code |

---

## 3. Configuration & Environment (`.env`)

```
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=root123
DB_NAME=SEE
SECRET_KEY=synapse_neo_mythic_key_change_in_prod
```

**What each variable does:**

- `DB_HOST / DB_USER / DB_PASSWORD / DB_NAME` → Used in `db.py` to build the MySQL connection string.
- `SECRET_KEY` → Used by Flask to cryptographically sign session cookies. If someone knows this key, they can forge sessions.

**Security note:** `.env` is listed in `.gitignore` so it never gets committed to Git.

---

## 4. Database Layer — `db.py`

This is the **foundation** of the entire backend. Every route in `app.py` imports `engine` from here.

### 4.1 Connection Pool

```python
engine = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}",
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)
```

**What you built and why:**

| Parameter | Value | Purpose |
|---|---|---|
| `poolclass=QueuePool` | Thread-safe pool | Reuses DB connections instead of opening a new one per request |
| `pool_size=10` | 10 idle connections | Always keeps 10 connections ready in the pool |
| `max_overflow=20` | 20 extra allowed | Under heavy load, can temporarily grow to 30 total (10 + 20) |
| `pool_pre_ping=True` | Health check | Before handing a connection to your code, SQLAlchemy pings MySQL to make sure the connection isn't dead |
| `pool_recycle=3600` | 1-hour recycle | Drops and recreates connections older than 1 hour to avoid MySQL's `wait_timeout` killing idle connections |

**Without this pool**, every single HTTP request would open a new TCP connection to MySQL, do its query, then close it — extremely slow and wasteful.

### 4.2 Schema Initialization — `init_db()`

This function creates all 4 tables, indexes, a view, and a stored procedure — but **only if they don't already exist** (`CREATE TABLE IF NOT EXISTS`).

#### Tables You Created:

**`neo_users`** — User accounts
```
id            INT AUTO_INCREMENT PRIMARY KEY
username      VARCHAR(150) UNIQUE NOT NULL
password_hash VARCHAR(255) NOT NULL
created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```
- `UNIQUE` on username prevents duplicates at the DB level (not just app level).
- `password_hash` stores the Werkzeug-hashed password, never plaintext.

**`neo_folders`** — Note organization
```
id         INT AUTO_INCREMENT PRIMARY KEY
name       VARCHAR(255) NOT NULL
user_id    INT NULL               → FK → neo_users(id) ON DELETE CASCADE
session_id VARCHAR(255) NULL
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```
- Supports both logged-in users (`user_id`) and guests (`session_id`).
- `ON DELETE CASCADE` means: if a user is deleted, all their folders are automatically deleted too.

**`neo_notes`** — The main content table
```
id         INT AUTO_INCREMENT PRIMARY KEY
title      VARCHAR(255) NOT NULL
content    TEXT NOT NULL
folder_id  INT NULL               → FK → neo_folders(id) ON DELETE SET NULL
user_id    INT NULL               → FK → neo_users(id)   ON DELETE CASCADE
session_id VARCHAR(255) NULL
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
deleted_at TIMESTAMP NULL DEFAULT NULL
```
- `ON DELETE SET NULL` for `folder_id` means: if a folder is deleted, notes in it survive — their `folder_id` just becomes `NULL`.
- `ON DELETE CASCADE` for `user_id` means: delete the user → delete all their notes.
- `deleted_at` is a **soft-delete** column — instead of permanently deleting, you set a timestamp. The admin view and search exclude soft-deleted notes.
- `ON UPDATE CURRENT_TIMESTAMP` on `updated_at` means MySQL auto-updates this timestamp every time the row changes.

**`neo_archived_notes`** — Archive vault
```
id          INT PRIMARY KEY       (NOT auto-increment — preserves original note ID)
title       VARCHAR(255) NOT NULL
content     TEXT NOT NULL
folder_id   INT NULL
user_id     INT NULL
session_id  VARCHAR(255) NULL
created_at  TIMESTAMP
archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
```
- No foreign keys here — archived notes are "frozen snapshots" that don't cascade.
- `archived_at` records when the note was moved to the archive.

#### Indexes You Created:

```
idx_notes_user_created      → neo_notes(user_id, created_at DESC)
idx_notes_session_created   → neo_notes(session_id, created_at DESC)
idx_folders_user            → neo_folders(user_id)
idx_archived_user           → neo_archived_notes(user_id, archived_at DESC)
```

**Why these matter:** Without indexes, every query like `SELECT * FROM neo_notes WHERE user_id = 5 ORDER BY created_at DESC` would do a **full table scan** — reading every row in the table. The composite index lets MySQL jump directly to user 5's notes, already sorted by date.

#### View — `Active_Hackers_View`

```sql
CREATE OR REPLACE VIEW Active_Hackers_View AS
SELECT u.id, u.username, COUNT(n.id) as note_count
FROM neo_users u
LEFT JOIN neo_notes n ON u.id = n.user_id AND n.deleted_at IS NULL
GROUP BY u.id
```

This is a **virtual table** used by the admin panel. Instead of writing the JOIN + COUNT query every time, you just `SELECT * FROM Active_Hackers_View`. It excludes soft-deleted notes from the count.

#### Stored Procedure — `PurgeUser`

```sql
CREATE PROCEDURE PurgeUser(IN uid INT)
BEGIN
    DELETE FROM neo_users WHERE id = uid;
END
```

Called from the admin panel as `CALL PurgeUser(:id)`. Because `neo_notes` has `ON DELETE CASCADE` referencing `neo_users`, deleting a user automatically deletes all their notes and folders in one atomic operation.

---

## 5. Migration System — `db_migrate.py`

This is how you **upgrade** an existing database without losing data. Instead of dropping and recreating tables, each migration checks if the change has already been applied.

### How the Migration Pattern Works:

```python
migrations = []

def migration(fn):
    migrations.append(fn)
    return fn
```

The `@migration` decorator registers each function into a list. When you run `python db_migrate.py`, it executes them in order inside a single transaction.

### The 5 Migrations You Wrote:

| # | What it does | Guard check |
|---|---|---|
| **001** | Adds `updated_at` column to `neo_notes` | `column_exists(conn, "neo_notes", "updated_at")` |
| **002** | Adds `deleted_at` column (soft-delete) | `column_exists(conn, "neo_notes", "deleted_at")` |
| **003** | Creates 4 composite indexes | `index_exists()` for each index |
| **004** | Adds `FULLTEXT` index on `(title, content)` | `fts_index_exists()` |
| **005** | Rebuilds the admin view to exclude soft-deleted notes | `CREATE OR REPLACE` (always safe) |

**Key design:** Every migration uses `information_schema` queries to check if the column/index already exists before trying to create it. This makes migrations **idempotent** — you can run them 100 times and nothing breaks.

### Helper Functions:

- `column_exists(conn, table, column)` → Queries `information_schema.COLUMNS`
- `index_exists(conn, table, index)` → Queries `information_schema.STATISTICS`
- `fts_index_exists(conn, table, index)` → Same but filters for `INDEX_TYPE = 'FULLTEXT'`

---

## 6. The Flask Application — `app.py`

This is the **brain** of the backend — 626 lines handling all HTTP requests.

### 6.1 App Initialization

```python
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev_secret_change_in_prod')
```

- `Flask(__name__)` creates the app and tells Flask where to find templates/static files.
- `secret_key` is critical — Flask uses it to sign session cookies with HMAC. Without it, sessions won't work.

### 6.2 Before-Request Middleware

```python
@app.before_request
def ensure_session_id():
    session.permanent = True
    if 'user_id' not in session and 'guest_id' not in session:
        session['guest_id'] = str(uuid.uuid4())
```

**What this does:** Runs **before every single request**. If the visitor isn't logged in AND doesn't have a guest ID yet, it generates a UUID and stores it in their session cookie. This is how guest users can create notes without signing up.

`session.permanent = True` makes the session cookie last 31 days (Flask's default permanent lifetime) instead of expiring when the browser closes.

### 6.3 Context Processor — Sidebar Data

```python
@app.context_processor
def inject_notes():
```

**What this does:** Runs **before every template render** and injects `all_notes`, `all_folders`, and `all_tags` into every template automatically. This is why the sidebar shows your notes on every page without each route having to query and pass them manually.

**How tags work:** It scans every note's content with `re.findall(r'(?<!\w)#(\w+)', content)` — this regex finds hashtags like `#python` but not things like `C#sharp` (the negative lookbehind `(?<!\w)` prevents matching mid-word).

### 6.4 Authentication Routes

#### `POST /signup`

```
1. Get username & password from form
2. Check if username already exists → flash error if yes
3. Hash password with generate_password_hash()
4. INSERT into neo_users
5. Redirect to login page
```

**Security:** Passwords are never stored as plaintext. `generate_password_hash()` uses PBKDF2-SHA256 with a random salt by default.

#### `POST /login`

```
1. Get username & password from form
2. SELECT user from neo_users
3. check_password_hash(stored_hash, provided_password)
4. If match → store user_id and username in session
5. TRANSFER GUEST NOTES: UPDATE neo_notes SET user_id = :uid WHERE session_id = :sid
6. Remove guest_id from session
```

**The guest-note transfer** (line 136-141) is important: if someone creates notes as a guest and then signs up/logs in, their notes are permanently linked to their account. The `session_id` is set to NULL and `user_id` is set to their new user ID.

#### `GET /logout`

Simply pops `user_id` and `username` from the session. The guest system kicks in on the next request via `before_request`.

### 6.5 Notes CRUD Routes

#### `POST /create` — Create a Note

```
1. Get title & content from form
2. Validate: both can't be empty
3. If no title → auto-generate "Untitled", "Untitled 1", "Untitled 2", etc.
4. Get folder_id from form (optional)
5. INSERT into neo_notes with either user_id OR session_id
6. Redirect to /edit/<new_id>
```

**The `get_untitled_title()` helper** is clever: it queries all existing "Untitled" notes for the user, extracts the numbers, finds the max, and returns the next one. So if you have "Untitled" and "Untitled 2", the next one is "Untitled 3".

#### `GET/POST /edit/<id>` — Edit a Note

```
GET:
  1. SELECT note WHERE id = :id AND (user_id or session_id matches)
  2. If not found → "unauthorized" flash → redirect
  3. Render note_form.html with the note data

POST:
  1. Same ownership check
  2. UPDATE title, content, folder_id
  3. Redirect back to /edit/<id>
```

**Ownership check pattern:** Every note operation verifies that either `user_id = session['user_id']` OR `session_id = session['guest_id']`. This prevents User A from editing User B's notes by guessing the note ID.

#### `POST /delete/<id>` — Delete a Note

```
1. DELETE FROM neo_notes WHERE id = :id AND (ownership check)
2. Check result.rowcount — if 0, the note didn't exist or wasn't yours
```

#### `POST /api/autosave/<id>` — JSON Autosave Endpoint

```
1. Accept JSON body: { title, content }
2. SELECT ... FOR UPDATE (row-level lock)
3. UPDATE the note
4. Return JSON: { status: "success", title: "..." }
```

**`FOR UPDATE`** is key here — it places a **row-level lock** in MySQL, preventing two simultaneous autosave requests from creating a race condition. The lock is released when the transaction commits.

This is the only **API-style** route for notes — it returns JSON instead of rendering HTML, designed to be called by JavaScript on the frontend.

### 6.6 Admin Routes

All admin routes check `session.get('username') != 'admin'` — only the user literally named "admin" can access these.

#### `GET /admin` — Admin Dashboard

```
1. Query Active_Hackers_View for user stats
2. Query ALL neo_notes (no user filter)
3. Render admin.html with users and notes lists
```

#### `POST /admin/delete_user/<id>` — Purge a User

```
1. CALL PurgeUser(:id)  ← stored procedure
2. CASCADE deletes all their notes and folders
```

#### `POST /admin/delete_note/<id>` — Delete Any Note

Admin can delete any note without ownership checks.

#### `POST /admin/backup` — Database Backup

```
1. Create backups/ directory
2. Run `mysqldump` as a subprocess
3. Save output to backups/backup_<random>.sql
```

This shells out to MySQL's `mysqldump` CLI tool — it's not going through SQLAlchemy, it's a raw OS-level command.

### 6.7 Archive Routes

#### `POST /archive/<id>` — Archive a Note

```
1. SELECT note (with FOR UPDATE lock)
2. INSERT same data into neo_archived_notes
3. DELETE from neo_notes
4. This is a manual "move" — not soft-delete
```

**Difference from soft-delete:** Soft-delete (`deleted_at`) keeps the note in `neo_notes` but marks it. Archiving physically moves the row to a different table (`neo_archived_notes`).

#### `GET /archive_vault` — View Archived Notes

Queries `neo_archived_notes` filtered by user/session, ordered by `archived_at DESC`.

#### `POST /restore/<id>` — Restore from Archive

The reverse of archive:
```
1. SELECT from neo_archived_notes (FOR UPDATE)
2. INSERT back into neo_notes
3. DELETE from neo_archived_notes
```

### 6.8 Folder Routes

#### `POST /create_folder`

Simple INSERT into `neo_folders` with the user's ID or session ID.

### 6.9 Import / Export Routes

#### `GET /export_note/<id>` — Download as Markdown

```
1. Auth check: logged-in users only
2. SELECT the note
3. Return a Response with:
   - mimetype='text/markdown'
   - Content-Disposition: attachment; filename="Note Title.md"
   - Content-Length header
```

This triggers a **file download** in the browser — the `attachment` disposition tells the browser to save it rather than display it.

#### `POST /import_note` — Upload a Markdown File

```
1. Auth check: logged-in users only
2. Read uploaded .md file
3. Use filename (minus .md) as title
4. INSERT into neo_notes
5. Redirect to edit the new note
```

### 6.10 Wikilink Resolver

#### `GET /open_note/<title>` — Open Note by Title

```
1. URL-decode the title
2. SELECT id FROM neo_notes WHERE title = :t AND (ownership)
3. Redirect to /edit/<id>
```

This powers the `[[wikilink]]` syntax — when you click a `[[Some Note]]` link in the rendered preview, it hits this route, finds the note by title, and opens it.

### 6.11 API Routes

#### `GET /api/graph_data` — 3D Graph Visualization Data

```python
nodes = []
edges = []
for note in notes:
    nodes.append({
        "id":   note['id'],
        "name": note['title'],
        "val":  len(note['content']) / 100 + 1   # node size based on content length
    })
    links = re.findall(r'\[\[(.*?)\]\]', note['content'])  # find [[wikilinks]]
    for link in links:
        if normalized_link in title_to_id:
            edges.append({"source": note['id'], "target": title_to_id[normalized]})
```

**What this returns:** A JSON graph structure `{ nodes: [...], links: [...] }` consumed by the Three.js 3D visualization ("The Wired"). Nodes are notes, edges are wikilink connections between them. Node size scales with content length.

#### `GET /api/search` — Full-Text Search

```sql
SELECT id, title FROM neo_notes
WHERE MATCH(title, content) AGAINST(:q IN BOOLEAN MODE)
AND user_id = :uid AND deleted_at IS NULL
```

Uses MySQL's built-in **FULLTEXT** index (created in migration 004). `BOOLEAN MODE` allows prefix matching with the appended `*` wildcard.

---

## 7. Request Lifecycle — Complete Flow

Here's what happens when a user hits `POST /create`:

```
Browser → POST /create
    │
    ├─ 1. Flask receives the HTTP request
    ├─ 2. @before_request runs → ensures session has guest_id or user_id
    ├─ 3. Route function create() executes
    │      ├─ Reads form data from request.form
    │      ├─ Opens a DB connection from the pool (engine.begin())
    │      ├─ Runs INSERT query with parameterized values
    │      ├─ Gets the new note's ID from result.lastrowid
    │      └─ Connection auto-commits and returns to pool
    ├─ 4. flash() stores a message in the session for next request
    ├─ 5. redirect() sends HTTP 302 to /edit/<new_id>
    │
Browser ← 302 Redirect
Browser → GET /edit/<new_id>
    │
    ├─ 1. @before_request runs again
    ├─ 2. @context_processor inject_notes() runs
    │      └─ Queries ALL notes & folders for sidebar
    ├─ 3. edit() route runs → SELECTs the specific note
    ├─ 4. render_template() merges note data + sidebar data into HTML
    │
Browser ← 200 OK + rendered HTML
```

---

## 8. Security Patterns Used

| Pattern | Where | How |
|---|---|---|
| **Password hashing** | `/signup`, `/login` | Werkzeug's PBKDF2-SHA256 with random salt |
| **Session-based auth** | Every route | Flask's signed cookie sessions (HMAC with SECRET_KEY) |
| **Ownership verification** | Every note/folder operation | `WHERE user_id = :uid` or `WHERE session_id = :sid` |
| **Parameterized queries** | Every SQL query | `text("... :param")` with `{"param": value}` — prevents SQL injection |
| **Row-level locking** | Autosave, archive, restore | `SELECT ... FOR UPDATE` prevents race conditions |
| **Environment variables** | DB creds, secret key | `.env` file loaded by python-dotenv, excluded from Git |
| **Admin gate** | All `/admin/*` routes | `session.get('username') != 'admin'` check |
| **Guest isolation** | Notes, folders | UUID-based session_id ensures guests can't see each other's data |

---

## 9. Connection Patterns — `engine.connect()` vs `engine.begin()`

You use two patterns throughout `app.py`:

```python
# READ-ONLY operations
with engine.connect() as conn:
    result = conn.execute(text("SELECT ..."))
    # No commit needed — auto-rollback on exit

# WRITE operations
with engine.begin() as conn:
    conn.execute(text("INSERT / UPDATE / DELETE ..."))
    # Auto-COMMIT on successful exit
    # Auto-ROLLBACK if an exception is raised
```

**Why this matters:** `engine.begin()` wraps everything in a **transaction**. If the INSERT succeeds but something fails before the block exits, the entire operation is rolled back — your data stays consistent.

---

## 10. Legacy File — `fix_db.py`

This is from the **old era** before you migrated to SQLAlchemy. It uses raw PyMySQL (`db.get_db_connection()`) and directly manipulates tables named `notes` and `users` (not the current `neo_notes` / `neo_users`).

**You don't need this anymore** — `db.py` and `db_migrate.py` handle everything. It's kept as a historical artifact.

---

## 11. Dependencies Breakdown — `requirements.txt`

| Package | Version | Role |
|---|---|---|
| **Flask** | 3.1.3 | Web framework |
| **SQLAlchemy** | 2.0.36 | Database toolkit + connection pool |
| **PyMySQL** | 1.1.3 | Pure-Python MySQL driver (used by SQLAlchemy) |
| **python-dotenv** | 1.0.1 | Loads `.env` into environment |
| **Werkzeug** | 3.1.8 | WSGI utilities + password hashing (Flask dependency) |
| **Jinja2** | 3.1.6 | Template engine (Flask dependency) |
| **cryptography** | 47.0.0 | SSL/TLS support for secure MySQL connections |
| **alembic** | 1.14.0 | Advanced migration framework (installed but you wrote your own simpler system) |
| **itsdangerous** | 2.2.0 | Session cookie signing (Flask dependency) |
| **click** | 8.3.3 | CLI toolkit (Flask dependency) |
| **MarkupSafe** | 3.0.3 | HTML escaping (Jinja2 dependency) |
| **blinker** | 1.9.0 | Signal/event support (Flask dependency) |
| **colorama** | 0.4.6 | Colored terminal output on Windows |
| **cffi** | 2.0.0 | C FFI for Python (cryptography dependency) |
| **pycparser** | 3.0 | C parser (cffi dependency) |

---

## 12. Complete Route Map

| Method | Route | Auth | Purpose |
|---|---|---|---|
| GET | `/` | None | Landing page |
| GET/POST | `/signup` | None | User registration |
| GET/POST | `/login` | None | User login + guest note transfer |
| GET | `/logout` | None | Clear session |
| GET/POST | `/create` | Guest/User | Create a new note |
| GET/POST | `/edit/<id>` | Owner only | View/edit a note |
| POST | `/delete/<id>` | Owner only | Permanently delete a note |
| POST | `/api/autosave/<id>` | Owner only | JSON autosave (called by JS) |
| GET | `/admin` | Admin only | Admin dashboard |
| POST | `/admin/delete_user/<id>` | Admin only | Purge user via stored procedure |
| POST | `/admin/delete_note/<id>` | Admin only | Delete any note |
| POST | `/admin/backup` | Admin only | mysqldump backup |
| POST | `/archive/<id>` | Owner only | Move note to archive table |
| GET | `/archive_vault` | Guest/User | View archived notes |
| POST | `/restore/<id>` | Owner only | Restore note from archive |
| POST | `/create_folder` | Guest/User | Create a folder |
| GET | `/export_note/<id>` | User only | Download note as .md file |
| POST | `/import_note` | User only | Upload .md file as note |
| GET | `/open_note/<title>` | Owner only | Wikilink resolver |
| GET | `/api/graph_data` | Guest/User | JSON graph for 3D visualization |
| GET | `/api/search` | User only | Full-text search API |
| GET | `/the_wired` | None | 3D network visualization page |

---

## 13. Database Relationship Diagram

```
┌──────────────┐       ┌───────────────┐       ┌────────────────────┐
│  neo_users   │       │  neo_folders   │       │  neo_archived_notes│
│──────────────│       │───────────────│       │────────────────────│
│ id        PK │◄──┐   │ id         PK │       │ id              PK │
│ username     │   │   │ name          │       │ title              │
│ password_hash│   ├───│ user_id    FK │       │ content            │
│ created_at   │   │   │ session_id    │       │ folder_id          │
└──────────────┘   │   │ created_at    │       │ user_id            │
                   │   └───────┬───────┘       │ session_id         │
                   │           │ ON DELETE      │ created_at         │
                   │           │ SET NULL       │ archived_at        │
                   │           ▼               └────────────────────┘
                   │   ┌───────────────┐
                   │   │   neo_notes    │
                   │   │───────────────│
                   │   │ id         PK │
                   │   │ title         │
                   │   │ content       │
                   ├───│ user_id    FK │ ON DELETE CASCADE
                   │   │ folder_id  FK │ ON DELETE SET NULL
                       │ session_id    │
                       │ created_at    │
                       │ updated_at    │
                       │ deleted_at    │
                       └───────────────┘
```

**Cascade rules:**
- Delete a **user** → all their **notes** and **folders** are auto-deleted
- Delete a **folder** → notes in it survive, their `folder_id` becomes `NULL`
- **Archived notes** have no foreign keys — they're independent frozen snapshots
