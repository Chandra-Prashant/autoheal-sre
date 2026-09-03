import subprocess
import time

from github import Auth, Github

from app.config import GITHUB_TOKEN


def open_pr(repo_path: str, repo_full_name: str, title: str, body: str, base: str = "main") -> str:
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN not set")

    branch = f"autoheal/fix-{int(time.time())}"
    subprocess.run(["git", "checkout", "-b", branch], cwd=repo_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", title], cwd=repo_path, check=True)
    subprocess.run(["git", "push", "origin", branch], cwd=repo_path, check=True)

    gh = Github(auth=Auth.Token(GITHUB_TOKEN))
    repo = gh.get_repo(repo_full_name)
    pr = repo.create_pull(title=title, body=body, head=branch, base=base)
    return pr.html_url
