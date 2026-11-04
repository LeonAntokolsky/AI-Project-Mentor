import os
import re
import logging
from pathlib import Path


IGNORE_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".idea", ".vscode", "dist", "build", "migrations", "coverage",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "reports" 
}
IGNORE_FILES = {
    ".env", ".env.local", ".env.production", ".auth_token", "mentor.db",
    "mentor.db-wal", "mentor.db-shm", "package-lock.json",
    "poetry.lock", "yarn.lock", "pnpm-lock.yaml"
}
ALLOWED_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css",
    ".md", ".json", ".yml", ".yaml", ".sql", ".sh", ".dockerfile"
}

COMBINED_SECRET_PATTERN = re.compile(
    r'(?i)(api[_-]?key|secret|token|password|auth)\s*[:=]\s*["\']?[a-zA-Z0-9_\-\.:/+=]{12,}["\']?'
    r'|\b\d{8,10}:[a-zA-Z0-9_-]{35}\b'
    r'|ghp_[a-zA-Z0-9]{36}'
    r'|github_pat_[a-zA-Z0-9_]{82}'
    r'|\bAIza[0-9A-Za-z-_]{35}\b'
    r'|\bAKIA[0-9A-Z]{16}\b'
    r'|-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----'
)

MAX_FILE_SIZE_BYTES = 500_000

def scrub_secrets(text: str | None) -> str:
    if not text:
        return ""
    return COMBINED_SECRET_PATTERN.sub('<REDACTED_SECRET>', text)

def is_scannable_file(path: Path) -> bool:
    """Determines whether a file path qualifies for scanning context."""
    name = path.name
    if name in IGNORE_FILES or name.startswith(".env"):
        return False
    return path.suffix.lower() in ALLOWED_EXTENSIONS or name.lower() == "dockerfile"


def read_single_file(base_dir: str, relative_path: str, max_size: int = MAX_FILE_SIZE_BYTES) -> str:
    """Reads a single file safely with path traversal protection and size limits."""
    if not base_dir or not base_dir.strip():
        return ""
    if not relative_path or not relative_path.strip():
        return ""

    root_path = Path(base_dir).resolve()
    clean_rel = relative_path.lstrip("/\\")
    target_path = (root_path / clean_rel).resolve()

    if not target_path.is_relative_to(root_path):
        return "[Security Exception: Target path is outside base directory]"

    if not target_path.exists() or not target_path.is_file():
        return f"[File not found: {clean_rel}]"

    if target_path.stat().st_size > max_size:
        return f"[File size exceeds maximum limit of {max_size} bytes]"

    try:
        content = target_path.read_text(encoding="utf-8", errors="replace")
        return scrub_secrets(content)
    except Exception as e:
        return f"[Error reading file: {e}]"

def collect_project_context(base_dir: str, max_size: int = MAX_FILE_SIZE_BYTES) -> str:
    """Collects and aggregates readable source files from the project directory."""
    if not base_dir or not base_dir.strip():
        return ""

    root_path = Path(base_dir).resolve()
    if not root_path.exists() or not root_path.is_dir():
        return ""

    context_parts = []

    for root, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for file_name in files:
            file_path = Path(root) / file_name
            if not is_scannable_file(file_path):
                continue
            try:
                st = file_path.stat()
                if st.st_size > max_size:
                    continue
                rel_path_str = str(file_path.relative_to(root_path))
                content = file_path.read_text(encoding="utf-8", errors="replace")
                clean_content = scrub_secrets(content)
                context_parts.append(f"--- File: {rel_path_str} ---\n{clean_content}\n")
            except Exception:
                continue

    return "\n".join(context_parts)
