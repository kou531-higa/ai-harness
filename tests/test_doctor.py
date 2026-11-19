import subprocess
from pathlib import Path

from ai_harness.doctor import diagnose, render
from ai_harness.init import run_init


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True,
        capture_output=True,
    )


def no_gh(_args, _cwd):
    return None


def small_prs(_args, _cwd):
    return [{"number": i, "additions": 100, "deletions": 20, "mergedAt": "2026-11-18T00:00:00Z"} for i in range(5)]


def scores(caps):
    return {c.name: c.score for c in caps}


def test_何もないリポジトリは低く_測れない基準は点に入れない(tmp_path):
    git(tmp_path, "init", "-q")
    caps = diagnose(tmp_path, gh=no_gh)
    assert len(caps) == 7 and sum(c.score for c in caps) == 0
    small = next(c for c in caps if c.name == "小さく出している")
    assert [k.ok for k in small.criteria] == [False, None, None]  # PR が読めないものは「測れない」
    text = render(caps, tmp_path)
    assert "合計 0点／21点" in text and "測れない" in text and "→ harness init（CLAUDE.md の雛形）" in text


def test_ハーネスを入れると上がり_根拠が出る(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "api" / "src" / "common").mkdir(parents=True)
    specs = tmp_path / "docs" / "specs"
    specs.mkdir(parents=True)
    (specs / "SPEC-001-x.md").write_text(
        "---\nid: SPEC-001\nstatus: approved\n---\n# x\n\n## 目的\nx\n\n## 対象外\n- x\n\n## 合格基準\n- AC-001-1 Given a When b Then c\n",
        encoding="utf-8",
    )
    (tmp_path / "Makefile").write_text("check:\n\techo ok\n", encoding="utf-8")
    run_init(tmp_path)
    git(tmp_path, "add", "-A")
    for i in range(5):
        git(tmp_path, "commit", "-q", "--allow-empty", "-m", f"変更 {i} (#{i + 1})")
    caps = diagnose(tmp_path, gh=small_prs)
    s = scores(caps)
    assert s["AIの方針が明確で伝わっている"] == 3
    assert s["小さく出している"] == 3  # 中央値 120行
    assert s["利用者を見ている"] == 3
    assert s["社内プラットフォームの質"] == 3
    assert s["バージョン管理が強い"] >= 2
    text = render(caps, tmp_path)
    assert "中央値 120行（5件）" in text


def test_PRは診断するリポジトリの場所で読む(tmp_path):
    seen = []
    git(tmp_path, "init", "-q")
    diagnose(tmp_path, gh=lambda args, cwd: seen.append(cwd) or [])
    assert seen == [tmp_path.resolve()]


def test_大きいPRは点が下がる(tmp_path):
    git(tmp_path, "init", "-q")
    caps = diagnose(tmp_path, gh=lambda _a, _c: [{"number": 1, "additions": 900, "deletions": 0, "mergedAt": "x"}])
    small = next(c for c in caps if c.name == "小さく出している")
    assert [k.ok for k in small.criteria][1:] == [False, False]
