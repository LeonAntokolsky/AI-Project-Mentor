from __future__ import annotations

import asyncio
import html
import secrets
import os
import random
import logging
import config
import json
import subprocess
import py_compile
from report_generator import generate_session_pdf_report
from typing import Dict
from datetime import datetime, timedelta
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, BufferedInputFile, BotCommand,
    MessageReactionUpdated, ReactionTypeEmoji, FSInputFile
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google.genai.errors import APIError
from scanner import collect_project_context, read_single_file
from agent import MentorAgent
from database import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

bot = Bot(config.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
db = Database(config.DB_PATH)
agent = MentorAgent()
scheduler = AsyncIOScheduler()

# Temporary in-memory store for custom text focus confirmation
pending_custom_focus: Dict[int, str] = {}


CUTE_HEART_REPLIES = [
    "🥺💖 Oh, thank you so much! I’m trying so hard to be useful!",
    "🥰✨ Your heart broke my silicon schemes! They pushed the code further!" ,
    "❤️ Thank you for your love! We will make sure to release this project!" ,
    "😻 Moore-moore, I can see a heartbeat! You’re an incredible developer!" ,
    "🌸💞 Thank you so much! My virtual motivation has peaked!"
]
ALLOWED_HEART_EMOJIS = {"❤️", "💖", "🥰", "💕", "❤"}

MAIN_JOB_ID = "scheduled_ping_job"
MAX_TG_LENGTH = 4000
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0"))
AUTH_TOKEN_FILE = Path("/app/data/.auth_token")
FOCUS_PRESETS = {
    "security": "Security hardening, input validation, auth protection, and secret safety",
    "perf": "Performance optimization, async efficiency, I/O reduction, and faster DB queries",
    "clean": "Strict UB-Mode refactoring: remove duplication, simplify state, and improve readability",
    "ux": "User experience, better error messages, interactive Telegram UI, and edge-case handling",
    "tests": "Adding unit tests, edge-case coverage, and safety assertions",
    "architecture": "Architectural refactoring, modularization, and decoupling logic",
    "full": "Full comprehensive audit covering security, performance, clean code, and bug fixes",
}

def is_authorized(user_id: int) -> bool:
    """Checks if the user is allowed to interact with the bot."""
    return not ALLOWED_USER_ID or user_id == ALLOWED_USER_ID

def get_or_create_fs_token() -> str:
    if not AUTH_TOKEN_FILE.exists():
        AUTH_TOKEN_FILE.write_text(secrets.token_hex(8), encoding="utf-8")
    return AUTH_TOKEN_FILE.read_text(encoding="utf-8").strip()

def extract_emojis(reactions_list: list) -> set[str]:
    """Extracts normalized emoji strings from Telegram ReactionType objects."""
    return {
        r.emoji.replace("\ufe0f", "")
        for r in reactions_list
        if isinstance(r, ReactionTypeEmoji)
    }

def get_cute_heart_reply() -> str:
    return random.choice(CUTE_HEART_REPLIES)

def check_file_syntax(file_path: Path) -> str | None:
    """Validates syntax for supported file types, returning error string if invalid."""
    if not isinstance(file_path, Path) or not file_path.exists() or not file_path.is_file():
        return f"File does not exist or is invalid: {file_path}"
    if file_path.suffix == ".py":
        try:
            py_compile.compile(file_path, doraise=True)
        except py_compile.PyCompileError as err:
            return str(err)
    elif file_path.suffix == ".json":
        try:
            json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as err:
            return str(err)
    return None

def clean_patch_text(text: str | None) -> str:
    """Removes accidental line number prefixes (e.g. '12: ') emitted by LLMs while preserving indentation."""
    if not text or not isinstance(text, str):
        return ""
    import re
    cleaned_lines = [
        re.sub(r"^\s*\d+:\s?", "", line)
        for line in text.replace("\r\n", "\n").split("\n")
    ]
    return "\n".join(cleaned_lines)

def apply_text_patch(content: str | None, search_block: str | None, replacement: str | None) -> str | None:
    """Pure function to safely apply search-and-replace with newline and line-number normalization."""
    if not content or not isinstance(content, str) or not search_block:
        return None
    norm_content = content.replace("\r\n", "\n")
    norm_search = clean_patch_text(search_block).strip("\r\n")
    norm_replace = clean_patch_text(replacement or "").strip("\r\n")

    if norm_search and norm_search in norm_content:
        return norm_content.replace(norm_search, norm_replace, 1)

    # Fallback to trimmed search block if trailing blank lines differ
    trimmed_search = norm_search.strip()
    if trimmed_search and trimmed_search in norm_content:
        return norm_content.replace(trimmed_search, norm_replace.strip(), 1)

    return None

def format_status_message(stats: dict) -> str:
    return (
        f"📊 <b>Project Momentum Status</b>\n\n"
        f"✅ <b>Completed & Verified:</b> {stats['completed']}\n"
        f"⏳ <b>Pending in backlog:</b> {stats['pending']}\n"
        f"⏭️ <b>Skipped:</b> {stats['skipped']}\n"
        f"💤 <b>Missed pings in a row:</b> {stats['ignored_count']}\n"
        f"⏰ <b>Ping interval:</b> every {stats['ping_interval_hours']}h"
    )

def resolve_target_channel(target: Message | CallbackQuery):
    """Resolves (chat_id, send_func) uniformly from Message or CallbackQuery."""
    if isinstance(target, Message):
        return target.chat.id, target.answer
    return target.message.chat.id, target.message.answer

async def send_status_view(target: Message | CallbackQuery):
    stats = await db.get_stats()
    _, send = resolve_target_channel(target)
    await send(format_status_message(stats), parse_mode="HTML", reply_markup=get_quick_actions_keyboard())

async def send_settings_menu(target: Message | CallbackQuery):
    """Sends the schedule settings menu for both command and quick action button callbacks."""
    chat_id, send = resolve_target_channel(target)
    await db.set_chat_id(chat_id)
    hours = await db.get_ping_interval(config.PING_INTERVAL_HOURS)
    text = (
        f"⚙️ <b>Reminder Schedule Settings</b>\n\n"
        f"Current interval: <b>every {hours} hours</b>.\n"
        f"Select a new interval below:"
    )
    await send(text, parse_mode="HTML", reply_markup=get_settings_keyboard(hours))

async def send_focus_menu(target: Message | CallbackQuery):
    """Sends the focused audit menu for both command and quick action button callbacks."""
    chat_id, send = resolve_target_channel(target)
    await db.set_chat_id(chat_id)
    text = (
        "🧭 <b>Focused Codebase Audit</b>\n\n"
        "Choose a focus preset below, or simply <b>type any custom goal in the chat</b> "
        "(e.g., <i>'Add rate limiting and protect database calls'</i>):"
    )
    await send(text, parse_mode="HTML", reply_markup=get_focus_presets_keyboard())

def get_session_complete_keyboard() -> InlineKeyboardMarkup:
    """Builds quick action buttons after session completion (without 'Next Task')."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Status", callback_data="quick:status"),
            InlineKeyboardButton(text="🔍 New Focus Scan", callback_data="quick:scan"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Settings", callback_data="quick:settings"),
            InlineKeyboardButton(text="📦 Commit & Push Changes", callback_data="git:commit_push")
        ]
    ])

async def send_session_pdf_report(chat_id: int):
    """Generates PDF report of completed tasks and sends it to the Telegram chat."""
    completed_tasks = await db.get_completed_tasks()
    current_focus = await db.get_current_focus()

    if not completed_tasks:
        await bot.send_message(
            chat_id,
            "ℹ️ <b>No fixes were applied in this session.</b> PDF report was not created.",
            parse_mode="HTML",
            reply_markup=get_session_complete_keyboard()
        )
        return

    status_msg = await bot.send_message(chat_id, "📄 <b>Generating PDF session report...</b>", parse_mode="HTML")

    try:
        pdf_path = await asyncio.to_thread(
            generate_session_pdf_report, current_focus, completed_tasks
        )
        doc_file = FSInputFile(str(pdf_path), filename=pdf_path.name)

        await bot.send_document(
            chat_id,
            document=doc_file,
            caption=(
                f"📊 <b>Session Complete!</b>\n\n"
                f"✅ Applied fixes: <b>{len(completed_tasks)}</b>\n"
                f"📁 Saved locally to: <code>{pdf_path}</code>"
            ),
            parse_mode="HTML",
            reply_markup=get_session_complete_keyboard()
        )
        await status_msg.delete()
    except Exception as e:
        logging.error(f"Error generating PDF report: {e}")
        await status_msg.edit_text(f"❌ <b>Failed to generate PDF report:</b> {html.escape(str(e))}", parse_mode="HTML")

async def run_task_verification(callback: CallbackQuery, task: dict):
    """Inspects target file content and runs AI verification with Gemini automatically."""
    status_msg = await callback.message.reply(
        f"🕵️‍♂️ Inspecting <code>{html.escape(task['file_path'])}</code> to verify fix with AI...",
        parse_mode="HTML"
    )

    try:
        current_code = read_single_file(config.CONTAINER_PROJECT_PATH, task["file_path"])
        verification = await asyncio.to_thread(agent.verify_task_fix, task, current_code)
    except Exception as e:
        await status_msg.edit_text(f"❌ Could not read file for verification: {html.escape(str(e))}")
        return

    feedback_escaped = html.escape(verification.feedback)
    task_id = task["id"]

    # Безопасно убираем клавиатуру у исходного сообщения
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass

    if verification.is_completed:
        await db.update_task_status(task_id, "completed")

        kb_next = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Next Task", callback_data="quick:next")],
            [InlineKeyboardButton(text="🛑 Stop Session & Get PDF Report", callback_data="task:stop_session")]
        ])
        await status_msg.edit_text(
            f"✅ <b>Verification Passed!</b>\n\n{feedback_escaped}\n\n"
            f"Task verified and marked as completed! 🚀",
            parse_mode="HTML",
            reply_markup=kb_next
        )
    else:
        await db.reset_ignored_count()
        await status_msg.edit_text(
            f"⚠️ <b>Verification Alert:</b>\n\n{feedback_escaped}\n\n"
            f"<i>Update the file and click below to re-verify when ready:</i>",
            parse_mode="HTML",
            reply_markup=get_post_task_keyboard(task_id)
        )

@dp.message(Command("auth"))
async def cmd_auth(message: Message):
    if ALLOWED_USER_ID and message.from_user.id != ALLOWED_USER_ID:
        return
    parts = message.text.split(maxsplit=1)
    token = parts[1].strip() if len(parts) > 1 else ""
    if token and secrets.compare_digest(token, get_or_create_fs_token()):
        await db.set_user_verified(message.chat.id)
        await message.answer("🔐 <b>Access confirmed!</b> You have proven access to the server's filesystem.", parse_mode="HTML")
    else:
        await message.answer("❌ Invalid token. Verify the data/.auth_token file on the server.", parse_mode="HTML")

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
        BotCommand(command="focus", description="🧭 Scan codebase with a custom focus/goal"),
        BotCommand(command="next", description="🎯 Get the next micro-task right now"),
        BotCommand(command="status", description="📊 View progress and momentum stats"),
        BotCommand(command="scan", description="🔍 Scan project and generate tasks"),
        BotCommand(command="settings", description="⚙️ Change reminder interval (1h-48h)"),
        BotCommand(command="motivate", description="💡 Co-Founder check-in & MVP rescue plan"),
        BotCommand(command="start", description="👋 Show welcome guide & help"),
    ]
    await bot_instance.set_my_commands(commands)

def get_task_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Builds interactive buttons for a task including an explicit Stop & Report action."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛠 Apply Fix Auto", callback_data=f"task:apply:{task_id}")],
        [
            InlineKeyboardButton(text="✅ Done Manually", callback_data=f"task:done:{task_id}"),
            InlineKeyboardButton(text="🔄 Reject & Alt", callback_data=f"task:reject:{task_id}")
        ],
        [InlineKeyboardButton(text="🛑 Stop Session & Get PDF Report", callback_data="task:stop_session")]
    ])

def get_post_task_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Builds standardized keyboard after a task is marked done or auto-applied."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Verify Fix with AI", callback_data=f"task:verify:{task_id}")],
        [InlineKeyboardButton(text="🎯 Next Task", callback_data="quick:next")],
        [InlineKeyboardButton(text="🛑 Stop Session & Get PDF Report", callback_data="task:stop_session")]
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

def get_focus_presets_keyboard() -> InlineKeyboardMarkup:
    """Builds 1-click focus preset buttons."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔒 Security & Auth", callback_data="focus_preset:security"),
            InlineKeyboardButton(text="⚡ Performance", callback_data="focus_preset:perf"),
        ],
        [
            InlineKeyboardButton(text="🧹 Clean Code (UB)", callback_data="focus_preset:clean"),
            InlineKeyboardButton(text="✨ UX & Reliability", callback_data="focus_preset:ux"),
        ],
        [
            InlineKeyboardButton(text="🧪 Tests & Edge-Cases", callback_data="focus_preset:tests"),
            InlineKeyboardButton(text="🏗 Architecture", callback_data="focus_preset:architecture"),
        ],
        [
            InlineKeyboardButton(text="🎯 Full Comprehensive Audit", callback_data="focus_preset:full"),
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

async def run_codebase_scan(chat_id: int, focus_direction: str = ""):
    """Scans the mounted directory with an optional focus direction and saves tasks."""
    await db.set_chat_id(chat_id)
    focus_badge = f"\n🧭 <b>Active Focus:</b> <i>{html.escape(focus_direction)}</i>" if focus_direction else ""
    await bot.send_message(
        chat_id,
        f"🔍 Scanning project files with UB-Mode skill principles...{focus_badge}",
        parse_mode="HTML"
    )
    try:
        code_dump = await asyncio.to_thread(collect_project_context, config.CONTAINER_PROJECT_PATH)
        audit_result = await asyncio.to_thread(agent.analyze_codebase, code_dump, focus_direction)
        await db.save_audit_result(audit_result, focus_direction)
        summary_escaped = html.escape(audit_result.project_summary)
        await bot.send_message(
            chat_id,
            f"✅ <b>Analysis Complete!</b>{focus_badge}\n\n"
            f"<b>Project Summary:</b>\n{summary_escaped}\n\n"
            f"Generated <b>{len(audit_result.tasks)}</b> focused micro-tasks with ROI analysis. "
            f"Use /next to start!",
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

    # 1. Check if backlog is empty FIRST before referencing task properties
    if not task:
        await send_session_pdf_report(chat_id)
        return

    # 2. Safely parse profit_text now that task is guaranteed to be a dict
    profit_text = html.escape(task.get("expected_profit") or "Improves code reliability and maintainability.")

    header = (
        f"🎯 <b>Micro-Task ({task['estimated_minutes']} mins)</b>\n"
        f"📂 <b>Category:</b> <code>{html.escape(task['category'])}</code>\n"
        f"📄 <b>File:</b> <code>{html.escape(task['file_path'])}</code>\n\n"
        f"<b>{html.escape(task['title'])}</b>\n"
        f"{html.escape(task['explanation'])}\n\n"
        f"💎 <b>Why & Profit (ROI):</b>\n<i>{profit_text}</i>\n\n"
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

        # Compact caption guaranteed to fit under Telegram's 1024-char limit safely
        caption = (
            f"🎯 <b>Micro-Task ({task['estimated_minutes']} mins)</b>\n"
            f"📄 <b>File:</b> <code>{html.escape(task['file_path'])}</code>\n\n"
            f"<b>{html.escape(task['title'])}</b>\n\n"
            f"📎 <i>The code fix is large, so it is attached as a file above!</i>"
        )

        await bot.send_document(
            chat_id,
            document=document,
            caption=caption,
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

@dp.message_reaction()
async def handle_heart_reaction(event: MessageReactionUpdated):
    # 1. Ignore reactions made by bots to prevent feedback loops
    if not event.user or event.user.is_bot or not is_authorized(event.user.id):
        return

    old_emojis = extract_emojis(event.old_reaction)
    new_emojis = extract_emojis(event.new_reaction)

    # 2. Check if a new heart reaction was added
    added_emojis = new_emojis - old_emojis
    has_new_heart = any(emoji in ALLOWED_HEART_EMOJIS for emoji in added_emojis)

    if not has_new_heart:
        return

    # 3. Set reciprocal reaction on the message
    try:
        await bot.set_message_reaction(
            chat_id=event.chat.id,
            message_id=event.message_id,
            reaction=[ReactionTypeEmoji(emoji="🥰")]
        )
    except Exception as e:
        logging.debug(f"Failed to set reciprocal reaction: {e}")

    # 4. Pick a random reply and send it
    reply_text = random.choice(CUTE_HEART_REPLIES)
    try:
        await bot.send_message(
            chat_id=event.chat.id,
            text=reply_text,
            reply_to_message_id=event.message_id
        )
    except Exception as e:
        logging.error(f"Failed to send cute reply text: {e}")

    # 5. Reset ping reminder counters in DB
    await db.set_chat_id(event.chat.id)
    await db.reset_ignored_count()

@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    await send_settings_menu(message)

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
    await cmd_focus(message)

@dp.message(Command("next"))
async def cmd_next(message: Message):
    await db.set_chat_id(message.chat.id)
    await db.reset_ignored_count()
    await send_task_to_user(message.chat.id)

@dp.message(Command("status"))
async def cmd_status(message: Message):
    await db.set_chat_id(message.chat.id)
    await send_status_view(message)

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
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    await db.set_chat_id(chat_id)
    await callback.answer()

    if action == "next":
        await db.reset_ignored_count()
        await send_task_to_user(chat_id)
    elif action == "status":
        await send_status_view(callback)
    elif action == "scan":
        await send_focus_menu(callback)
    elif action == "settings":
        await send_settings_menu(callback)


@dp.callback_query(F.data.startswith("task:"))
async def handle_task_actions(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]
    chat_id = callback.message.chat.id
    await db.set_chat_id(chat_id)

    if action == "stop_session":
        await callback.answer("Stopping session...")
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        await send_session_pdf_report(chat_id)
        return

    if len(parts) < 3:
        await callback.answer("Invalid task request.", show_alert=True)
        return

    task_id = int(parts[2])
    task = await db.get_task_by_id(task_id)

    if not task or (action != "verify" and task['status'] != 'pending'):
        await callback.answer("Task already processed or missing.", show_alert=True)
        return

    if action == "done":
        await callback.answer()
        await run_task_verification(callback, task)

    elif action == "verify":
        await callback.answer()
        await run_task_verification(callback, task)

    elif action == "apply":
        await callback.answer("Applying patches & checking syntax...")
        proj_dir = Path(config.CONTAINER_PROJECT_PATH)

        patches_to_apply = [{
            "file_path": task["file_path"],
            "search_block": (task.get("search_block") or "").strip(),
            "ready_code_fix": task["ready_code_fix"].strip()
        }]

        dep_raw = task.get("dependent_patches") or "[]"
        try:
            dep_patches = json.loads(dep_raw) if isinstance(dep_raw, str) else dep_raw
            patches_to_apply.extend(dep_patches)
        except Exception:
            pass

        applied_files = []
        for patch in patches_to_apply:
            clean_rel = patch["file_path"].lstrip("/\\")
            target_path = (proj_dir / clean_rel).resolve()
            if not target_path.is_relative_to(proj_dir.resolve()) or not target_path.exists():
                continue

            content = target_path.read_text(encoding="utf-8")
            s_block = patch["search_block"]
            r_fix = patch["ready_code_fix"]

            patched_content = apply_text_patch(content, s_block, r_fix)
            if patched_content is None:
                continue

            # Save original snapshot for atomic rollback
            target_path.write_text(patched_content, encoding="utf-8")
            applied_files.append((target_path, content))

            syntax_error = check_file_syntax(target_path)
            if syntax_error:
                for path_to_revert, orig_body in applied_files:
                    path_to_revert.write_text(orig_body, encoding="utf-8")
                await callback.message.answer(
                    f"❌ <b>Syntax Error in {html.escape(patch['file_path'])}! All changes rolled back.</b>\n"
                    f"<pre><code>{html.escape(syntax_error)}</code></pre>",
                    parse_mode="HTML"
                )
                return

        if applied_files:
            try:
                subprocess.run(["git", "config", "--global", "--add", "safe.directory", str(proj_dir)], check=False)
                has_user = subprocess.run(["git", "config", "user.name"], cwd=proj_dir, capture_output=True, text=True)
                if not has_user.stdout.strip():
                    subprocess.run(["git", "config", "user.name", "AI Project Mentor"], cwd=proj_dir, check=False)
                    subprocess.run(["git", "config", "user.email", "mentor@local"], cwd=proj_dir, check=False)
                for f in applied_files:
                    subprocess.run(["git", "add", str(f)], cwd=proj_dir, check=False)
                    rel_name = str(f.relative_to(proj_dir)) if f.is_relative_to(proj_dir) else f.name
                    scope = f.stem
                    is_primary = (rel_name == task.get("file_path", "").lstrip("/\\"))
                    action_detail = "apply" if is_primary else "update dependent"
                    f_commit_msg = f"refactor({scope}): {action_detail} {task['title'].lower()}"
                    subprocess.run(["git", "commit", "-m", f_commit_msg], cwd=proj_dir, check=False)
            except Exception as e:
                logging.debug(f"Git auto-commit failed: {e}")

            await callback.message.answer(
                f"⚙️ <b>Fix applied to {len(applied_files)} file(s) and committed!</b> Running AI verification...",
                parse_mode="HTML"
            )
            await run_task_verification(callback, task)
        else:
            await callback.message.answer(
                "⚠️ <b>Auto-Apply Failed:</b> Could not find the exact code block to replace.",
                parse_mode="HTML"
            )

    elif action == "reject":
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        status_msg = await callback.message.answer("🧠 Generating an alternative strategy...")

        try:
            code_dump = collect_project_context(config.CONTAINER_PROJECT_PATH)
            alt_task = await asyncio.to_thread(agent.generate_alternative_task, task, code_dump)
            await db.replace_with_alternative_task(task_id, alt_task)

            await status_msg.edit_text("✨ Alternative solution generated!")
            await send_task_to_user(chat_id)
        except Exception as e:
            logging.error(f"Failed to generate alternative task: {e}")
            await db.update_task_status(task_id, "skipped")
            await status_msg.edit_text("🔄 Task skipped. Moving to next backlog item...")
            await send_task_to_user(chat_id)


@dp.callback_query(F.data == "git:commit_push")
async def handle_git_commit_push(callback: CallbackQuery):
    await callback.answer("Checking modified files in Git...")
    proj_dir = config.CONTAINER_PROJECT_PATH

    try:
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", proj_dir], check=False)

        data_dir = Path(proj_dir) / "data"
        if data_dir.exists():
            gitkeep = data_dir / ".gitkeep"
            if not gitkeep.exists():
                gitkeep.touch()

        subprocess.run(["git", "add", "-A"], cwd=proj_dir, check=False)

        staged_proc = subprocess.run(
            ["git", "diff", "--cached", "HEAD"],
            cwd=proj_dir, capture_output=True, text=True, errors="replace"
        )
        staged_diff = staged_proc.stdout.strip()

        if not staged_diff:
            staged_proc_all = subprocess.run(
                ["git", "diff", "--cached"],
                cwd=proj_dir, capture_output=True, text=True, errors="replace"
            )
            staged_diff = staged_proc_all.stdout.strip()

        if not staged_diff:
            await callback.message.answer("ℹ️ <b>Working tree clean:</b> No new changes to commit.", parse_mode="HTML")
            return

        subprocess.run(["git", "reset"], cwd=proj_dir, check=False)
        status_proc = subprocess.run(["git", "status", "--porcelain"], cwd=proj_dir, capture_output=True, text=True)
        changed_entries = [line.strip().split(maxsplit=1)[-1] for line in status_proc.stdout.splitlines() if line.strip()]
        commit_summaries = []
        for file_rel in changed_entries:
            clean_file = file_rel.strip('"\'')
            diff_proc = subprocess.run(["git", "diff", "--", clean_file], cwd=proj_dir, capture_output=True, text=True)
            file_diff = diff_proc.stdout.strip()
            if not file_diff:
                f_obj = Path(proj_dir) / clean_file
                file_diff = f_obj.read_text(encoding="utf-8", errors="ignore")[:3000] if f_obj.is_file() else "new file"
            file_msg = await asyncio.to_thread(agent.generate_file_commit_message, clean_file, file_diff)
            subprocess.run(["git", "add", clean_file], cwd=proj_dir, check=False)
            commit_res = subprocess.run(["git", "commit", "-m", file_msg], cwd=proj_dir, capture_output=True, text=True)
            if commit_res.returncode == 0:
                commit_summaries.append(f"• {clean_file}: {file_msg}")
        if not commit_summaries:
            await callback.message.answer("ℹ️ <b>Git:</b> No files were committed.", parse_mode="HTML")
            return
        commit_msg = "\n".join(commit_summaries)

        push_res = subprocess.run(
            ["git", "push", "origin", "HEAD"],
            cwd=proj_dir, capture_output=True, text=True, errors="replace"
        )

        if push_res.returncode == 0:
            push_status = "and pushed to remote 🚀"
        else:
            err_msg = push_res.stderr.strip() or push_res.stdout.strip()
            if "fetch first" in err_msg or "rejected" in err_msg:
                push_status = "⚠️ <i>(push rejected: run 'git pull' on host to merge remote changes)</i>"
            elif "Could not read from remote" in err_msg or "Permission denied" in err_msg:
                push_status = "⚠️ <i>(push skipped: no SSH keys or Git credentials inside container)</i>"
            else:
                push_status = f"⚠️ <i>(push skipped: {html.escape(err_msg[:80])})</i>"

        await callback.message.answer(
            f"✅ <b>Committed successfully!</b>\n"
            f"Status: {push_status}\n\n"
            f"<b>Message:</b>\n<code>{html.escape(commit_msg)}</code>",
            parse_mode="HTML"
        )

    except Exception as e:
        logging.error(f"Git commit/push error: {e}")
        await callback.message.answer(f"❌ <b>Git Error:</b> {html.escape(str(e))}", parse_mode="HTML")

# Fallback handler AT THE VERY BOTTOM so the user NEVER gets silence
@dp.message(Command("focus"))
async def cmd_focus(message: Message):
    await db.set_chat_id(message.chat.id)
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        await run_codebase_scan(message.chat.id, focus_direction=parts[1].strip())
        return
    await send_focus_menu(message)

@dp.callback_query(F.data.startswith("focus_preset:"))
async def handle_focus_preset(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    focus_text = FOCUS_PRESETS.get(key, "")
    await callback.answer("🧭 Starting focused scan...")
    await run_codebase_scan(callback.message.chat.id, focus_direction=focus_text)


@dp.callback_query(F.data == "focus_custom:confirm")
async def handle_custom_focus_confirm(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    focus_text = pending_custom_focus.pop(chat_id, "")

    # Always acknowledge the callback first to prevent button infinite loading
    await callback.answer()

    if not focus_text:
        await callback.message.answer("Focus request expired, please type it again.")
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    try:
        await run_codebase_scan(chat_id, focus_direction=focus_text)
    except Exception as e:
        logging.error(f"Error during custom focused scan: {e}")
        await callback.message.answer(f"❌ Error during scan: {html.escape(str(e))}")

# Smart Fallback: turns any plain text message into a 1-click custom focus direction!
@dp.message(F.text)
async def fallback_message_handler(message: Message):
    await db.set_chat_id(message.chat.id)
    user_text = message.text.strip()

    if len(user_text) >= 5 and not user_text.startswith("/"):
        pending_custom_focus[message.chat.id] = user_text
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Scan with this Focus", callback_data="focus_custom:confirm")],
            [InlineKeyboardButton(text="🎯 Just get Next Task", callback_data="quick:next")]
        ])
        await message.answer(
            f"🧭 <b>New Focus Direction Detected:</b>\n"
            f"<i>\"{html.escape(user_text)}\"</i>\n\n"
            f"Would you like me to scan the codebase specifically for improvements in this direction?",
            parse_mode="HTML",
            reply_markup=kb
        )
        return

    await message.answer(
        "🤔 Unknown command. Use the <b>Menu</b> button or pick an action below:",
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
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "message_reaction"])

if __name__ == "__main__":
    asyncio.run(main())
