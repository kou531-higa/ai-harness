from __future__ import annotations

import os
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
    assert "本体 400行" in r.stdout


def test_上限を超えたら失敗し_大きいファイルを示す(repo):
    add_lines(repo, "api/app/x.py", 300)
    add_lines(repo, "web/app/y.tsx", 101)
    r = run(repo)
    assert r.returncode == 1
    assert "本体 401行" in r.stdout
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
    assert "本体 10行" in r.stdout
    assert "数えなかったファイル 3件" in r.stdout


def test_名前で生成物と分かるファイルは数えない(repo):
    add_lines(repo, "api/src/common/catalog/catalog.generated.ts", 1000)
    add_lines(repo, "db/procedures/fn_catalog.generated.sql", 1000)
    add_lines(repo, "batch/core/catalog_generated.py", 1000)
    add_lines(repo, "api/app/generated_note.py", 10)  # 名前の途中に generated があるだけのものは数える
    add_lines(repo, "batch/tests/test_catalog_generated.py", 20)  # テストは生成物の形でも数える
    r = run(repo)
    assert r.returncode == 0, r.stdout
    assert "本体 10行" in r.stdout and "テスト 20行" in r.stdout
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
    assert "本体 500行" in r.stdout


def test_テストは本体と別に数え_本体の上限に入れない(repo):
    add_lines(repo, "api/app/x.py", 300)
    add_lines(repo, "api/tests/test_x.py", 700)
    add_lines(repo, "web/src/x.test.tsx", 50)
    r = run(repo)
    assert r.returncode == 0, r.stdout
    assert "本体 300行（上限 400）" in r.stdout
    assert "テスト 750行（上限 800）" in r.stdout


def test_テストの上限を超えたら失敗する(repo):
    add_lines(repo, "api/app/x.py", 10)
    add_lines(repo, "e2e/tests/a.spec.ts", 801)
    r = run(repo)
    assert r.returncode == 1
    assert "テスト 801行" in r.stdout
    assert "e2e/tests/a.spec.ts" in r.stdout


def test_テストの上限を変えられる(repo):
    add_lines(repo, "api/tests/test_x.py", 300)
    assert run(repo, "--max-tests", "200").returncode == 1
    assert run(repo, "--max-tests", "300").returncode == 0


def test_上限は環境変数でも変えられる(repo):
    add_lines(repo, "api/app/x.py", 150)
    e = dict(os.environ, HARNESS_PR_MAX="100")
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", "main"], cwd=repo.path, capture_output=True, text=True, env=e
    )
    assert r.returncode == 1
    assert "上限 100" in r.stdout


def test_スナップショットはテストの名前でも数えない(repo):
    add_lines(repo, "web/src/__snapshots__/x.test.tsx.snap", 2000)
    add_lines(repo, "web/src/__snapshots__/y.test.tsx.txt", 2000)
    add_lines(repo, "web/src/x.test.tsx", 5)
    r = run(repo)
    assert r.returncode == 0, r.stdout
    assert "テスト 5行" in r.stdout
    assert "数えなかったファイル 2件" in r.stdout


@pytest.mark.parametrize(
    "path",
    [
        "api/tests/helper.py",
        "batch/tests/conftest.py",
        "web/src/__tests__/util.ts",
        "e2e/pages/list.ts",
        "api/test/app.e2e.ts",
    ],
)
def test_テストの場所にあるものはテストとして数える(repo, path):
    add_lines(repo, path, 20)
    r = run(repo)
    assert "テスト 20行" in r.stdout, r.stdout
