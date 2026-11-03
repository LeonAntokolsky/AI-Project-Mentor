import json
import aiosqlite
from contextlib import asynccontextmanager
from typing import Optional
from agent import BacklogTask, ProjectAuditResult
from datetime import datetime

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    @asynccontextmanager
    async def _get_db(self):
        """Centralized async context manager providing a configured SQLite connection."""
        async with aiosqlite.connect(self.db_path, timeout=15.0) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            db.row_factory = aiosqlite.Row
            yield db

    async def init_db(self, default_interval: int = 24):
        """Initializes SQLite tables and runs safe schema migrations."""
        async with self._get_db() as db:
            await db.execute(f"""
                CREATE TABLE IF NOT EXISTS project_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    chat_id INTEGER,
                    summary TEXT,
                    ignored_count INTEGER DEFAULT 0,
                    ping_interval_hours INTEGER DEFAULT {default_interval},
                    is_verified INTEGER DEFAULT 0,
                    current_focus TEXT DEFAULT ''
                )
            """)
            for col_def in ["is_verified INTEGER DEFAULT 0", "current_focus TEXT DEFAULT ''"]:
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
                    status TEXT DEFAULT 'pending'
                )
            """)
            migrations = [
                ("tasks", "session_id TEXT DEFAULT ''"),
                ("project_state", "current_session_id TEXT DEFAULT ''"),
                ("tasks", "expected_profit TEXT DEFAULT ''"),
                ("tasks", "search_block TEXT DEFAULT ''"),
                ("tasks", "dependent_patches TEXT DEFAULT '[]'"),
            ]
            for table, col in migrations:
                try:
                    await db.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
                except Exception:
                    pass
            await db.commit()

    async def _update_state_field(self, column: str, value: any):
        """Helper to upsert a single field in project_state for row id=1."""
        allowed_columns = {
            "chat_id", "ping_interval_hours", "is_verified", "summary",
            "current_focus", "current_session_id", "ignored_count"
        }
        if column not in allowed_columns:
            raise ValueError(f"Invalid state column: {column}")

        async with self._get_db() as db:
            await db.execute(f"""
                INSERT INTO project_state (id, {column})
                VALUES (1, ?)
                ON CONFLICT(id) DO UPDATE SET {column} = excluded.{column}
            """, (value,))
            await db.commit()

    async def set_chat_id(self, chat_id: int):
        """Sets or updates the active Telegram chat ID."""
        await self._update_state_field("chat_id", chat_id)

    async def _get_state_field(self, column: str, default: any = None) -> any:
        """Helper to fetch a single column from project_state for row id=1."""
        allowed_columns = {
            "chat_id", "ping_interval_hours", "is_verified", "summary",
            "current_focus", "current_session_id", "ignored_count"
        }
        if column not in allowed_columns:
            raise ValueError(f"Invalid state column: {column}")

        async with self._get_db() as db:
            cursor = await db.execute(f"SELECT {column} FROM project_state WHERE id = 1")
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else default

    async def get_chat_id(self) -> Optional[int]:
        """Retrieves the registered Telegram chat_id."""
        return await self._get_state_field("chat_id")

    async def set_ping_interval(self, interval_hours: int):
        """Sets or updates the ping interval in hours."""
        await self._update_state_field("ping_interval_hours", interval_hours)

    async def set_user_verified(self):
        """Marks user as verified for filesystem access."""
        await self._update_state_field("is_verified", 1)

    async def get_ping_interval(self, default_hours: int = 24) -> int:
        """Retrieves the current reminder interval in hours."""
        return await self._get_state_field("ping_interval_hours", default_hours)

    async def get_completed_tasks(self) -> list[dict]:
        """Fetches completed tasks belonging strictly to the active session."""
        async with self._get_db() as db:
            cursor = await db.execute("""
                SELECT t.* FROM tasks t
                JOIN project_state p ON p.id = 1
                WHERE t.status = 'completed'
                  AND (t.session_id = p.current_session_id OR p.current_session_id = '')
                ORDER BY t.id ASC
            """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_current_focus(self) -> str:
        """Retrieves the active session focus direction."""
        return (await self._get_state_field("current_focus")) or "General Code Refactoring"

    async def save_audit_result(self, audit: ProjectAuditResult, focus_direction: str = ""):
        """Saves project summary, active focus direction, populates tasks, and initializes session_id."""
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        async with self._get_db() as db:
            await db.execute("""
                INSERT INTO project_state (id, summary, ignored_count, current_focus, current_session_id)
                VALUES (1, ?, 0, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    summary = excluded.summary,
                    ignored_count = 0,
                    current_focus = excluded.current_focus,
                    current_session_id = excluded.current_session_id
            """, (audit.project_summary, focus_direction, session_id))

            await db.execute("DELETE FROM tasks WHERE status = 'pending'")

            records = [
                (
                    t.category,
                    t.file_path,
                    t.title,
                    t.explanation,
                    t.expected_profit,
                    t.search_block,
                    t.ready_code_fix,
                    t.estimated_minutes,
                    json.dumps([p.model_dump() for p in getattr(t, 'dependent_patches', [])]),
                    session_id,
                )
                for t in audit.tasks
            ]
            await db.executemany("""
                INSERT INTO tasks (
                    category, file_path, title, explanation,
                    expected_profit, search_block, ready_code_fix,
                    estimated_minutes, dependent_patches, session_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, records)
            await db.commit()

    async def replace_with_alternative_task(self, task_id: int, alt: BacklogTask) -> int:
        """Marks old task as skipped and inserts alternative task with the active session_id."""
        async with self._get_db() as db:
            cursor = await db.execute("SELECT current_session_id FROM project_state WHERE id = 1")
            row = await cursor.fetchone()
            session_id = row[0] if row and row[0] else ""

            await db.execute("UPDATE tasks SET status = 'skipped' WHERE id = ?", (task_id,))
            patches_json = json.dumps([p.model_dump() for p in getattr(alt, 'dependent_patches', [])])
            cursor = await db.execute("""
                INSERT INTO tasks (
                    category, file_path, title, explanation,
                    expected_profit, search_block, ready_code_fix,
                    estimated_minutes, dependent_patches, status, session_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """, (
                alt.category, alt.file_path, alt.title, alt.explanation,
                alt.expected_profit, alt.search_block, alt.ready_code_fix,
                alt.estimated_minutes, patches_json, session_id
            ))
            await db.commit()
            return cursor.lastrowid

    async def _fetch_task(self, query: str, params: tuple = ()) -> Optional[dict]:
        """Executes a task lookup query and returns a dictionary representation."""
        async with self._get_db() as db:
            cursor = await db.execute(query, params)
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_next_task(self) -> Optional[dict]:
        """Fetches the next pending micro-task from the backlog."""
        return await self._fetch_task(
            "SELECT * FROM tasks WHERE status = 'pending' ORDER BY id ASC LIMIT 1"
        )

    async def get_task_by_id(self, task_id: int) -> Optional[dict]:
        """Fetches a specific task by its ID for verification."""
        return await self._fetch_task("SELECT * FROM tasks WHERE id = ?", (task_id,))

    async def update_task_status(self, task_id: int, status: str):
        """Updates task status and resets ignored_count when user interacts."""
        async with self._get_db() as db:
            await db.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
            await db.commit()
        await self.reset_ignored_count()

    async def reset_ignored_count(self):
        """Resets ignored counter when user manually interacts with the bot."""
        async with self._get_db() as db:
            await db.execute("UPDATE project_state SET ignored_count = 0 WHERE id = 1")
            await db.commit()

    async def increment_ignored_count(self) -> tuple[int, str]:
        """Increments ignored counter and returns (ignored_count, project_summary)."""
        async with self._get_db() as db:
            await db.execute("UPDATE project_state SET ignored_count = ignored_count + 1 WHERE id = 1")
            await db.commit()
            cursor = await db.execute("SELECT ignored_count, summary FROM project_state WHERE id = 1")
            row = await cursor.fetchone()
            return (row[0], row[1]) if row else (0, "")

    async def get_stats(self) -> dict:
        """Returns current project statistics and task counts."""
        async with self._get_db() as db:
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
        """Checks if the active user has verified filesystem ownership."""
        return bool(await self._get_state_field("is_verified", 0))