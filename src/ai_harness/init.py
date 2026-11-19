"""harness init：テンプレートを導入先のリポジトリに展開する。

- 既にあるファイルは上書きしない（--force のときだけ上書きする）
- 層（web・api・batch・db・e2e）は、導入先にそのディレクトリがあるものだけ入れる
- git の pre-push フックを入れる（main への直接の push を止める）
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import __version__

LAYERS = ["web", "api", "batch", "db", "e2e"]
IGNORE_NAMES = {"__pycache__", ".DS_Store"}
GITIGNORE_LINES = [".harness/", ".claude/settings.local.json", "CLAUDE.local.md", "*.harness-new"]
MANIFEST = ".claude/harness.json"
PRE_PUSH_SRC = "scripts/git-hooks/pre-push"


def templates_dir() -> Path:
    """配布物の中のテンプレート。開発中はリポジトリ直下の templates を使う。"""
    here = Path(__file__).resolve().parent
    for cand in (here / "templates", here.parents[1] / "templates"):
        if (cand / "core").is_dir():
            return cand
    raise FileNotFoundError("テンプレートが見つかりません")


@dataclass
class Plan:
    created: List[str] = field(default_factory=list)
    overwritten: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _files(src: Path) -> List[Path]:
    out = []
    for p in sorted(src.rglob("*")):
        if p.is_file() and not (set(p.relative_to(src).parts) & IGNORE_NAMES) and p.suffix != ".pyc":
            out.append(p)
    return out


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def template_files(tdir: Path, layers: List[str]) -> Dict[str, Path]:
    """導入先での置き場所 → テンプレートのファイル"""
    core = tdir / "core"
    out = {src.relative_to(core).as_posix(): src for src in _files(core)}
    for name in layers:
        out[f"{name}/CLAUDE.md"] = tdir / "layers" / name / "CLAUDE.md"
    return out


def detect_layers(target: Path) -> List[str]:
    return [name for name in LAYERS if (target / name).is_dir()]


def _copy(src: Path, dst: Path, rel: str, plan: Plan, force: bool, dry_run: bool) -> None:
    if dst.exists():
        if not force:
            plan.skipped.append(rel)
            return
        if dst.read_bytes() == src.read_bytes():
            plan.skipped.append(rel)
            return
        plan.overwritten.append(rel)
    else:
        plan.created.append(rel)
    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _merge_gitignore(target: Path, plan: Plan, dry_run: bool) -> None:
    path = target / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    have = {line.strip() for line in text.splitlines()}
    missing = [line for line in GITIGNORE_LINES if line not in have]
    if not missing:
        return
    plan.notes.append(".gitignore に追加：" + "、".join(missing))
    if not dry_run:
        prefix = "" if not text or text.endswith("\n") else "\n"
        path.write_text(text + prefix + "\n# ai-harness\n" + "\n".join(missing) + "\n", encoding="utf-8")


def _git_hooks_dir(target: Path) -> Optional[Path]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"], cwd=target, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    p = Path(out)
    return p if p.is_absolute() else target / p


def _install_pre_push(target: Path, plan: Plan, force: bool, dry_run: bool) -> None:
    hooks = _git_hooks_dir(target)
    if hooks is None:
        plan.notes.append("git のリポジトリではないので、pre-push フックは入れていません")
        return
    dst = hooks / "pre-push"
    src = target / PRE_PUSH_SRC
    if dst.exists() and not force:
        if src.exists() and dst.read_bytes() == src.read_bytes():
            return
        plan.notes.append(
            f"pre-push フックが既にあるので入れていません（{dst}）。{PRE_PUSH_SRC} を呼ぶようにしてください"
        )
        return
    plan.notes.append("pre-push フックを入れました（main への直接の push を止める）")
    if not dry_run:
        hooks.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run_init(
    target: Path,
    layers: Optional[List[str]] = None,
    force: bool = False,
    dry_run: bool = False,
    git_hook: bool = True,
    tdir: Optional[Path] = None,
) -> Plan:
    target = target.resolve()
    tdir = tdir or templates_dir()
    plan = Plan()
    chosen = detect_layers(target) if layers is None else layers
    for name in chosen:
        if name not in LAYERS:
            raise ValueError(f"知らない層です：{name}（使えるのは {', '.join(LAYERS)}）")

    files = template_files(tdir, chosen)
    for rel, src in files.items():
        _copy(src, target / rel, rel, plan, force, dry_run)

    _merge_gitignore(target, plan, dry_run)

    # テンプレートのまま入れたファイルの中身を覚えておく（harness upgrade が、人が直したかを見分けるため）
    installed = {}
    for rel, src in files.items():
        dst = target / rel
        data = src.read_bytes()
        if dry_run or (dst.exists() and dst.read_bytes() == data):
            installed[rel] = digest(data)
    manifest: Dict[str, object] = {"version": __version__, "layers": chosen, "files": installed}
    mpath = target / MANIFEST
    if not dry_run:
        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plan.notes.append(f"{MANIFEST} に版と層を記録：{__version__}・{', '.join(chosen) or 'なし'}")

    if git_hook and (dry_run or (target / PRE_PUSH_SRC).exists()):
        _install_pre_push(target, plan, force, dry_run)
    if not dry_run:
        for rel in plan.created + plan.overwritten:
            if rel.startswith(".claude/hooks/") and rel.endswith(".py") or rel.startswith("scripts/"):
                p = target / rel
                os.chmod(p, p.stat().st_mode | stat.S_IXUSR)
    return plan
