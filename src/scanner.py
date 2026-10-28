import os
import re
import logging
from pathlib import Path


IGNORE_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".idea", ".vscode", "dist", "build", "migrations", "coverage"
}
IGNORE_FILES = {
    ".env", ".env.local", ".env.production", "package-lock.json",
    "poetry.lock", "yarn.lock", "pnpm-lock.yaml"
}
ALLOWED_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css",
    ".md", ".json", ".yml", ".yaml", ".sql", ".sh", ".dockerfile"
}

SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|secret|token|password|auth)\s*[:=]\s*["\']?[a-zA-Z0-9_\-\.:/+=]{12,}["\']?'),
    re.compile(r'\b\d{8,10}:[a-zA-Z0-9_-]{35}\b'),
]

def scrub_secrets(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub('<REDACTED_SECRET>', text)
    return text

def read_single_file(project_dir: str, rel_file_path: str) -> str:
    base_path = Path(project_dir).resolve()
    clean_rel = rel_file_path.lstrip("/\\")
    target_path = (base_path / clean_rel).resolve()
    if not target_path.is_relative_to(base_path):
        raise ValueError("Invalid file path: outside of project directory.")
    if not target_path.is_file():
        raise FileNotFoundError(f"File '{rel_file_path}' not found in project.")
    return scrub_secrets(target_path.read_text(encoding="utf-8", errors="ignore"))

def collect_project_context(project_dir: str, max_chars: int = 300_000) -> str:
    """Traverses the project directory and packs allowed source files into a single string."""
    base_path = Path(project_dir)
    if not base_path.exists():
        raise FileNotFoundError(f"Target project directory '{project_dir}' does not exist.")

    collected_parts = []
    total_chars = 0

    for root, dirs, files in os.walk(base_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

        for file in files:
            if file in IGNORE_FILES or file.startswith(".env"):
                continue

            file_path = Path(root) / file
            if file_path.suffix.lower() not in ALLOWED_EXTENSIONS and file.lower() != "dockerfile":
                continue

            rel_path = file_path.relative_to(base_path)
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                content = scrub_secrets(content)
                snippet = f"\n=== FILE: {rel_path} ===\n{content}\n"

                if total_chars + len(snippet) > max_chars:
                    collected_parts.append("\n[...Context limit reached, remaining files truncated...]")
                    return "".join(collected_parts)

                collected_parts.append(snippet)
                total_chars += len(snippet)
            except Exception as e:
                print(f"Error reading file {rel_path}: {e}")

    if not collected_parts:
        return "Project directory is empty or contains no supported source files."

    return "".join(collected_parts)
