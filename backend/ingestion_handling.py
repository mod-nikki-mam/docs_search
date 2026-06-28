import re
import os, shutil
from pathlib import Path
from git import Repo
from vecdb import VectorDB, run_query, create_db
import tempfile
import chunk

# https style https://github.com/user/repo or https://gitlab.com/user/repo etc.
RE_GIT_HTTPS = re.compile(
    r"^https?://"
    r"(?:[\w.-]+\.)?"  # optional subdomain
    r"(?:github|gitlab|bitbucket|gitea|codeberg)\.(?:com|org|io)"
    r"(?:/.*)?$",
    re.IGNORECASE,
)

# SSH scp eg: git@github.com:user/repo.git
RE_GIT_SSH_SCP = re.compile(
    r"^git@"
    r"(?:[\w.-]+\.)?"
    r"(?:github|gitlab|bitbucket|gitea|codeberg)\.(?:com|org|io)"
    r":[^/].*$",
    re.IGNORECASE,
)

# ssh URL style: ssh://git@github.com/user/repo.git
RE_GIT_SSH_URL = re.compile(
    r"^ssh://"
    r"(?:git@)?"
    r"(?:[\w.-]+\.)?"
    r"(?:github|gitlab|bitbucket|gitea|codeberg)\.(?:com|org|io)"
    r"(?:/.*)?$",
    re.IGNORECASE,
)


class Injestor:
    def __init__(self, url: str, local_db_path: str, local_docs_folder: str):
        self.url = url
        self.local_docs_folder = local_docs_folder or "./docs"
        self.local_db_folder = local_db_path or "./database"

    def _is_git_url(url: str) -> bool:
        return any(p.match(url) for p in (RE_GIT_HTTPS, RE_GIT_SSH_SCP, RE_GIT_SSH_URL))

    def injest_docs(self, url: str):
        docs_path: Path
        if self._is_git_url(url):
            result = self._get_git_docs(url)
            if result:
                docs_path = result
            else:
                return {
                    "success": False,
                    "error": "repo doesn't seem to have a docs folder",
                }
        else:
            return {
                "success": False,
                "error": "oops,this program doesnt integrate non-git links,that's a WIP",
            }
        db = create_db(url="", path=docs_path, cache_dir=self.local_db_folder)

    def _get_git_docs(self, url: str) -> Path | None:
        repo, tmp = self._clone_repo(url)

        try:
            docs = self._find_docs_folder(repo)
            if docs is None:
                return None

            path = self._download_docs(repo, docs)
            return path

        finally:
            tmp.cleanup()

    def _download_docs(self, repo: Repo, docs_dir: Path) -> Path:
        dest = self.local_docs_folder / repo.working_tree_dir.name

        repo.git.sparse_checkout("set", docs_dir.name)
        repo.git.checkout()

        shutil.move(docs_dir, dest)
        return dest

    def _find_docs_folder(repo: Repo) -> Path | None:
        root = Path(repo.working_tree_dir)

        for entry in root.iterdir():
            if entry.is_dir() and entry.name.lower() in {
                "docs",
                "documentation",
            }:
                return entry

        return None

    def _clone_repo(url: str) -> tuple[Repo, tempfile.TemporaryDirectory]:
        tmp_dir = tempfile.TemporaryDirectory()
        repo = Repo.clone_from(
            url,
            tmp_dir.name,
            depth=1,
            branch="main",
            single_branch=True,
            no_checkout=True,
        )
        return repo, tmp_dir
