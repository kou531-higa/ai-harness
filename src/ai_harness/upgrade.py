"""harness upgrade：入れたあとに更新されたテンプレートを、導入先に取り込む。

ファイルごとに、導入先の今の中身・入れたときの中身（.claude/harness.json の files）・新しいテンプレートを比べる。
- ない（入れたことがない）           → 足す
- 入れたまま触っていない             → 新しいテンプレートに入れ替える
- 人が直した（入れたときと違う）     → 上書きしない。新しいテンプレートを <ファイル>.harness-new に置く
- 人が消した                         → 戻さない
- テンプレートから消えた             → 知らせるだけ（消すかは人が決める）
入れたときの記録がない（古い版で入れた）ファイルは、テンプレートと同じでなければ「人が直した」として扱う。
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import __version__
from .init import MANIFEST, _merge_gitignore, digest, template_files, templates_dir

NEW_SUFFIX = ".harness-new"


@dataclass
class UpgradePlan:
    added: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    current: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    deleted_by_user: List[str] = field(default_factory=list)
    gone_from_template: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    from_version: str = "?"


def run_upgrade(target: Path, dry_run: bool = False, tdir: Optional[Path] = None) -> UpgradePlan:
    target = target.resolve()
    tdir = tdir or templates_dir()
    mpath = target / MANIFEST
    if not mpath.exists():
        raise FileNotFoundError(f"{MANIFEST} がありません。先に harness init を実行してください")
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    base: Dict[str, str] = dict(manifest.get("files") or {})
    layers: List[str] = list(manifest.get("layers") or [])
    plan = UpgradePlan(from_version=str(manifest.get("version", "?")))
    if "files" not in manifest:
        plan.notes.append(
            "入れたときの記録がない版で入れているので、テンプレートと違うファイルは「人が直した」として扱います"
        )

    files = template_files(tdir, layers)
    recorded: Dict[str, str] = {}
    for rel, src in files.items():
        new = src.read_bytes()
        new_d = digest(new)
        dst = target / rel
        if not dst.exists():
            if rel in base:
                plan.deleted_by_user.append(rel)
                recorded[rel] = base[rel]  # 消したことを覚えておく（次の upgrade でも戻さない）
                continue
            plan.added.append(rel)
            _write(dst, new, dry_run, rel)
            recorded[rel] = new_d
            continue
        cur_d = digest(dst.read_bytes())
        if cur_d == new_d:
            plan.current.append(rel)
            recorded[rel] = new_d
        elif base.get(rel) == cur_d:
            plan.updated.append(rel)
            _write(dst, new, dry_run, rel)
            recorded[rel] = new_d
        else:
            plan.conflicts.append(rel)
            _write(dst.with_name(dst.name + NEW_SUFFIX), new, dry_run, rel)
            if rel in base:
                recorded[rel] = base[rel]  # 人が合わせるまで、入れたときの中身を覚えておく
    plan.gone_from_template = sorted(set(base) - set(files))

    _merge_gitignore(target, plan, dry_run)  # type: ignore[arg-type]
    if not dry_run:
        manifest.update({"version": __version__, "files": dict(sorted(recorded.items()))})
        mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return plan


def _write(dst: Path, data: bytes, dry_run: bool, rel: str) -> None:
    if dry_run:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    if rel.startswith("scripts/") or (rel.startswith(".claude/hooks/") and rel.endswith(".py")):
        os.chmod(dst, dst.stat().st_mode | stat.S_IXUSR)
