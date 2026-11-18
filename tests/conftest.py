"""フックのテスト用の共通部品。

一時ディレクトリに git リポジトリを作り、templates/core を展開して、
本物と同じようにフックを別プロセスで起動する（stdin に JSON を渡す）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "templates" / "core"


class Project:
    def __init__(self, path: Path):
        self.path = path

    def write(self, rel: str, content: str) -> Path:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.path, check=True, capture_output=True)

    def commit_all(self, message: str = "test") -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def run_hook(self, name: str, payload: dict, env_extra: dict | None = None) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.path)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, str(self.path / ".claude" / "hooks" / name)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=self.path,
            env=env,
            check=False,
        )

    def events(self) -> list:
        log = self.path / ".harness" / "events.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def project(tmp_path: Path) -> Project:
    shutil.copytree(CORE, tmp_path, dirs_exist_ok=True)
    p = Project(tmp_path)
    p.git("init", "-q", "-b", "main")
    p.git("config", "user.email", "test@example.com")
    p.git("config", "user.name", "test")
    p.commit_all("init")
    return p
