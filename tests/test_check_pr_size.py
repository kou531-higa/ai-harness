from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "templates" / "core" / "scripts" / "check_pr_size.py"


class Repo:
    def __init__(self, path: Path):
        self.path = path

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.path, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    r = Repo(tmp_path)
    r.git("init", "-q", "-b", "main")
    r.git("config", "user.email", "test@example.com")
    r.git("config", "user.name", "test")
    (tmp_path / "README.md").write_text("init\n")
    r.git("add", "-A")
    r.git("commit", "-q", "-m", "init")
    r.git("switch", "-q", "-c", "feature")
    return r


def add_lines(repo: Repo, rel: str, n: int) -> None:
    p = repo.path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(f"line {i}\n" for i in range(n)))
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", f"add {rel}")


def run(repo: Repo, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--base", "main", *args],
        cwd=repo.path,
        capture_output=True,
        text=True,
        check=False,
    )


def test_上限以内なら通す(repo):
    add_lines(repo, "api/app/x.py", 400)
    r = run(repo)
    assert r.returncode == 0, r.stdout
    assert "変更行数: 400" in r.stdout


def test_上限を超えたら失敗し_大きいファイルを示す(repo):
    add_lines(repo, "api/app/x.py", 300)
    add_lines(repo, "web/app/y.tsx", 101)
    r = run(repo)
    assert r.returncode == 1
    assert "変更行数: 401" in r.stdout
    assert "api/app/x.py" in r.stdout
    assert "size-exception" in r.stdout


def test_例外ラベルがあれば通す(repo):
    add_lines(repo, "api/app/x.py", 500)
    r = run(repo, "--labels", "type:feature,size-exception")
    assert r.returncode == 0
    assert "ラベルがあるので通します" in r.stdout


def test_ロックファイルと生成物は数えない(repo):
    add_lines(repo, "uv.lock", 1000)
    add_lines(repo, "web/package-lock.json", 1000)
    add_lines(repo, "docs/metrics/index.html", 1000)
    add_lines(repo, "api/app/x.py", 10)
    r = run(repo)
    assert r.returncode == 0, r.stdout
    assert "変更行数: 10" in r.stdout
    assert "数えなかったファイル 3件" in r.stdout


def test_名前で生成物と分かるファイルは数えない(repo):
    add_lines(repo, "api/src/common/catalog/catalog.generated.ts", 1000)
    add_lines(repo, "db/procedures/fn_catalog.generated.sql", 1000)
    add_lines(repo, "batch/core/catalog_generated.py", 1000)
    add_lines(repo, "api/app/generated_note.py", 10)  # 名前の途中に generated があるだけのものは数える
    r = run(repo)
    assert r.returncode == 0, r.stdout
    assert "変更行数: 10" in r.stdout
    assert "数えなかったファイル 3件" in r.stdout


def test_除外パターンを追加できる(repo):
    add_lines(repo, "api/generated/client.py", 1000)
    r = run(repo, "--exclude", "api/generated/*")
    assert r.returncode == 0


def test_上限を変えられる(repo):
    add_lines(repo, "api/app/x.py", 150)
    assert run(repo, "--max", "100").returncode == 1


def test_削除行も数える(repo):
    add_lines(repo, "api/app/x.py", 300)
    repo.git("switch", "-q", "main")
    repo.git("merge", "-q", "feature")
    repo.git("switch", "-q", "-c", "remove")
    (repo.path / "api/app/x.py").unlink()
    add_lines(repo, "api/app/z.py", 200)
    r = run(repo)
    assert r.returncode == 1
    assert "変更行数: 500" in r.stdout
