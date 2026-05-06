# SYNAPSE-NOTES (CyberCore NeoNotes)

A brutalist, Neo-Mythic 90s Web/Cyberpunk Notes application built with Python (Flask) and a robust SQLAlchemy-based MySQL backend. It features a unique, immersive aesthetic inspired by *Serial Experiments Lain* and 90s hacker culture, complete with an interactive 3D network graph visualization known as "The Wired."

## 🚀 Key Features

### Core Note-Taking & Markdown Engine
* **Advanced Markdown & Live Preview:** Write notes in Markdown and view a beautifully styled live preview. The custom rendering engine supports:
  * **Syntax Highlighting** for code blocks.
  * **KaTeX** for rendering complex mathematical equations inline.
  * **Footnotes** for academic or detailed referencing.
  * Native line breaks and styling support.
* **Auto-save:** Notes automatically and silently save in the background 3 seconds after you stop typing, preventing data loss.
* **Auto-naming:** Notes saved without titles automatically get assigned sequential names ("Untitled", "Untitled 1", etc.).
* **Import/Export:** Seamlessly import `.md` files into your workspace and export individual notes as Markdown files.

### Organization & Connectivity
* **Folder Management:** Organize notes into custom folders with a VS Code-style collapsible UI and searchable dropdowns in the sidebar.
* **Dynamic Tagging:** Any `#tags` included in your note content are automatically extracted and displayed as quick-filters in the left sidebar.
* **Archive Vault:** Securely archive notes to declutter your workspace, with the ability to restore them at any time utilizing fully transactional database operations.
* **"The Wired" 3D Graph:** An interactive, 3D visual network topology mapping your notes. Nodes vary in size based on content length, and edges (connections) are dynamically formed using `[[Note Title]]` syntax within the note content.

### User System
* **Secure Authentication:** User sign-up and login utilizing securely hashed passwords (via Werkzeug security).
* **Guest Mode:** Try the application immediately without an account. Notes save to your browser session via UUIDs. If you decide to sign up, your guest notes and folders transfer automatically to your new account!
* **Command Palette:** Power-user navigation. Press `Ctrl + K` to open a quick-command input modal (Commands: `> new`, `> logout`, `> admin`).

### Admin "Observer" Dashboard (`SYNAPSE_OBSERVER`)
Accessible exclusively by creating an account with the username `admin`.
* **System Overview:** View active hackers (users) and all system notes.
* **Scalable Data Management:** Built to handle thousands of users effortlessly with server-side pagination, user search, and dynamic data loading.
* **User-Specific Filtering:** Click to view notes created by specific users in real-time.
* **Moderation:** Purge users via stored procedures or delete specific notes directly from the dashboard.
* **Backups:** Generate full database backups manually directly from the UI.

## 🛠 Tech Stack

* **Backend:** Python, Flask
* **Database & ORM:** MySQL, SQLAlchemy, Alembic (Migrations)
* **Frontend:** HTML, Vanilla CSS (Custom Neo-Mythic Brutalist Design System), Vanilla JavaScript
* **Libraries:** Marked.js (with KaTeX & Footnotes plugins), Highlight.js, DOMPurify, 3D-Force-Graph

## 🗄 Database Architecture

The application relies on a comprehensive MySQL database accessed via SQLAlchemy.

### Core Tables
* `neo_users`: Stores user credentials and metadata.
* `neo_folders`: Manages the organizational folders.
* `neo_notes`: Stores the core note data, linked by Foreign Keys to users and folders.
* `neo_logs`: A system audit log tracking CRUD actions and user events.
* `neo_archived_notes`: A secure vault for archived note data.

### Advanced Database Mechanics
* **ACID Transactions:** Used during the Archiving and Restoring processes (via `engine.begin()`) to ensure data integrity across multiple tables.
* **Row-Level Locking:** Utilizes `SELECT ... FOR UPDATE` in autosave and archive queries to prevent concurrent race conditions.
* **Views & Stored Procedures:** Utilizes raw SQL views (`Active_Hackers_View`) and procedures (`PurgeUser`) to efficiently manage data at the SQL level.

## 💻 Developer Setup

### Prerequisites
* Python 3.9+
* MySQL Server (Ensure your database credentials are set in a `.env` file)
* `mysqldump` installed and in your system PATH (Required for the Admin Backup feature).

### Installation Instructions

1. **Clone / Navigate to the directory:**
   ```bash
   cd notes_app
   ```

2. **Set up a Python Virtual Environment:**
   ```bash
   python -m venv venv
   ```

3. **Activate the Virtual Environment:**
   * **Windows:** `venv\Scripts\activate`
   * **macOS/Linux:** `source venv/bin/activate`

4. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Environment Configuration:**
   Create a `.env` file in the root directory:
   ```env
   SECRET_KEY=your_secure_secret_key
   DB_USER=root
   DB_PASSWORD=your_password
   DB_NAME=SEE
   ```

6. **Initialize the Database:**
   Run the migration/db setup script to create the database schema:
   ```bash
   python db_migrate.py
   ```

7. **Run the Application:**
   ```bash
   flask run
   ```
   The application will start. Open your browser and navigate to `http://127.0.0.1:5000`.
