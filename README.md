<div align="center">

# 🚀 AI Project Mentor

**Your Autonomous AI Tech Lead & Engineering Co-Founder in Telegram**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker Compose](https://img.shields.io/badge/docker--compose-ready-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![Google Gemini API](https://img.shields.io/badge/AI-Google%20Gemini-8E75C2.svg)](https://ai.google.dev/)
[![Aiogram 3](https://img.shields.io/badge/telegram-aiogram%203-2CA5E0.svg?logo=telegram&logoColor=white)](https://github.com/aiogram/aiogram)
[![Code Style: UB-Mode](https://img.shields.io/badge/discipline-UB--Mode-green.svg)](#-the-ub-mode-discipline)

<p align="center">
  Transform overwhelming tech debt and feature backlogs into atomic, verified, 15-minute micro-tasks with automated syntax checks, one-click Git commits, and executive PDF audit reports.
</p>

</div>

---

## 🗺️ System Architecture & Workflow

```text
+-----------------------------------------------------------------------------------+
|                                 HOST ENVIRONMENT                                  |
|  +------------------------+   Volume Mount   +---------------------------------+  |
|  | Target Project Repo    |<================>| /workspace/project (read/write) |  |
|  +------------------------+                  +---------------------------------+  |
+-------------------------------------------------------------|---------------------+
                                                              | (Scanner + Redaction)
                                                              v
+-----------------------------------------------------------------------------------+
|                         AI PROJECT MENTOR CONTAINER                               |
|                                                                                   |
|  [Scanner & Secret Sanitizer] ---> Removes tokens, passwords, and private keys    |
|                 |                                                                 |
|                 v                                                                 |
|       [Gemini Mentor Agent] <==> Prompted with strict UB-Mode Engineering Skill   |
|                 |                                                                 |
|                 v (Search & Replace Blocks, ROI Analysis, Minutes Estimate)       |
|       [SQLite Backlog (WAL)] ===> Persistent storage for active session tasks      |
|                 |                                                                 |
|                 v                                                                 |
|      [Patch Application Engine] ---> py_compile & JSON syntax pre-validation     |
|                 |                    (Auto-Rollback on compiler failure)          |
|                 v                                                                 |
|     [Conventional Git Commit] ===> Auto safe.directory, git add & git commit      |
|                 |                                                                 |
|                 v                                                                 |
|     [ReportLab PDF Engine] ====> Generates styled, Cyrillic-ready session reports |
+-------------------------------------------------------------|---------------------+
                                                              | (Async Polling & Push)
                                                              v
+-----------------------------------------------------------------------------------+
|                               TELEGRAM USER INTERFACE                             |
|   - Interactive Tasks (Apply Auto / Done Manually / Reject & Alt Solution)        |
|   - Momentum Reminders & Co-Founder Motivational Pivot Mode                       |
|   - Filesystem Token Security Handshake (/auth <token>)                           |
+-----------------------------------------------------------------------------------+
```

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
