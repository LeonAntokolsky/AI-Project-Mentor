import asyncio
import html
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from scanner import collect_project_context
from agent import MentorAgent
from database import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
db = Database(config.DB_PATH)
agent = MentorAgent(api_key=config.GEMINI_API_KEY)

MAX_TG_LENGTH = 4000

def get_task_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Builds inline buttons for user interaction."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Done", callback_data=f"done:{task_id}"),
            InlineKeyboardButton(text="⏭ Skip", callback_data=f"skip:{task_id}")
        ]
    ])

async def run_codebase_scan(chat_id: int):
    """Scans the mounted directory, calls Gemini API, and saves backlog tasks."""
    await bot.send_message(chat_id, "🔍 Scanning project files and analyzing architecture with Gemini...")
    try:
        code_dump = collect_project_context(config.CONTAINER_PROJECT_PATH)
        audit_result = await asyncio.to_thread(agent.analyze_codebase, code_dump)
        await db.save_audit_result(audit_result)
        summary_escaped = html.escape(audit_result.project_summary)
        await bot.send_message(
            chat_id,
            f"✅ <b>Analysis Complete!</b>\n\n<b>Project Summary:</b>\n{summary_escaped}\n\n"
            f"Generated <b>{len(audit_result.tasks)}</b> micro-tasks. Use /next to get your first task immediately!",
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Error during codebase scan: {e}")
        await bot.send_message(chat_id, f"❌ Error scanning project: {e}")

async def send_task_to_user(chat_id: int):
    """Fetches the next pending task and safely sends it within Telegram's character limits."""
    task = await db.get_next_task()
    if not task:
        await run_codebase_scan(chat_id)
        task = await db.get_next_task()
        if not task:
            return

    header = (
        f"🎯 <b>Micro-Task ({task['estimated_minutes']} mins)</b>\n"
        f"📂 <b>Category:</b> <code>{html.escape(task['category'])}</code>\n"
        f"📄 <b>File:</b> <code>{html.escape(task['file_path'])}</code>\n\n"
        f"<b>{html.escape(task['title'])}</b>\n"
        f"{html.escape(task['explanation'])}\n\n"
        f"<b>Suggested Fix:</b>\n"
    )

    code_fix = html.escape(task["ready_code_fix"])
    # Reserve space for header and <pre><code> tags so total length never exceeds 4096 chars
    max_code_len = MAX_TG_LENGTH - len(header) - 30
    if len(code_fix) > max_code_len:
        code_fix = code_fix[:max_code_len] + "\n# ... [Truncated to fit Telegram message limit]"

    full_text = f"{header}<pre><code>{code_fix}</code></pre>"

    await bot.send_message(
        chat_id,
        full_text,
        parse_mode="HTML",
        reply_markup=get_task_keyboard(task["id"])
    )

async def send_scheduled_ping():
    """Triggered automatically by APScheduler at regular intervals."""
    if not config.TELEGRAM_CHAT_ID:
        return

    ignored_count, summary = await db.increment_ignored_count()

    # Scenario 4: If user ignored 3 or more scheduled pings in a row, switch to Co-Founder Motivation Mode
    if ignored_count >= 3 and summary:
        logging.info("User ignored 3+ reminders. Triggering motivation/pivot mode.")
        pivot_msg = await asyncio.to_thread(agent.generate_motivation_pivot, summary, ignored_count)
        safe_msg = html.escape(pivot_msg)[:MAX_TG_LENGTH]
        await bot.send_message(
            config.TELEGRAM_CHAT_ID,
            f"💡 <b>Co-Founder Check-In</b>\n\n{safe_msg}",
            parse_mode="HTML"
        )
        return

    await send_task_to_user(config.TELEGRAM_CHAT_ID)

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        f"👋 Welcome to <b>AI Project Mentor</b>!\n\n"
        f"Your Chat ID is: <code>{message.chat.id}</code>\n\n"
        f"<b>Available Commands:</b>\n"
        f"/scan — Analyze mounted project and generate tasks\n"
        f"/next — Get the next micro-task right now\n"
        f"/status — View project progress and momentum stats\n"
        f"/motivate — Test the Co-Founder motivation &amp; pivot mode",
        parse_mode="HTML"
    )

@dp.message(Command("scan"))
async def cmd_scan(message: Message):
    await run_codebase_scan(message.chat.id)

@dp.message(Command("next"))
async def cmd_next(message: Message):
    await db.reset_ignored_count()
    await send_task_to_user(message.chat.id)

@dp.message(Command("status"))
async def cmd_status(message: Message):
    stats = await db.get_stats()
    await message.answer(
        f"📊 <b>Project Momentum Status</b>\n\n"
        f"✅ <b>Completed:</b> {stats['completed']}\n"
        f"⏳ <b>Pending in backlog:</b> {stats['pending']}\n"
        f"⏭ <b>Skipped:</b> {stats['skipped']}\n"
        f"💤 <b>Missed pings in a row:</b> {stats['ignored_count']}",
        parse_mode="HTML"
    )

@dp.message(Command("motivate"))
async def cmd_motivate(message: Message):
    """Allows manual testing of Scenario 4 (Motivation & Pivot Ideas)."""
    stats = await db.get_stats()
    if stats["summary"] == "Not scanned yet":
        await message.answer("Please run /scan first so I can understand your project!")
        return
    await message.answer("🧠 Thinking of new product ideas and an MVP rescue plan...")
    pivot_msg = await asyncio.to_thread(
        agent.generate_motivation_pivot, stats["summary"], max(stats["ignored_count"], 3)
    )
    safe_msg = html.escape(pivot_msg)[:MAX_TG_LENGTH]
    await message.answer(f"💡 <b>Co-Founder Check-In</b>\n\n{safe_msg}", parse_mode="HTML")

@dp.callback_query(F.data.startswith(("done:", "skip:")))
async def handle_task_callback(callback: CallbackQuery):
    action, task_id_str = callback.data.split(":")
    task_id = int(task_id_str)
    new_status = "completed" if action == "done" else "skipped"

    await db.update_task_status(task_id, new_status)
    status_label = "✅ Completed!" if action == "done" else "⏭ Skipped."
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(status_label)
    await callback.message.reply(
        f"{status_label} Momentum counter reset. Send /next if you want another task right away! 🚀"
    )

async def main():
    await db.init_db()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_scheduled_ping, "interval", hours=config.PING_INTERVAL_HOURS)
    scheduler.start()

    logging.info("Starting AI Project Mentor bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
