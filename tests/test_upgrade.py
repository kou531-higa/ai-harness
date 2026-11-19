import json
import shutil
from pathlib import Path

import pytest

from ai_harness.cli import main
from ai_harness.init import MANIFEST, run_init
from ai_harness.upgrade import NEW_SUFFIX, run_upgrade


@pytest.fixture()
def tdir(tmp_path: Path) -> Path:
    """小さなテンプレート（版1）"""
    t = tmp_path / "templates"
    for rel, text in {
        "core/CLAUDE.md": "規約 v1\n",
        "core/.claude/skills/review/SKILL.md": "review v1\n",
        "core/.claude/skills/old/SKILL.md": "old v1\n",
        "core/scripts/check.py": "print(1)\n",
        "layers/api/CLAUDE.md": "api v1\n",
    }.items():
        p = t / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return t


@pytest.fixture()
def target(tmp_path: Path) -> Path:
    d = tmp_path / "app"
    (d / "api").mkdir(parents=True)
    return d


def manifest(target: Path) -> dict:
    return json.loads((target / MANIFEST).read_text(encoding="utf-8"))


def test_initは入れたファイルの中身を覚える(tdir, target):
    run_init(target, git_hook=False, tdir=tdir)
    files = manifest(target)["files"]
    assert set(files) == {
        "CLAUDE.md",
        ".claude/skills/review/SKILL.md",
        ".claude/skills/old/SKILL.md",
        "scripts/check.py",
        "api/CLAUDE.md",
    }
    assert all(v.startswith("sha256:") for v in files.values())


def test_触っていないものは入れ替え_直したものは上書きせず隣に置く(tdir, target):
    run_init(target, git_hook=False, tdir=tdir)
    (target / "CLAUDE.md").write_text("規約 v1\nこのプロジェクトの1行\n", encoding="utf-8")  # 人が直した
    (target / "scripts" / "check.py").unlink()  # 人が消した
    # テンプレートの版2：review を更新、CLAUDE.md も更新、new を足し、old を消す
    (tdir / "core/.claude/skills/review/SKILL.md").write_text("review v2\n", encoding="utf-8")
    (tdir / "core/CLAUDE.md").write_text("規約 v2\n", encoding="utf-8")
    (tdir / "core/scripts/check.py").write_text("print(2)\n", encoding="utf-8")
    new = tdir / "core/.claude/skills/new/SKILL.md"
    new.parent.mkdir(parents=True)
    new.write_text("new v2\n", encoding="utf-8")
    shutil.rmtree(tdir / "core/.claude/skills/old")

    plan = run_upgrade(target, tdir=tdir)
    assert plan.updated == [".claude/skills/review/SKILL.md"]
    assert plan.added == [".claude/skills/new/SKILL.md"]
    assert plan.conflicts == ["CLAUDE.md"]
    assert plan.deleted_by_user == ["scripts/check.py"]
    assert plan.gone_from_template == [".claude/skills/old/SKILL.md"]
    assert (target / ".claude/skills/review/SKILL.md").read_text(encoding="utf-8") == "review v2\n"
    assert (target / "CLAUDE.md").read_text(encoding="utf-8") == "規約 v1\nこのプロジェクトの1行\n"  # 人の変更は残る
    assert (target / ("CLAUDE.md" + NEW_SUFFIX)).read_text(encoding="utf-8") == "規約 v2\n"
    assert not (target / "scripts" / "check.py").exists()  # 消したものは戻さない
    assert (target / ".claude/skills/old/SKILL.md").exists()  # テンプレートから消えても、勝手に消さない
    assert "*.harness-new" in (target / ".gitignore").read_text(encoding="utf-8")  # 置いたものをコミットしない

    # もう一度回しても、同じ結果（入れ替えたものは「変わらない」に、直したものは引き続き手で合わせる）
    again = run_upgrade(target, tdir=tdir)
    assert again.updated == [] and again.added == [] and again.conflicts == ["CLAUDE.md"]


def test_記録のない古い版で入れたものは_違えば人が直したものとして扱う(tdir, target):
    run_init(target, git_hook=False, tdir=tdir)
    m = manifest(target)
    del m["files"]
    (target / MANIFEST).write_text(json.dumps(m), encoding="utf-8")
    (tdir / "core/.claude/skills/review/SKILL.md").write_text("review v2\n", encoding="utf-8")
    plan = run_upgrade(target, tdir=tdir)
    assert plan.updated == [] and plan.conflicts == [".claude/skills/review/SKILL.md"]
    assert any("記録がない" in n for n in plan.notes)
    assert "files" in manifest(target)  # 次からは見分けられるように、同じだったものを記録する


def test_試しに実行は何も変えない(tdir, target):
    run_init(target, git_hook=False, tdir=tdir)
    before = (target / MANIFEST).read_text(encoding="utf-8")
    (tdir / "core/.claude/skills/review/SKILL.md").write_text("review v2\n", encoding="utf-8")
    plan = run_upgrade(target, dry_run=True, tdir=tdir)
    assert plan.updated == [".claude/skills/review/SKILL.md"]
    assert (target / ".claude/skills/review/SKILL.md").read_text(encoding="utf-8") == "review v1\n"
    assert (target / MANIFEST).read_text(encoding="utf-8") == before


def test_入れていない所では止める(tmp_path, capsys):
    assert main(["upgrade", str(tmp_path)]) == 2
    assert "harness init" in capsys.readouterr().err
