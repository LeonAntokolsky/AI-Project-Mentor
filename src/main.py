import asyncio
import html
import secrets
import os
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, BufferedInputFile, BotCommand
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google.genai.errors import APIError

import config
from scanner import collect_project_context, read_single_file
from agent import MentorAgent
from database import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
db = Database(config.DB_PATH)
agent = MentorAgent(api_key=config.GEMINI_API_KEY)
scheduler = AsyncIOScheduler()

MAIN_JOB_ID = "scheduled_ping_job"
MAX_TG_LENGTH = 4000
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0"))
AUTH_TOKEN_FILE = Path("/app/data/.auth_token")

def is_authorized(user_id: int) -> bool:
    """Checks if the user is allowed to interact with the bot."""
    return not ALLOWED_USER_ID or user_id == ALLOWED_USER_ID

def get_or_create_fs_token() -> str:
    if not AUTH_TOKEN_FILE.exists():
        AUTH_TOKEN_FILE.write_text(secrets.token_hex(8), encoding="utf-8")
    return AUTH_TOKEN_FILE.read_text(encoding="utf-8").strip()

@dp.message(Command("auth"))
async def cmd_auth(message: Message):
    if ALLOWED_USER_ID and message.from_user.id != ALLOWED_USER_ID:
        return
    parts = message.text.split(maxsplit=1)
    token = parts[1].strip() if len(parts) > 1 else ""
    if token and secrets.compare_digest(token, get_or_create_fs_token()):
        await db.set_user_verified(message.chat.id)
        await message.answer("🔐 <b> Access confirmed!  You have proven to have access to the server’s file system.", parse_mode="HTML")
    else:
        await message.answer("❌ Invalid token. Verify the data/. auth_token file on the server.", parse_mode="HTML")

async def unverified_filter(event: Message | CallbackQuery) -> bool:
    if ALLOWED_USER_ID and event.from_user.id != ALLOWED_USER_ID:
        return True
    return not (await db.is_user_verified())

@dp.message(unverified_filter)
async def block_unverified_msg(message: Message):
    get_or_create_fs_token()  # Ensure the auth token file is created on disk
    await message.answer(
        "🔒 <b>Bot is locked.</b>\n"
        "Prove server filesystem access: run <code>cat data/.auth_token</code> "
        "and send <code>/auth YOUR_TOKEN</code>",
        parse_mode="HTML"
    )

@dp.callback_query(unverified_filter)
async def block_unverified_cb(callback: CallbackQuery):
    await callback.answer("🔒 Please authenticate via /auth first!", show_alert=True)

@dp.callback_query(lambda cb: not is_authorized(cb.from_user.id))
async def unauthorized_callback_handler(callback: CallbackQuery):
    await callback.answer("⛔️ Unauthorized access.", show_alert=True)

async def setup_bot_commands(bot_instance: Bot):
    """Registers the persistent Command Menu in Telegram UI."""
    commands = [
        BotCommand(command="next", description="🎯 Get the next micro-task right now"),
        BotCommand(command="status", description="📊 View progress and momentum stats"),
        BotCommand(command="scan", description="🔍 Scan project and generate tasks"),
        BotCommand(command="settings", description="⚙️ Change reminder interval (1h-48h)"),
        BotCommand(command="motivate", description="💡 Co-Founder check-in & MVP rescue plan"),
        BotCommand(command="start", description="👋 Show welcome guide & help"),
    ]
    await bot_instance.set_my_commands(commands)

def get_task_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Builds inline buttons for verifying, snoozing, or skipping a task."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Verify & Done", callback_data=f"verify:{task_id}"),
            InlineKeyboardButton(text="⏭ Skip", callback_data=f"skip:{task_id}")
        ],
        [
            InlineKeyboardButton(text="⏳ Snooze (Remind Tomorrow)", callback_data=f"snooze:{task_id}")
        ]
    ])

def get_quick_actions_keyboard() -> InlineKeyboardMarkup:
    """Builds a rescue keyboard so the user never gets stuck."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 Next Task", callback_data="quick:next"),
            InlineKeyboardButton(text="📊 Status", callback_data="quick:status"),
        ],
        [
            InlineKeyboardButton(text="🔍 Rescan Project", callback_data="quick:scan"),
            InlineKeyboardButton(text="⚙️ Settings", callback_data="quick:settings"),
        ],
        [
            InlineKeyboardButton(text="📦 Commit & Push Changes", callback_data="git:commit_push")
        ]
    ])

def get_settings_keyboard(current_hours: int) -> InlineKeyboardMarkup:
    """Builds inline keyboard to change reminder interval on the fly."""
    options = [1, 6, 12, 24, 48]
    buttons = []
    for h in options:
        label = f"{'🔘 ' if h == current_hours else ''}{h}h"
        buttons.append(InlineKeyboardButton(text=label, callback_data=f"set_interval:{h}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])

async def run_codebase_scan(chat_id: int):
    """Scans the mounted directory, calls Gemini API, and saves backlog tasks."""
    await db.set_chat_id(chat_id)
    await bot.send_message(chat_id, "🔍 Scanning project files with UB-Mode skill principles...")
    try:
        code_dump = collect_project_context(config.CONTAINER_PROJECT_PATH)
        audit_result = await asyncio.to_thread(agent.analyze_codebase, code_dump)
        await db.save_audit_result(audit_result)
        summary_escaped = html.escape(audit_result.project_summary)
        await bot.send_message(
            chat_id,
            f"✅ <b>Analysis Complete!</b>\n\n<b>Project Summary:</b>\n{summary_escaped}\n\n"
            f"Generated <b>{len(audit_result.tasks)}</b> micro-tasks. Use /next to get your first task immediately!",
            parse_mode="HTML",
            reply_markup=get_quick_actions_keyboard()
        )
    except FileNotFoundError:
        logging.error(f"Project directory not found at {config.CONTAINER_PROJECT_PATH}")
        await bot.send_message(
            chat_id,
            "❌ <b>Error:</b> Project directory not found. Please check <code>TARGET_PROJECT_PATH</code> in your <code>.env</code>.",
            parse_mode="HTML"
        )
    except APIError as e:
        logging.error(f"Gemini API error during codebase scan: {e}")
        await bot.send_message(
            chat_id,
            f"❌ <b>Gemini API Error:</b> {html.escape(str(e))}",
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Unhandled error during codebase scan: {e}")
        await bot.send_message(
            chat_id,
            f"❌ <b>Unexpected error during scan:</b> {html.escape(str(e))}",
            parse_mode="HTML"
        )

async def send_task_to_user(chat_id: int):
    """Fetches the next pending task and sends it (attaching a file if code exceeds Telegram limits)."""
    task = await db.get_next_task()
    if not task:
        await bot.send_message(
            chat_id,
            "🎉 You've completed all tasks in the current backlog!\n"
            "Run /scan to generate new tasks or /motivate for a co-founder check-in.",
            reply_markup=get_quick_actions_keyboard()
        )
        return

    header = (
        f"🎯 <b>Micro-Task ({task['estimated_minutes']} mins)</b>\n"
        f"📂 <b>Category:</b> <code>{html.escape(task['category'])}</code>\n"
        f"📄 <b>File:</b> <code>{html.escape(task['file_path'])}</code>\n\n"
        f"<b>{html.escape(task['title'])}</b>\n"
        f"{html.escape(task['explanation'])}\n\n"
    )

    code_fix_escaped = html.escape(task["ready_code_fix"])
    full_text = f"{header}<b>Suggested Fix:</b>\n<pre><code>{code_fix_escaped}</code></pre>"

    if len(full_text) <= MAX_TG_LENGTH:
        await bot.send_message(
            chat_id,
            full_text,
            parse_mode="HTML",
            reply_markup=get_task_keyboard(task["id"])
        )
    else:
        ext = Path(task["file_path"]).suffix or ".txt"
        filename = f"suggested_fix_task_{task['id']}{ext}"
        file_bytes = task["ready_code_fix"].encode("utf-8")
        document = BufferedInputFile(file_bytes, filename=filename)

        caption = f"{header}📎 <i>The code snippet is large, so I attached the complete untruncated file below!</i>"
        await bot.send_document(
            chat_id,
            document=document,
            caption=caption[:1024],
            parse_mode="HTML",
            reply_markup=get_task_keyboard(task["id"])
        )

async def send_scheduled_ping():
    """Triggered automatically by APScheduler at regular intervals."""
    chat_id = await db.get_chat_id()
    if not chat_id:
        logging.warning("No chat_id registered in DB yet. Waiting for user to send /start.")
        return

    ignored_count, summary = await db.increment_ignored_count()

    if ignored_count >= 3 and summary:
        logging.info("User ignored 3+ reminders. Triggering motivation/pivot mode.")
        pivot_msg = await asyncio.to_thread(agent.generate_motivation_pivot, summary, ignored_count)
        safe_msg = html.escape(pivot_msg)[:MAX_TG_LENGTH]
        await bot.send_message(
            chat_id,
            f"💡 <b>Co-Founder Check-In</b>\n\n{safe_msg}",
            parse_mode="HTML",
            reply_markup=get_quick_actions_keyboard()
        )
        return

    await send_task_to_user(chat_id)

@dp.message(Command("start", "help"))
async def cmd_start(message: Message):
    await db.set_chat_id(message.chat.id)
    interval = await db.get_ping_interval(config.PING_INTERVAL_HOURS)
    await message.answer(
        f"👋 Welcome to <b>AI Project Mentor</b> (UB-Mode enabled)!\n\n"
        f"✅ Registered Chat ID: <code>{message.chat.id}</code>\n"
        f"⏰ Current Reminder Interval: <b>every {interval}h</b>\n\n"
        f"<b>Available Commands:</b>\n"
        f"/next — Get the next micro-task right now\n"
        f"/scan — Analyze mounted project and generate tasks\n"
        f"/status — View project progress and momentum stats\n"
        f"/settings — Change reminder interval on the fly\n"
        f"/motivate — Test the Co-Founder motivation & pivot mode",
        parse_mode="HTML",
        reply_markup=get_quick_actions_keyboard()
    )

@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    await db.set_chat_id(message.chat.id)
    current_hours = await db.get_ping_interval(config.PING_INTERVAL_HOURS)
    await message.answer(
        f"⚙️ <b>Reminder Schedule Settings</b>\n\n"
        f"Current interval: <b>every {current_hours} hours</b>.\n"
        f"Select a new interval below (applies immediately without restarting):",
        parse_mode="HTML",
        reply_markup=get_settings_keyboard(current_hours)
    )

@dp.callback_query(F.data.startswith("set_interval:"))
async def handle_set_interval(callback: CallbackQuery):
    hours = int(callback.data.split(":")[1])
    await db.set_ping_interval(hours)

    scheduler.add_job(
        send_scheduled_ping,
        "interval",
        hours=hours,
        id=MAIN_JOB_ID,
        replace_existing=True
    )

    await callback.message.edit_text(
        f"⚙️ <b>Reminder Schedule Settings</b>\n\n"
        f"✅ Updated! I will now ping you <b>every {hours} hours</b>.",
        parse_mode="HTML",
        reply_markup=get_settings_keyboard(hours)
    )
    await callback.answer(f"Interval set to {hours}h!")

@dp.message(Command("scan"))
async def cmd_scan(message: Message):
    await run_codebase_scan(message.chat.id)

@dp.message(Command("next"))
async def cmd_next(message: Message):
    await db.set_chat_id(message.chat.id)
    await db.reset_ignored_count()
    await send_task_to_user(message.chat.id)

@dp.message(Command("status"))
async def cmd_status(message: Message):
    await db.set_chat_id(message.chat.id)
    stats = await db.get_stats()
    await message.answer(
        f"📊 <b>Project Momentum Status</b>\n\n"
        f"✅ <b>Completed & Verified:</b> {stats['completed']}\n"
        f"⏳ <b>Pending in backlog:</b> {stats['pending']}\n"
        f"⏭ <b>Skipped:</b> {stats['skipped']}\n"
        f"💤 <b>Missed pings in a row:</b> {stats['ignored_count']}\n"
        f"⏰ <b>Ping interval:</b> every {stats['ping_interval_hours']}h",
        parse_mode="HTML",
        reply_markup=get_quick_actions_keyboard()
    )

@dp.message(Command("motivate"))
async def cmd_motivate(message: Message):
    await db.set_chat_id(message.chat.id)
    stats = await db.get_stats()
    if stats["summary"] == "Not scanned yet":
        await message.answer(
            "Please run /scan first so I can understand your project!",
            reply_markup=get_quick_actions_keyboard()
        )
        return
    await message.answer("🧠 Thinking of new product ideas and an MVP rescue plan...")
    pivot_msg = await asyncio.to_thread(
        agent.generate_motivation_pivot, stats["summary"], max(stats["ignored_count"], 3)
    )
    safe_msg = html.escape(pivot_msg)[:MAX_TG_LENGTH]
    await message.answer(
        f"💡 <b>Co-Founder Check-In</b>\n\n{safe_msg}",
        parse_mode="HTML",
        reply_markup=get_quick_actions_keyboard()
    )

@dp.callback_query(F.data.startswith("quick:"))
async def handle_quick_actions(callback: CallbackQuery):
    """Handles quick action buttons so the user can navigate without typing commands."""
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    await db.set_chat_id(chat_id)
    await callback.answer()

    if action == "next":
        await db.reset_ignored_count()
        await send_task_to_user(chat_id)
    elif action == "status":
        stats = await db.get_stats()
        await callback.message.answer(
            f"📊 <b>Project Momentum Status</b>\n\n"
            f"✅ <b>Completed & Verified:</b> {stats['completed']}\n"
            f"⏳ <b>Pending in backlog:</b> {stats['pending']}\n"
            f"⏭ <b>Skipped:</b> {stats['skipped']}\n"
            f"💤 <b>Missed pings in a row:</b> {stats['ignored_count']}\n"
            f"⏰ <b>Ping interval:</b> every {stats['ping_interval_hours']}h",
            parse_mode="HTML",
            reply_markup=get_quick_actions_keyboard()
        )
    elif action == "scan":
        await run_codebase_scan(chat_id)
    elif action == "settings":
        current_hours = await db.get_ping_interval(config.PING_INTERVAL_HOURS)
        await callback.message.answer(
            f"⚙️ <b>Reminder Schedule Settings</b>\n\n"
            f"Current interval: <b>every {current_hours} hours</b>.\n"
            f"Select a new interval below:",
            parse_mode="HTML",
            reply_markup=get_settings_keyboard(current_hours)
        )

@dp.callback_query(F.data.startswith(("verify:", "done:")))
async def handle_verify_callback(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    task = await db.get_task_by_id(task_id)
    if not task:
        await callback.answer("Task not found!", show_alert=True)
        return

    await callback.answer("🔍 Checking your code changes...")
    status_msg = await callback.message.reply(
        f"🕵️‍♂️ Inspecting <code>{html.escape(task['file_path'])}</code> to verify your fix...",
        parse_mode="HTML"
    )

    try:
        current_code = read_single_file(config.CONTAINER_PROJECT_PATH, task["file_path"])
        verification = await asyncio.to_thread(agent.verify_task_fix, task, current_code)
    except Exception as e:
        await status_msg.edit_text(f"❌ Could not read file for verification: {html.escape(str(e))}")
        return

    feedback_escaped = html.escape(verification.feedback)
    if verification.is_completed:
        await db.update_task_status(task_id, "completed")
        await callback.message.edit_reply_markup(reply_markup=None)
        await status_msg.edit_text(
            f"✅ <b>Verification Passed!</b>\n\n{feedback_escaped}\n\n"
            f"Task marked as completed! Moving to the next task... 🚀",
            parse_mode="HTML"
        )
        await send_task_to_user(callback.message.chat.id)
    else:
        await db.reset_ignored_count()
        await status_msg.edit_text(
            f"⚠️ <b>Not quite ready yet!</b>\n\n{feedback_escaped}\n\n"
            f"<i>Update the file and click <b>✅ Verify & Done</b> again when ready.</i>",
            parse_mode="HTML"
        )

@dp.callback_query(F.data.startswith("skip:"))
async def handle_skip_callback(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    await db.update_task_status(task_id, "skipped")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("⏭ Skipped")
    await callback.message.reply("⏭ Task skipped. Fetching the next one...")
    await send_task_to_user(callback.message.chat.id)

@dp.callback_query(F.data.startswith("snooze:"))
async def handle_snooze_callback(callback: CallbackQuery):
    # Keep the buttons intact so the user can still verify or skip whenever they return!
    await db.reset_ignored_count()
    interval = await db.get_ping_interval(config.PING_INTERVAL_HOURS)
    next_run = datetime.now() + timedelta(hours=24)
    scheduler.add_job(
        send_scheduled_ping,
        "interval",
        hours=interval,
        next_run_time=next_run,
        id=MAIN_JOB_ID,
        replace_existing=True
    )
    await callback.answer("⏳ Snoozed for 24 hours!")
    await callback.message.reply(
        "⏳ <b>Snoozed for 24 hours!</b>\n"
        "You can still click <b>✅ Verify & Done</b> above whenever you finish, or use the quick actions below:",
        parse_mode="HTML",
        reply_markup=get_quick_actions_keyboard()
    )

@dp.callback_query(F.data == "git:commit_push")
async def handle_git_commit_push(callback: CallbackQuery):
    await callback.answer("📦 Checking modified files in Git...")
    proj_dir = config.CONTAINER_PROJECT_PATH

    try:
        # Allow git to operate inside the mounted directory
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", proj_dir], check=False)

        # Get diff only for modified tracked files
        diff_proc = subprocess.run(["git", "diff", "HEAD"], cwd=proj_dir, capture_output=True, text=True)
        diff_text = diff_proc.stdout.strip()

        if not diff_text:
            await callback.message.answer("ℹ️ No modified tracked files to commit (`git diff` is empty).")
            return

        status_msg = await callback.message.answer("🧠 Generating commit message from changes and updating Git...")

        # 1. Generate commit description via Gemini
        commit_msg = await asyncio.to_thread(agent.generate_commit_message, diff_text)

        # 2. Stage ONLY modified files (git add -u ignores untruncated junk and untracked files)
        subprocess.run(["git", "add", "-u"], cwd=proj_dir, check=True)

        # 3. Set default author credentials (if not configured in container) and commit
        subprocess.run(["git", "config", "user.name", "AI Project Mentor"], cwd=proj_dir, check=False)
        subprocess.run(["git", "config", "user.email", "mentor@local"], cwd=proj_dir, check=False)
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=proj_dir, check=True)

        # 4. Attempt git push
        push_proc = subprocess.run(["git", "push"], cwd=proj_dir, capture_output=True, text=True)
        if push_proc.returncode == 0:
            await status_msg.edit_text(
                f"✅ <b>Git successfully updated and pushed!</b>\n"
                f"📝 <b>Commit:</b> <code>{html.escape(commit_msg)}</code>",
                parse_mode="HTML"
            )
        else:
            await status_msg.edit_text(
                f"✅ <b>Local commit created successfully!</b>\n"
                f"📝 <code>{html.escape(commit_msg)}</code>\n\n"
                f"⚠️ <i>Push requires host authentication:</i>\n<code>{html.escape(push_proc.stderr[:300])}</code>",
                parse_mode="HTML"
            )
    except Exception as e:
        await callback.message.answer(f"❌ <b>Git Error:</b> {html.escape(str(e))}", parse_mode="HTML")


# Fallback handler AT THE VERY BOTTOM so the user NEVER gets silence
@dp.message()
async def fallback_message_handler(message: Message):
    await db.set_chat_id(message.chat.id)
    await message.answer(
        "🤔 I didn't quite catch that command.\n\n"
        "Use the <b>Menu</b> button on the left of your message bar or pick an action below:",
        parse_mode="HTML",
        reply_markup=get_quick_actions_keyboard()
    )

async def main():
    await db.init_db(default_interval=config.PING_INTERVAL_HOURS)
    interval = await db.get_ping_interval(config.PING_INTERVAL_HOURS)

    await setup_bot_commands(bot)

    scheduler.add_job(
        send_scheduled_ping,
        "interval",
        hours=interval,
        id=MAIN_JOB_ID,
        replace_existing=True
    )
    scheduler.start()

    logging.info(f"Starting AI Project Mentor bot (Ping interval: {interval}h)...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
