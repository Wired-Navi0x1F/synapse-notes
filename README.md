# Synapse-Notes Web Application

A brutalist, Neo-Mythic 90s Web/Cyberpunk Notes application with a MySQL backend.

## Features Currently Implemented
1. **Secure Authentication**: User sign-up and login securely hashed.
2. **Guest Mode**: Try the application without an account. Notes save to your browser session. If you sign up, your guest notes transfer automatically!
3. **Admin 'Observer' Dashboard**: Accessible only if your username is `admin`. Shows raw database tables and system logs.
4. **Auto-naming**: Notes saved without titles automatically get assigned "Untitled", "Untitled 1", etc.
5. **Auto-save**: Notes automatically and silently save in the background 3 seconds after you stop typing.
6. **Command Palette**: Press `Ctrl + K` to open a quick-command input modal (commands: `> new`, `> logout`, `> admin`).
7. **Markdown & Live Preview**: Write in Markdown and see the styled preview, with syntax highlighting for code blocks.
8. **Tagging System**: `#tags` included in your notes are automatically extracted and show up in the left sidebar as directories.
9. **System Logs**: The admin dashboard tracks all user actions dynamically.

## Developer Setup
1. Python venv: `python -m venv venv`
2. Install: `pip install flask pymysql werkzeug`
3. Setup DB: `python db.py`
4. Run: `python app.py`
