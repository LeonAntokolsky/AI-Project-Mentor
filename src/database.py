import aiosqlite
from typing import Optional
from agent import ProjectAuditResult

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init_db(self):
        """Initializes SQLite tables for project state and task backlog."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS project_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    summary TEXT,
                    ignored_count INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    file_path TEXT,
                    title TEXT,
                    explanation TEXT,
                    ready_code_fix TEXT,
                    estimated_minutes INTEGER,
                    status TEXT DEFAULT 'pending' -- pending, completed, skipped
                )
            """)
            await db.commit()

    async def save_audit_result(self, audit: ProjectAuditResult):
        """Saves project summary and populates pending tasks."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO project_state (id, summary, ignored_count)
                VALUES (1, ?, 0)
                ON CONFLICT(id) DO UPDATE SET summary = excluded.summary, ignored_count = 0
            """, (audit.project_summary,))

            # Clear old pending tasks before inserting fresh audit results
            await db.execute("DELETE FROM tasks WHERE status = 'pending'")

            for t in audit.tasks:
                await db.execute("""
                    INSERT INTO tasks (category, file_path, title, explanation, ready_code_fix, estimated_minutes)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (t.category, t.file_path, t.title, t.explanation, t.ready_code_fix, t.estimated_minutes))
            await db.commit()

    async def get_next_task(self) -> Optional[dict]:
        """Fetches the next pending micro-task from the backlog."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE status = 'pending' ORDER BY id ASC LIMIT 1"
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_task_status(self, task_id: int, status: str):
        """Updates task status and resets ignored_count when user interacts."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
            await db.execute("UPDATE project_state SET ignored_count = 0 WHERE id = 1")
            await db.commit()

    async def reset_ignored_count(self):
        """Resets ignored counter when user manually interacts with the bot."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE project_state SET ignored_count = 0 WHERE id = 1")
            await db.commit()

    async def increment_ignored_count(self) -> tuple[int, str]:
        """Increments ignored counter and returns (ignored_count, project_summary)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE project_state SET ignored_count = ignored_count + 1 WHERE id = 1")
            await db.commit()
            cursor = await db.execute("SELECT ignored_count, summary FROM project_state WHERE id = 1")
            row = await cursor.fetchone()
            return (row[0], row[1]) if row else (0, "")

    async def get_stats(self) -> dict:
        """Returns current project statistics and task counts."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT summary, ignored_count FROM project_state WHERE id = 1")
            state_row = await cursor.fetchone()

            cursor = await db.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
            counts = dict(await cursor.fetchall())

            return {
                "summary": state_row[0] if state_row else "Not scanned yet",
                "ignored_count": state_row[1] if state_row else 0,
                "pending": counts.get("pending", 0),
                "completed": counts.get("completed", 0),
                "skipped": counts.get("skipped", 0),
            }
