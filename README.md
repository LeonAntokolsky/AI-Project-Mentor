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

## 🛠️ Quick Start & Installation

### 1. Prerequisites
- [Docker & Docker Compose](https://docs.docker.com/get-docker/) installed.
- A [Google Gemini API Key](https://aistudio.google.com/app/apikey).
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather).

### 2. Clone and Configure
```bash
# Clone the repository
git clone https://github.com/your-username/ai-project-mentor.git
cd ai-project-mentor

# Create configuration file from template
cp .env.example .env 2>/dev/null || touch .env
```

### 3. Environment Variables Reference

Edit `.env` with your project parameters:

| Variable | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `GEMINI_API_KEY` | **Yes** | — | Google Gemini API secret key. |
| `TELEGRAM_BOT_TOKEN` | **Yes** | — | Telegram Bot token issued by @BotFather. |
| `TARGET_PROJECT_PATH` | No | `.` | Absolute or relative host path to the project you want the bot to audit. |
| `ALLOWED_USER_ID` | No | `0` | Telegram User ID allowed to control the bot (`0` allows any user who passes filesystem auth). |
| `PING_INTERVAL_HOURS` | No | `24` | Scheduled reminder interval (can also be changed dynamically in Telegram). |
| `GEMINI_MODEL_NAME` | No | `gemini-3.8-flash` | Gemini model identifier used for analysis and verification. |
| `CONTAINER_PROJECT_PATH`| No | `/workspace/project`| Container directory where target project is mounted. |
| `DB_PATH` | No | `/app/data/mentor.db`| SQLite database location. |

### 4. Launch Containerized Agent
```bash
# Build and start services in background
docker-compose up --build -d

# View streaming logs
docker-compose logs -f mentor-agent
```

> 💡 **Persistent Data**: SQLite database and generated PDF reports are automatically persisted in the host `./data` directory.

## 🤖 Telegram Bot Interface & Commands

### 🔐 Filesystem Authentication Handshake
To guarantee that only individuals with access to the host machine can trigger code edits:
1. Send `/start` to the bot.
2. When prompted that the bot is locked, retrieve the secret token created on the server:
   ```bash
   cat data/.auth_token
   ```
3. Reply in Telegram:
   ```text
   /auth YOUR_GENERATED_TOKEN
   ```
4. Access is granted instantly and saved in the database.

### 🎮 Bot Commands
| Command | Description |
| :--- | :--- |
| `/start` | Welcome guide, system status, and main action keyboard. |
| `/focus [goal]` | Run a focused codebase scan tailored to a custom goal (e.g. `/focus harden SQL queries`). |
| `/scan` | Open focus preset menu or run a comprehensive project audit. |
| `/next` | Receive the highest-priority pending micro-task from the backlog. |
| `/status` | View completed, pending, skipped task metrics and reminder schedules. |
| `/settings` | Switch reminder ping interval on the fly (1h, 6h, 12h, 24h, 48h). |
| `/motivate` | Co-Founder check-in: triggers an MVP rescue plan and 2 pivot ideas if you are stuck. |

### 🕹️ Interactive Task Controls
When a micro-task arrives in Telegram, the message contains the ROI rationale, estimated minutes, target file, and complete replacement snippet. Choose your action:
- **🛠 Apply Fix Auto**: Automatically patches target files, validates language syntax, and creates a local Git commit.
- **✅ Done Manually**: Tells the mentor you implemented the fix manually; the AI inspects the live file to verify completion.
- **🔄 Reject & Alt**: Rejects the suggested pattern and commands Gemini to devise an alternate solution.
- **🔍 Verify Fix with AI**: Runs automated verification of current file content against task requirements.
- **🛑 Stop Session & Get PDF Report**: Finalizes current session and delivers a formatted PDF audit document.
## 📦 Git Automation & One-Click Push

- **Automatic Safe Directory Registration**: The container configures `git config --global --add safe.directory` to prevent Docker user ID mismatch errors.
- **AI Conventional Commit Messages**: When you tap **📦 Commit & Push Changes**, the bot analyzes the staged `git diff` using Gemini to generate compliant conventional messages (e.g., `feat: implement redis token caching`).
- **SSH Remote Push**: By mounting `~/.ssh:/root/.ssh:ro`, the container securely pushes commits to remote repositories (GitHub, GitLab) using your existing host SSH keys.

---

## 📄 Automated PDF Session Reports

Every time you complete a refactoring session or tap **Stop Session & Get PDF Report**, the bot uses ReportLab to generate a clean A4 PDF document containing:
- Session focus and execution timestamp.
- Total number of fixes applied.
- Before / After diff blocks for each completed task.
- ROI and architectural reasoning for every fix.
- Embedded Cyrillic-compatible fonts (`DejaVuSans`) ensuring clean international character rendering.

Reports are saved to `data/reports/Report_<timestamp>.pdf` and sent directly to your Telegram chat.

---

## 💡 Solo-Developer Best Practices

1. **Work in Sprints**: Run `/focus` with a specific topic (e.g. *"Simplify state management"*), complete 3-4 micro-tasks, then tap **Stop Session & Get PDF Report**.
2. **Trust the Compiler**: If an auto-apply causes a syntax alert, the engine safely rolls back. Review the bot's compiler output and click **Reject & Alt**.
3. **Use Motivational Check-ins**: When motivation dips, run `/motivate` to get high-level product feedback and MVP feature reduction advice.

