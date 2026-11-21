"""Stop：変更があるのに検査が通っていなければ、終わらせない（check-done-on-stop.py）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HOOK = "check-done-on-stop.py"


@pytest.fixture
def counter(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("counter") / "runs.txt"


def env(cmd: str, on: str = "1") -> dict:
    return {"HARNESS_STOP_CHECK": on, "HARNESS_STOP_CHECK_CMD": cmd}


def counting(counter: Path, exit_code: int = 0) -> str:
    code = f"open({str(counter)!r}, 'a').write('x'); print('検査の出力'); raise SystemExit({exit_code})"
    return f'"{sys.executable}" -c "{code}"'


def runs(counter: Path) -> int:
    return len(counter.read_text()) if counter.exists() else 0


def test_既定では何もしない(project, counter):
    project.write("api/app.py", "x = 1\n")
    r = project.run_hook(HOOK, {}, env(counting(counter, 1), on=""))
    assert r.returncode == 0
    assert runs(counter) == 0


def test_変更がなければ検査を走らせない(project, counter):
    r = project.run_hook(HOOK, {}, env(counting(counter, 1)))
    assert r.returncode == 0
    assert runs(counter) == 0


def test_変更があって検査が落ちたら終わらせない(project, counter):
    project.write("api/app.py", "x = 1\n")
    r = project.run_hook(HOOK, {}, env(counting(counter, 1)))
    assert r.returncode == 2
    assert "検査の出力" in r.stderr
    assert project.events()[-1]["hook"] == "check-done-on-stop"


def test_通ったら記録し_同じ中身なら2回目は走らせない(project, counter):
    project.write("api/app.py", "x = 1\n")
    assert project.run_hook(HOOK, {}, env(counting(counter))).returncode == 0
    assert project.run_hook(HOOK, {}, env(counting(counter))).returncode == 0
    assert runs(counter) == 1
    project.write("api/app.py", "x = 2\n")
    assert project.run_hook(HOOK, {}, env(counting(counter))).returncode == 0
    assert runs(counter) == 2


def test_コミット済みの変更も既定の枝と比べて見る(project, counter):
    project.git("switch", "-q", "-c", "feat/1-a")
    project.write("api/app.py", "x = 1\n")
    project.commit_all("feat")
    r = project.run_hook(HOOK, {}, env(counting(counter, 1)))
    assert r.returncode == 2


def test_すでに1回止めた後は止めない(project, counter):
    project.write("api/app.py", "x = 1\n")
    r = project.run_hook(HOOK, {"stop_hook_active": True}, env(counting(counter, 1)))
    assert r.returncode == 0
    assert runs(counter) == 0


def test_時間切れも通っていない扱いにする(project):
    project.write("api/app.py", "x = 1\n")
    cmd = f'"{sys.executable}" -c "import time; time.sleep(5)"'
    r = project.run_hook(HOOK, {}, {**env(cmd), "HARNESS_STOP_CHECK_TIMEOUT": "1"})
    assert r.returncode == 2
    assert "時間" in r.stderr
