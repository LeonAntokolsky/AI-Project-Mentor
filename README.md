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

## ✨ Core Capabilities

### 🧠 UB-Mode Engineering Discipline
The mentor operates under strict **UB-Mode (Make it Work -> Make it Right -> Follow Practice)** system instructions:
- **Laziness Protocol**: Single source of truth; smallest possible diff that cleanly solves the root problem.
- **Subtract Before You Add**: Strips accidental complexity before adding new logic.
- **Boundary & Type Discipline**: Zero placeholders or ellipses (`# rest of code...`). All suggested fixes are 100% executable.
- **Idempotency**: Running patches repeatedly yields identical deterministic states.

### 🛡️ Automated Patching with Syntax Guardrails
- **Exact Character Matching**: Replaces targeted code blocks without fuzzy misalignments or damaged indentation.
- **Pre-Commit Syntax Checks**: Runs `py_compile` on Python files and `json.loads` on JSON files prior to committing.
- **Auto-Rollback**: If a suggested fix introduces syntax errors, the original file is restored instantly, and the compiler traceback is sent to Telegram.
- **Atomic Dependent Patches**: Automatically applies accompanying updates across multiple files (imports, caller signatures, configs) in a single unified step.

### 🔒 Secret Scrubbing & Privacy by Design
Before source code context reaches the LLM, regex pattern filters strip:
- Telegram Bot Tokens, GitHub Personal Access Tokens (`ghp_*`, `github_pat_*`).
- API Keys, generic credentials, and private keys (`-----BEGIN PRIVATE KEY-----`).
- Environment files (`.env`, `.env.*`) and credentials caches are blocked by default.

### 🎯 Focused Audits & Strategy Alternates
- **1-Click Presets**: Security & Auth, Performance Optimization, Clean Code Refactoring, UX & Reliability, Unit Testing, Architecture.
- **Natural Language Focus**: Type any phrase directly in chat (e.g., *"Refactor database pool to asyncpg"*) to trigger a targeted scan.
- **Reject & Re-strategize**: Dislike a proposed fix? Hit **Reject & Alt** to have Gemini generate an alternative architectural pattern for the same issue.

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
