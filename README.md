# AI Project Mentor

This project provides an AI-powered mentor agent that scans your codebase, identifies potential improvements, vulnerabilities, and unfinished tasks, and delivers them as bite-sized micro-tasks via Telegram.

## Features
- Codebase analysis and task generation
- Telegram bot interface for task delivery
- Scheduled reminders and motivational messages
- Task tracking (pending, completed, skipped)

## Setup
1. Clone the repository.
2. Create a `.env` file based on `.env.example`.
3. Run `docker-compose up --build`.

## Usage
- Send `/start` to the Telegram bot to register.
- Use `/scan` to analyze your project.
- Use `/next` to get your next task.
