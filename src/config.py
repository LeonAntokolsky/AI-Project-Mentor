import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set.")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set.")

TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
PING_INTERVAL_HOURS = int(os.getenv("PING_INTERVAL_HOURS", "24"))

# Internal container paths
CONTAINER_PROJECT_PATH = os.getenv("CONTAINER_PROJECT_PATH", "/workspace/project")
DB_PATH = os.getenv("DB_PATH", "/app/data/mentor.db")
