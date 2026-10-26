from typing import Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

class BacklogTask(BaseModel):
    category: Literal["vulnerability", "unfinished_todo", "improvement"] = Field(
        description="Task category: security vulnerability, unfinished feature/TODO, or architectural improvement"
    )
    file_path: str = Field(description="Relative file path associated with the task")
    title: str = Field(description="Short, actionable task title (3-7 words)")
    explanation: str = Field(description="Clear explanation of why this matters and the value it brings (max 3 sentences)")
    ready_code_fix: str = Field(
        description="Concise, ready-to-use code snippet or function to resolve the issue (strictly under 35 lines, do NOT dump the entire file)"
    )
    estimated_minutes: int = Field(description="Estimated time to implement (5 to 30 minutes)")

class ProjectAuditResult(BaseModel):
    project_summary: str = Field(description="Concise summary of the project's purpose and core value")
    tasks: list[BacklogTask] = Field(description="List of 5-10 bite-sized actionable tasks")

class MentorAgent:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-2.5-flash"

    def analyze_codebase(self, codebase_dump: str) -> ProjectAuditResult:
        """Analyzes the codebase and generates a structured backlog of micro-tasks."""
        prompt = (
            "You are a senior Tech Lead and AI Co-founder. Your goal is to help a solo developer "
            "maintain momentum and ship their pet project to production.\n"
            "Analyze the provided project source code:\n"
            "1. Summarize the core purpose and value proposition of the project (project_summary).\n"
            "2. Identify real security vulnerabilities (vulnerability), unfinished code/TODOs/stubs (unfinished_todo), "
            "and high-impact improvements (improvement).\n"
            "3. Break findings down into bite-sized micro-tasks taking 10-20 minutes each to reduce cognitive friction.\n"
            "4. Provide a concrete, copy-pasteable code snippet (ready_code_fix) for every task. "
            "IMPORTANT: Keep ready_code_fix concise (under 35 lines / 1500 characters). Show only the changed function or block, never the whole file.\n\n"
            f"PROJECT SOURCE CODE:\n{codebase_dump}"
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ProjectAuditResult,
                temperature=0.3,
            ),
        )
        return ProjectAuditResult.model_validate_json(response.text)

    def generate_motivation_pivot(self, project_summary: str, ignored_count: int) -> str:
        """Generates a motivational message and product pivot ideas when the user ignores notifications."""
        prompt = (
            f"The developer is building the following project: '{project_summary}'. "
            f"They have ignored {ignored_count} consecutive reminders and stalled on development.\n"
            "Do NOT mention bugs and do NOT induce guilt. Act as an inspiring product co-founder:\n"
            "1. Remind them of the real-world impact: who will benefit once this tool is live.\n"
            "2. Suggest 2 fresh product pivot or monetization ideas that could make the project even more exciting.\n"
            "3. Propose an 'MVP Rescue Plan': suggest what non-essential features to cut right now "
            "so they can deploy a working version in a single evening.\n"
            "Keep the tone encouraging, concise (under 2500 characters), well-structured, and use emojis."
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7),
        )
        return response.text
