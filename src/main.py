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
from typing import Dict
from datetime import datetime, timedelta
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, BufferedInputFile, BotCommand,
    MessageReactionUpdated, ReactionTypeEmoji
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google.genai.errors import APIError
from scanner import collect_project_context, read_single_file
from agent import MentorAgent
from database import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
db = Database(config.DB_PATH)
agent = MentorAgent(api_key=config.GEMINI_API_KEY)
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

def apply_text_patch(content: str, search_block: str, replacement: str) -> str | None:
    """Pure function to safely apply search-and-replace with newline normalization."""
    norm_content = content.replace("\r\n", "\n")
    norm_search = search_block.replace("\r\n", "\n")
    norm_replace = replacement.replace("\r\n", "\n")

    target_match = norm_search if norm_search and norm_search in norm_content else (
        norm_search.strip() if norm_search and norm_search.strip() in norm_content else None
    )
    if not target_match:
        return None

    actual_fix = norm_replace if target_match == norm_search else norm_replace.strip()
    return norm_content.replace(target_match, actual_fix, 1)

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
    """Builds interactive buttons for a newly received task."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛠 Apply Fix Auto", callback_data=f"task:apply:{task_id}")],
        [
            InlineKeyboardButton(text="✅ Done Manually", callback_data=f"task:done:{task_id}"),
            InlineKeyboardButton(text="🔄 Reject & Alt", callback_data=f"task:reject:{task_id}")
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
        code_dump = collect_project_context(config.CONTAINER_PROJECT_PATH)
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
        await bot.send_message(
            chat_id,
            "🎉 You've completed all tasks in the current backlog!\n"
            "Run /scan to generate new tasks or /motivate for a co-founder check-in.",
            reply_markup=get_quick_actions_keyboard()
        )
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
    stats = await db.get_stats()
    await message.answer(
        format_status_message(stats),
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
            format_status_message(stats),
            parse_mode="HTML",
            reply_markup=get_quick_actions_keyboard()
        )
    elif action == "scan":
        await callback.message.answer(
            "🧭 <b>Focused Codebase Audit</b>\n\n"
            "Choose a focus preset below, or simply <b>type any custom goal in the chat</b>:",
            parse_mode="HTML",
            reply_markup=get_focus_presets_keyboard()
        )
    elif action == "settings":
        await send_settings_menu(callback)


@dp.callback_query(F.data.startswith("task:"))
async def handle_task_actions(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]
    task_id = int(parts[2])
    chat_id = callback.message.chat.id
    await db.set_chat_id(chat_id)

    task = await db.get_task_by_id(task_id)
    if not task or (action != "verify" and task['status'] != 'pending'):
        await callback.answer("Task already processed or missing.", show_alert=True)
        return

    if action == "done":
        await db.update_task_status(task_id, "completed")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Marked as done!")

        kb_post_done = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Verify Fix with AI", callback_data=f"task:verify:{task_id}")],
            [InlineKeyboardButton(text="🎯 Next Task", callback_data="quick:next")]
        ])
        await callback.message.answer(
            f"✅ <b>Task marked as done manually!</b>\n"
            f"File: <code>{html.escape(task['file_path'])}</code>\n\n"
            f"If you edited the code yourself, click below to verify syntax & logic with AI:",
            parse_mode="HTML",
            reply_markup=kb_post_done
        )

    elif action == "verify":
        await callback.answer("🔍 Inspecting code changes...")
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

            kb_next = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎯 Next Task", callback_data="quick:next")]
            ])
            await status_msg.edit_text(
                f"✅ <b>Verification Passed!</b>\n\n{feedback_escaped}\n\n"
                f"Task verified! Click below to move forward 🚀",
                parse_mode="HTML",
                reply_markup=kb_next
            )
        else:
            await db.reset_ignored_count()
            kb_reverify = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Verify Fix Again", callback_data=f"task:verify:{task_id}")],
                [InlineKeyboardButton(text="🎯 Next Task", callback_data="quick:next")]
            ])
            await status_msg.edit_text(
                f"⚠️ <b>Not quite ready yet!</b>\n\n{feedback_escaped}\n\n"
                f"<i>Fix the file and click below to re-verify:</i>",
                parse_mode="HTML",
                reply_markup=kb_reverify
            )


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

            new_content = apply_text_patch(content, s_block, r_fix)
            if new_content is None:
                continue
            target_path.write_text(new_content, encoding="utf-8")
            applied_files.append(target_path)

            syntax_error = None
            if target_path.suffix == ".py":
                try:
                    py_compile.compile(target_path, doraise=True)
                except py_compile.PyCompileError as e:
                    syntax_error = str(e)
            elif target_path.suffix == ".json":
                try:
                    json.loads(target_path.read_text(encoding="utf-8"))
                except Exception as e:
                    syntax_error = str(e)

            if syntax_error:
                target_path.write_text(content, encoding="utf-8")
                await callback.message.answer(
                    f"❌ <b>Syntax Error in {html.escape(patch['file_path'])}! Rollback applied.</b>\n"
                    f"<pre><code>{html.escape(syntax_error)}</code></pre>",
                    parse_mode="HTML"
                )
                return

        if applied_files:
            try:
                for f in applied_files:
                    subprocess.run(["git", "add", str(f)], cwd=proj_dir, check=False)
                commit_msg = f"refactor: {task['title'].lower()}"
                subprocess.run(["git", "commit", "-m", commit_msg], cwd=proj_dir, check=False)
            except Exception as e:
                logging.debug(f"Git auto-commit failed: {e}")

            await db.update_task_status(task_id, "completed")
            await callback.message.edit_reply_markup(reply_markup=None)

            kb_applied = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Verify Fix with AI", callback_data=f"task:verify:{task_id}")],
                [InlineKeyboardButton(text="🎯 Next Task", callback_data="quick:next")]
            ])
            await callback.message.answer(
                f"✅ <b>Fix applied to {len(applied_files)} file(s) and committed!</b>\n\n"
                f"Click <b>🔍 Verify Fix with AI</b> if you want to inspect implementation consistency:",
                parse_mode="HTML",
                reply_markup=kb_applied
            )
        else:
            await callback.message.answer(
                "⚠️ <b>Auto-Apply Failed:</b> Could not find the exact code block to replace.",
                parse_mode="HTML"
            )


    elif action == "reject":
        await callback.message.edit_reply_markup(reply_markup=None)
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
@dp.message(Command("focus"))
async def cmd_focus(message: Message):
    await db.set_chat_id(message.chat.id)
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        await run_codebase_scan(message.chat.id, focus_direction=parts[1].strip())
        return

    await message.answer(
        "🧭 <b>Focused Codebase Audit</b>\n\n"
        "Choose a focus preset below, or simply <b>type any custom goal in the chat</b> "
        "(e.g., <i>'Add rate limiting and protect database calls'</i>):",
        parse_mode="HTML",
        reply_markup=get_focus_presets_keyboard()
    )

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
