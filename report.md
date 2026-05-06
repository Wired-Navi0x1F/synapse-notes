# CS1211 DATABASE MANAGEMENT SYSTEM
## Mini Project Report
**NeoNotes: A Neo-Mythic CyberCore Notes Application**

**Submitted By:**
- Student Name 1 (USN)
- Student Name 2 (USN)
- Student Name 3 (USN)

**Under the guidance of:**
- Dr./Prof. [Faculty Name]

**School of Computer Science and Engineering**  
**RV University, Bangalore**

---

# CERTIFICATE
Certified that the CS1211 Database Management Systems Mini Project work titled **NeoNotes: A Neo-Mythic CyberCore Notes Application** is carried out by **[Names]** **[USN]** who are bonafide students of the School of Computer Science and Engineering, RV University, Bengaluru, during the year 2025–26.

It is certified that all corrections/suggestions from all the continuous internal evaluations have been incorporated into the project and in this report.

**Faculty Guide:** _________________  
**Program Director:** _________________

---

# Abstract
- **Problem Statement:** Traditional note-taking applications often lack immersive visual organization and fail to provide a seamless transition from transient guest sessions to authenticated user accounts.
- **Objectives:** To build a secure, ACID-compliant database application that supports complex Markdown rendering, dynamic tagging, seamless guest-to-user session transfer, and an interactive 3D network topology visualization.
- **Methodology:** Developed a monolithic full-stack web application using Flask, anchored by a fully normalized MySQL database utilizing SQLAlchemy ORM and raw SQL executions.
- **Tools used:** Python, Flask, MySQL, SQLAlchemy, Vanilla JS, Marked.js.
- **Key outcomes:** Successfully implemented an advanced DBMS project featuring Views, Triggers, Stored Procedures, and explicitly locked ACID Transactions ensuring absolute data integrity.

---

# Table of Contents
1. Introduction
2. Objectives
3. Literature Survey
4. Database Design
5. Implementation
6. Results and Discussion
7. Conclusion
8. Future Enhancements
9. References

---

# Chapter 1: Introduction

## 1.1 Background
In the era of modern personal knowledge management (PKM), users require robust tools to organize their thoughts. NeoNotes addresses this by providing a highly aesthetic, cyberpunk-themed interface powered by a rigorous relational database backend.

## 1.2 Problem Statement
Existing notes applications often lock users behind immediate authentication walls and lack visual network relationship mapping. Furthermore, they abstract away database operations, leading to potential data integrity flaws during operations like archival. NeoNotes solves this by implementing a seamless guest-to-user workflow and ACID-compliant transactional archiving.

## 1.3 Scope
The scope encompasses a web-based note-taking client supporting Markdown, KaTeX, and Footnotes, backed by a MySQL database handling user authentication, folder management, tagging, and administrative oversight.

## 1.4 Motivation
A relational database solution is strictly required because of the inherent relational nature of the data: Notes belong to Folders, Folders and Notes belong to Users, and Notes contain references to other Notes.

# Chapter 2: Objectives
- **Objective 1:** Implement a secure, normalized (3NF) relational database to store users, folders, and notes.
- **Objective 2:** Create an interactive 3D force graph visualizing relationships between notes based on internal Markdown links.
- **Objective 3:** Utilize advanced DBMS features including Views, Triggers, Stored Procedures, and Row-Level locking.
- **Objective 4:** Develop an administrative dashboard capable of paginating through thousands of records efficiently using SQL `LIMIT` and `OFFSET`.

# Chapter 3: Literature Survey

| Existing System | Features | Limitations |
| --- | --- | --- |
| **Evernote** | Cloud sync, rich text | Heavy UI, proprietary data lock-in, lacks 3D relationship graphing. |
| **Obsidian** | Local Markdown, 2D Graph | Not web-native, requires local installation, no built-in guest cloud sessions. |
| **Notion** | Block-based editor, databases | High latency, overly complex for simple notes, steep learning curve. |

# Chapter 4: Database Design

## 4.1 ER Diagram
*(Insert ER Diagram Image Here: Show Users (1) to Notes (N), Users (1) to Folders (N), Folders (1) to Notes (N))*

## 4.2 Entity Description
- **neo_users:** Stores primary user authentication data.
- **neo_folders:** Represents organizational directories for notes.
- **neo_notes:** The core entity holding markdown text and metadata.
- **neo_archived_notes:** A secure vault identical in structure to neo_notes.
- **neo_logs:** An audit trail entity.

## 4.3 Schema Design & Keys
- **Primary Keys:** `id` (INT AUTO_INCREMENT) in all tables.
- **Foreign Keys:** `user_id` referencing `neo_users(id)`, `folder_id` referencing `neo_folders(id)`.
- **Unique Constraints:** `username` in `neo_users`.

## 4.4 Normalization
The database is normalized up to 3NF. There are no repeating groups (1NF). All non-key attributes depend wholly on the primary key (2NF). No transitive dependencies exist (3NF)—for example, user credentials are not stored in the notes table, only the `user_id`.

# Chapter 5: Implementation

## 5.1 Software and Tools Used
- **DBMS:** MySQL 8.0
- **Programming Language:** Python 3
- **Frontend:** HTML, Vanilla CSS, Vanilla JS
- **Libraries:** Flask, SQLAlchemy ORM, Marked.js

## 5.2 SQL Commands & Advanced Features

**Views:** Used in the Admin Dashboard to calculate aggregate note counts dynamically.
```sql
CREATE OR REPLACE VIEW Active_Hackers_View AS
SELECT u.id, u.username, COUNT(n.id) as note_count
FROM neo_users u
LEFT JOIN neo_notes n ON u.id = n.user_id AND n.deleted_at IS NULL
GROUP BY u.id;
```

**Triggers:** Audit logging for when a note is created.
```sql
CREATE TRIGGER after_note_insert
AFTER INSERT ON neo_notes
FOR EACH ROW
BEGIN
    INSERT INTO neo_logs (action, user_id)
    VALUES (CONCAT('Created Note: ', NEW.title), NEW.user_id);
END;
```

**Stored Procedures:** Safely purging a user.
```sql
CREATE PROCEDURE PurgeUser(IN uid INT)
BEGIN
    DELETE FROM neo_users WHERE id = uid;
END;
```

**Transactions & Concurrency (ACID):** Archiving uses strict locking.
```sql
START TRANSACTION;
SELECT * FROM neo_notes WHERE id = ? FOR UPDATE;
INSERT INTO neo_archived_notes (...) VALUES (...);
DELETE FROM neo_notes WHERE id = ?;
COMMIT;
-- If any error occurs: ROLLBACK;
```

# Chapter 6: Results and Discussion

## 6.1 Sample Outputs
*(Insert Screenshots Here: The NeoNotes Editor, The Wired 3D Graph, The Admin Dashboard)*

## 6.2 Analysis
The system successfully handles scale through server-side pagination. The explicit locking mechanism (`SELECT ... FOR UPDATE`) prevents dirty reads and write skews during rapid autosaving and archiving operations. The guest session transfer workflow functions flawlessly using UUID matching.

# Chapter 7: Conclusion
The NeoNotes project successfully demonstrates the power of a normalized MySQL database integrated with a modern web framework. It meets all DBMS Mini Project requirements, excelling particularly in the implementation of advanced database features such as ACID transactions, triggers, views, and stored procedures.

# Chapter 8: Future Enhancements
- Implement collaborative editing using WebSockets.
- Add full-text search capability using MySQL `MATCH() AGAINST()`.
- Allow image attachments stored as BLOBs or via cloud storage URLs.

# References
1. Elmasri, R., & Navathe, S. B. (2015). *Fundamentals of Database Systems*. Pearson.
2. Flask Documentation. https://flask.palletsprojects.com/
3. MySQL 8.0 Reference Manual. https://dev.mysql.com/doc/refman/8.0/en/
