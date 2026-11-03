# AI Project Mentor

This project provides an AI-powered mentor agent that scans your codebase, identifies potential improvements, vulnerabilities, and unfinished tasks, and delivers them as bite-sized micro-tasks via Telegram.

## Features
- Codebase analysis and task generation
- Telegram bot interface for task delivery
- Scheduled reminders and motivational messages
- Task tracking (pending, completed, skipped)

## Setup
1. Clone the repository: `git clone <repo-url> && cd ai-project-mentor`
2. Create a `.env` file with `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, and optional `TARGET_PROJECT_PATH`.
3. Verify `.env` is listed in your `.gitignore` before committing.
4. Run `docker-compose up --build`.

## Usage
- Send `/start` to the Telegram bot to register.
- Use `/scan` or `/focus` to analyze your project and find improvements.
- Use `/next` to receive and apply micro-tasks.
- Tap **Commit & Push Changes** to record fixes to your Git history.
