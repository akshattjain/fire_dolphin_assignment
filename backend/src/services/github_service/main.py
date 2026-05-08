import logging
import os

from github import Github, GithubException

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


def _parse_owner_repo(github_url: str) -> tuple[str, str]:
    """Extract (owner, repo_name) from a GitHub URL."""
    parts = github_url.rstrip("/").split("/")
    owner = parts[-2]
    repo_name = parts[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    return owner, repo_name


def fetch_repo_metadata(github_url: str) -> dict:
    """Fetch repository metadata via the GitHub API."""
    owner, repo_name = _parse_owner_repo(github_url)
    g = Github(GITHUB_TOKEN) if GITHUB_TOKEN else Github()

    try:
        repo = g.get_repo(f"{owner}/{repo_name}")
        return {
            "owner": owner,
            "name": repo_name,
            "description": repo.description,
            "stars": repo.stargazers_count,
            "default_branch": repo.default_branch,
            "primary_language": repo.language,
        }
    except GithubException as exc:
        logger.warning("GitHub API call failed for %s/%s: %s", owner, repo_name, exc)
        return {
            "owner": owner,
            "name": repo_name,
            "description": None,
            "stars": 0,
            "default_branch": "main",
            "primary_language": None,
        }
