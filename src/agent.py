from __future__ import annotations
import config
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

DEFAULT_SKILL_PATH = Path(__file__).resolve().parent / "skills" / "SKILL.md"

class FilePatch(BaseModel):
    file_path: str = Field(description="Relative file path for this patch")
    search_block: str = Field(description="Exact substring of original code to replace")
    ready_code_fix: str = Field(description="Replacement code snippet")

class BacklogTask(BaseModel):
    category: Literal["vulnerability", "unfinished_todo", "improvement"] = Field(
        description="Task category: security vulnerability, unfinished feature/TODO, or architectural improvement"
    )
    file_path: str = Field(description="Relative file path associated with the primary task")
    title: str = Field(description="Short, actionable task title (3-7 words)")
    explanation: str = Field(description="Clear explanation of why this matters and the value it brings (max 3 sentences)")
    expected_profit: str = Field(
        description="Concrete ROI/benefit: why this approach is better and what measurable profit it brings"
    )
    search_block: str = Field(
        description="The EXACT lines of original code to be replaced. Must be an exact substring match to the file."
    )
    ready_code_fix: str = Field(
        description="The new code that will replace search_block."
    )
    dependent_patches: list[FilePatch] = Field(
        default_factory=list,
        description="Required accompanying edits in other files (imports, callers, signature updates, configs) so the project never breaks"
    )
    estimated_minutes: int = Field(description="Estimated time to implement (5 to 30 minutes)")

class ProjectAuditResult(BaseModel):
    project_summary: str = Field(description="Concise summary of the project's purpose and core value")
    tasks: list[BacklogTask] = Field(description="List of 5-10 bite-sized actionable tasks")

class TaskVerificationResult(BaseModel):
    is_completed: bool = Field(description="True if the issue is properly resolved in the current file content, False otherwise")
    feedback: str = Field(description="Short, constructive feedback explaining what is good or what is still missing (2-3 sentences)")

class MentorAgent:
    def __init__(self, api_key: str, skill_path: str | Path | None = None):
        self.client = genai.Client(api_key=api_key)
        self.model_name = config.GEMINI_MODEL_NAME
        resolved_path = Path(skill_path) if skill_path else DEFAULT_SKILL_PATH
        self.skill_instructions = self._load_skill(resolved_path)

    def _load_skill(self, path: Path) -> str:
        """Loads agent engineering principles (SKILL.md) to inject as system instructions."""
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="ignore")
        return "Follow clean, minimal, and idempotent coding practices."

    def analyze_codebase(self, codebase_dump: str, focus_direction: str = "") -> ProjectAuditResult:
        """Analyzes the codebase with an optional user-defined focus and calculates task ROI."""
        focus_instruction = (
            f"\nCRITICAL USER FOCUS DIRECTION: '{focus_direction}'\n"
            "Prioritize scanning the files specifically through this lens. "
            "Every generated task MUST directly advance this focus goal.\n"
            if focus_direction else
            "\nPerform a comprehensive audit covering security vulnerabilities, unfinished TODOs, and high-impact improvements.\n"
        )

        prompt = (
            "You are a senior Tech Lead and AI Co-founder. Your goal is to help a solo developer "
            "ship their project to production.\n"
            "STRICT SEARCH BLOCK RULE: 'search_block' MUST include full lines from start to end (including function definitions or full conditionals if modifying logic). Never cut off a search_block mid-statement."
            "Strictly apply your engineering skill principles (First Make it Work, Laziness Protocol, "
            "Subtract Before You Add, Boundary Discipline, Fix Root Causes) when proposing tasks.\n"
            f"{focus_instruction}\n"
            "Analyze the provided project source code:\n"
            "1. Summarize the core purpose of the project (project_summary).\n"
            "2. Break findings down into bite-sized micro-tasks taking 10-20 minutes each.\n"
            "3. For EVERY task, provide 'search_block' with the EXACT, VERBATIM original code to replace (must match characters byte-for-byte without ellipses or omissions), and 'ready_code_fix' with the exact replacement.\n"
            "4. Keep search_block minimal (3-15 lines) around the exact lines to modify so automated string substitution succeeds reliably.\n"
            "5. ATOMIC DEPENDENCY RULE: If modifying 'file_path' requires adjustments in OTHER files (such as imports, callers, or configs), include them in 'dependent_patches' with exact search_block and ready_code_fix so they can be auto-applied in the same step.\n\n"
            "Use line numbers from context to locate code, but DO NOT include line number prefixes inside search_block or ready_code_fix snippets.\n\n"
            f"PROJECT SOURCE CODE:\n{codebase_dump}"
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.skill_instructions,
                response_mime_type="application/json",
                response_schema=ProjectAuditResult,
                temperature=0.3,
            ),
        )
        return ProjectAuditResult.model_validate_json(response.text)

    def generate_alternative_task(self, task: dict, project_context: str = "") -> BacklogTask:
        """Generates an alternative architectural or implementation fix when the user rejects the first proposal."""
        prompt = (
            "You are a senior Tech Lead. The developer rejected your previous suggested fix for this task:\n\n"
            f"REJECTED TASK TITLE: {task.get('title')}\n"
            f"PRIMARY FILE: {task.get('file_path')}\n"
            f"PREVIOUS EXPLANATION: {task.get('explanation')}\n"
            f"REJECTED FIX SNIPPET:\n{task.get('ready_code_fix')}\n\n"
            "CRITICAL: You MUST solve the EXACT SAME core bug/issue described in REJECTED TASK TITLE, "
            "but using a different code pattern, library, or architectural approach. Do NOT switch to a different bug."
        )
        if project_context:
            prompt += f"\n\nPROJECT CONTEXT:\n{project_context[:40000]}"

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.skill_instructions,
                response_mime_type="application/json",
                response_schema=BacklogTask,
                temperature=0.4,
            ),
        )
        return BacklogTask.model_validate_json(response.text)

    def verify_task_fix(self, task: dict, current_file_content: str) -> TaskVerificationResult:
        """Verifies whether the user properly applied the requested fix in the target file."""
        prompt = (
            "You are verifying whether a developer completed the assigned micro-task.\n\n"
            f"ASSIGNED TASK TITLE: {task['title']}\n"
            f"TASK EXPLANATION: {task['explanation']}\n"
            f"SUGGESTED FIX WAS:\n{task['ready_code_fix']}\n\n"
            f"CURRENT CONTENT OF FILE '{task['file_path']}':\n{current_file_content}\n\n"
            "Evaluate the current file content:\n"
            "- Set is_completed = True if the root problem described in the task is solved (even if the developer's implementation slightly differs from the suggested snippet).\n"
            "- Set is_completed = False if the change has not been applied yet or has a critical flaw.\n"
            "- Provide brief, helpful feedback."
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.skill_instructions,
                response_mime_type="application/json",
                response_schema=TaskVerificationResult,
                temperature=0.2,
            ),
        )
        return TaskVerificationResult.model_validate_json(response.text)

    def generate_motivation_pivot(self, project_summary: str, ignored_count: int) -> str:
        """Generates a motivational message and product pivot ideas when the user ignores notifications."""
        prompt = (
            f"The developer is building the following project: '{project_summary}'. "
            f"They have ignored {ignored_count} consecutive reminders and stalled on development.\n"
            "Do NOT mention bugs and do NOT induce guilt. Act as an inspiring product co-founder:\n"
            "1. Remind them of the real-world impact: who will benefit once this tool is live.\n"
            "2. Suggest 2 fresh product pivot or monetization ideas.\n"
            "3. Propose an 'MVP Rescue Plan' (Subtract Before You Add): suggest what non-essential features to cut "
            "so they can deploy a working version in a single evening.\n"
            "Keep the tone encouraging, concise (under 2500 characters), well-structured, and use emojis."
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.skill_instructions,
                temperature=0.7,
            ),
        )
        return response.text

    def generate_commit_message(self, diff_text: str) -> str:
        """Generates a concise git commit message based on git diff."""
        prompt = (
            "Generate a concise, single-line Conventional Commit message (e.g., 'feat: ...', 'fix: ...', 'refactor: ...') "
            "summarizing ONLY the actual changes shown in this git diff. Return plain text without quotes or markdown:\n\n"
            f"{diff_text[:15000]}"
        )
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2),
        )
        lines = [line.strip() for line in (response.text or "").splitlines() if line.strip()]
        return lines[0] if lines else "chore: update codebase"
