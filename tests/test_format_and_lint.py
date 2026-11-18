"""本物の ruff などは使わず、PATH に偽のツールを置いて振る舞いを確かめる。"""

from __future__ import annotations

import os
import stat
from pathlib import Path

HOOK = "format-and-lint.py"


def fake_tool(bin_dir: Path, name: str, script: str) -> None:
    p = bin_dir / name
    p.write_text("#!/bin/sh\n" + script + "\n", encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)


def env_with(bin_dir: Path) -> dict:
    # 偽のツールだけが見えるようにする（本物の ruff が入っていても影響しない）
    return {"PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin"}


def write_payload(path: Path) -> dict:
    return {"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": str(path)}}


def test_指摘が残ればAIに返す(project, tmp_path_factory):
    bin_dir = tmp_path_factory.mktemp("bin")
    # check --fix は成功、check は失敗する ruff
    fake_tool(
        bin_dir,
        "ruff",
        'if [ "$1" = check ] && [ "$2" != --fix ]; then echo "F401 unused import"; exit 1; fi; exit 0',
    )
    f = project.write("api/app/x.py", "import os\n")
    r = project.run_hook(HOOK, write_payload(f), env_with(bin_dir))
    assert r.returncode == 2
    assert "F401" in r.stderr
    assert project.events()[-1]["reason"] == "lint"


def test_整形を実行し_指摘がなければ通す(project, tmp_path_factory):
    bin_dir = tmp_path_factory.mktemp("bin")
    calls = bin_dir / "calls.txt"
    fake_tool(bin_dir, "ruff", f'echo "$@" >> {calls}; exit 0')
    f = project.write("api/app/x.py", "x=1\n")
    r = project.run_hook(HOOK, write_payload(f), env_with(bin_dir))
    assert r.returncode == 0, r.stderr
    log = calls.read_text()
    assert "format api/app/x.py" in log
    assert "check --fix api/app/x.py" in log


def test_ツールがなければ飛ばす(project, tmp_path_factory):
    bin_dir = tmp_path_factory.mktemp("empty")
    f = project.write("api/app/x.py", "x=1\n")
    r = project.run_hook(HOOK, write_payload(f), env_with(bin_dir))
    assert r.returncode == 0


def test_対象外の拡張子は何もしない(project, tmp_path_factory):
    bin_dir = tmp_path_factory.mktemp("bin")
    fake_tool(bin_dir, "ruff", "exit 1")
    f = project.write("docs/memo.md", "# memo\n")
    r = project.run_hook(HOOK, write_payload(f), env_with(bin_dir))
    assert r.returncode == 0


def test_node_modulesのツールを優先する(project, tmp_path_factory):
    bin_dir = tmp_path_factory.mktemp("bin")
    fake_tool(bin_dir, "eslint", "exit 0")
    local_bin = project.path / "web" / "node_modules" / ".bin"
    local_bin.mkdir(parents=True)
    fake_tool(local_bin, "eslint", 'if [ "$1" != --fix ]; then echo "local eslint error"; exit 1; fi')
    f = project.write("web/app/page.tsx", "export default 1\n")
    r = project.run_hook(HOOK, write_payload(f), env_with(bin_dir))
    assert r.returncode == 2
    assert "local eslint error" in r.stderr
