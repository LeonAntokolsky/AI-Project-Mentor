import aiosqlite
from typing import Optional
from agent import ProjectAuditResult

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init_db(self, default_interval: int = 24):
        """Initializes SQLite tables and runs safe schema migrations."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"""
                CREATE TABLE IF NOT EXISTS project_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    chat_id INTEGER,
                    summary TEXT,
                    ignored_count INTEGER DEFAULT 0,
                    ping_interval_hours INTEGER DEFAULT {default_interval}
                )
            """)
            for col_def in ["chat_id INTEGER", f"ping_interval_hours INTEGER DEFAULT {default_interval}", "is_verified INTEGER DEFAULT 0"]:
                try:
                    await db.execute(f"ALTER TABLE project_state ADD COLUMN {col_def}")
                except Exception:
                    pass

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

    async def set_chat_id(self, chat_id: int):
        """Registers or updates the active Telegram chat_id."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO project_state (id, chat_id, ignored_count)
                VALUES (1, ?, 0)
                ON CONFLICT(id) DO UPDATE SET chat_id = excluded.chat_id
            """, (chat_id,))
            await db.commit()

    async def get_chat_id(self) -> Optional[int]:
        """Retrieves the registered Telegram chat_id."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT chat_id FROM project_state WHERE id = 1")
            row = await cursor.fetchone()
            return row[0] if row and row[0] else None

    async def set_ping_interval(self, hours: int):
        """Updates the reminder interval in hours."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO project_state (id, ping_interval_hours)
                VALUES (1, ?)
                ON CONFLICT(id) DO UPDATE SET ping_interval_hours = excluded.ping_interval_hours
            """, (hours,))
            await db.commit()

    async def get_ping_interval(self, default_hours: int = 24) -> int:
        """Retrieves the current reminder interval in hours."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT ping_interval_hours FROM project_state WHERE id = 1")
            row = await cursor.fetchone()
            return row[0] if row and row[0] else default_hours

    async def save_audit_result(self, audit: ProjectAuditResult):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO project_state (id, summary, ignored_count) VALUES (1, ?, 0) ON CONFLICT(id) DO UPDATE SET summary = excluded.summary, ignored_count = 0",
                (audit.project_summary,))
            await db.execute("DELETE FROM tasks WHERE status = 'pending'")
            task_rows = [
                (t.category, t.file_path, t.title, t.explanation, t.ready_code_fix, t.estimated_minutes)
                for t in audit.tasks
            ]
            await db.executemany(
                "INSERT INTO tasks (category, file_path, title, explanation, ready_code_fix, estimated_minutes) VALUES (?, ?, ?, ?, ?, ?)",
                task_rows)
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

    async def get_task_by_id(self, task_id: int) -> Optional[dict]:
        """Fetches a specific task by its ID for verification."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
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
            cursor = await db.execute(
                "SELECT summary, ignored_count, chat_id, ping_interval_hours FROM project_state WHERE id = 1"
            )
            state_row = await cursor.fetchone()

            cursor = await db.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
            counts = dict(await cursor.fetchall())

            return {
                "summary": state_row[0] if state_row and state_row[0] else "Not scanned yet",
                "ignored_count": state_row[1] if state_row and state_row[1] else 0,
                "chat_id": state_row[2] if state_row else None,
                "ping_interval_hours": state_row[3] if state_row and state_row[3] else 24,
                "pending": counts.get("pending", 0),
                "completed": counts.get("completed", 0),
                "skipped": counts.get("skipped", 0),
            }

    async def is_user_verified(self) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT is_verified FROM project_state WHERE id = 1")
            row = await cursor.fetchone()
            return bool(row and row[0])

    async def set_user_verified(self, chat_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO project_state (id, chat_id, is_verified) VALUES (1, ?, 1)
                ON CONFLICT(id) DO UPDATE SET chat_id = excluded.chat_id, is_verified = 1
            """, (chat_id,))
            await db.commit()