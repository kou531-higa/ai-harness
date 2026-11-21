"""PR の本文や仕様が参照する DEC-番号の判断記録が、docs/decisions/ にあるか（check_dec_refs.py）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "templates" / "core" / "scripts" / "check_dec_refs.py"


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def run(root: Path, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=root, input=stdin, capture_output=True, text=True, check=False
    )


def test_仕様が参照するDECがあれば通す(tmp_path):
    write(tmp_path, "docs/decisions/DEC-001-cancel-window.md", "---\nid: DEC-001\n---\n")
    write(tmp_path, "docs/specs/SPEC-001.md", "取り消しは DEC-001 による\n")
    r = run(tmp_path, "docs/specs")
    assert r.returncode == 0, r.stdout


def test_ないDECを参照していたら止める(tmp_path):
    write(tmp_path, "docs/decisions/DEC-001-a.md", "---\nid: DEC-001\n---\n")
    write(tmp_path, "docs/specs/SPEC-001.md", "x\n在庫の引き当ては DEC-012 による\n")
    r = run(tmp_path, "docs/specs")
    assert r.returncode == 1
    assert "DEC-012" in r.stdout and "SPEC-001.md:2" in r.stdout


def test_PRの本文も見る(tmp_path):
    write(tmp_path, "docs/decisions/DEC-002.md", "---\nid: DEC-002\n---\n")
    body = tmp_path / "body.md"
    body.write_text("## 関係する DEC\n- DEC-002\n- DEC-003\n", encoding="utf-8")
    r = run(tmp_path, "--body-file", str(body))
    assert r.returncode == 1
    assert "DEC-003" in r.stdout
    assert "見つからない DEC：1件" in r.stdout


def test_frontmatterのidでも見つける(tmp_path):
    write(tmp_path, "docs/decisions/order-cancel.md", "---\nid: DEC-004\nstatus: decided\n---\n")
    r = run(tmp_path, "-", stdin="DEC-004 に従う\n")
    assert r.returncode == 0, r.stdout


def test_型のファイルとDEC_000は数えない(tmp_path):
    write(tmp_path, "docs/decisions/_template.md", "id: DEC-000\n次は DEC-999 を見る\n")
    write(tmp_path, "docs/specs/SPEC-001.md", "例：DEC-000\n")
    r = run(tmp_path, "docs/specs", "docs/decisions")
    assert r.returncode == 0, r.stdout


def test_PRの本文のコードの中の番号は例として数えない(tmp_path):
    write(tmp_path, "docs/decisions/DEC-002.md", "---\nid: DEC-002\n---\n")
    body = "DEC-002 による\n例：`DEC-901` のように書く\n```\nsupersedes: DEC-030\n```\nDEC-044 も見る\n"
    write(tmp_path, "pr.md", body)
    r = run(tmp_path, "--body-file", "pr.md")
    assert r.returncode == 1
    assert "DEC-044" in r.stdout and "PR の本文:6" in r.stdout
    assert "DEC-901" not in r.stdout and "DEC-030" not in r.stdout


def test_仕様ではコードの中の番号も参照として数える(tmp_path):
    write(tmp_path, "docs/specs/SPEC-001.md", "取り消しは `DEC-012` による\n")
    assert run(tmp_path, "docs/specs").returncode == 1
