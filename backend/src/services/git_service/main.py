import os
import shutil
import tempfile
from pathlib import Path

from git import Repo

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
}

SKIP_DIRS: set[str] = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".next",
    "vendor",
    "target",
    ".idea",
    ".vscode",
    "coverage",
    ".pytest_cache",
    "*.egg-info",
}

MAX_FILE_SIZE_BYTES = 500_000  # skip files larger than 500 KB


def get_temp_dir(repo_id: str) -> str:
    return f"/tmp/repo_{repo_id}"


def clone_repository(github_url: str, repo_id: str) -> str:
    """Clone a GitHub repo (shallow) and return the temp directory path."""
    temp_dir = get_temp_dir(repo_id)
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    Repo.clone_from(github_url, temp_dir, depth=1)
    return temp_dir


def get_code_files(temp_dir: str) -> list[dict]:
    """Walk temp_dir and return metadata dicts for all supported code files."""
    files: list[dict] = []
    base = Path(temp_dir)

    for path in base.rglob("*"):
        if not path.is_file():
            continue

        parts = path.relative_to(base).parts
        if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in parts):
            continue

        ext = path.suffix.lower()
        language = SUPPORTED_EXTENSIONS.get(ext)
        if language is None:
            continue

        size = path.stat().st_size
        if size > MAX_FILE_SIZE_BYTES:
            continue

        files.append(
            {
                "file_path": str(path.relative_to(base)),
                "language": language,
                "abs_path": str(path),
                "file_size": size,
            }
        )

    return files


def cleanup_temp_dir(repo_id: str) -> None:
    temp_dir = get_temp_dir(repo_id)
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)
