"""フック共通の処理。標準ライブラリだけを使う（導入先の環境に依存しないため）。

Claude Code のフックは stdin で JSON を受け取る。
終了コード 2 で操作を止め、stderr の内容が AI に返る。
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, NoReturn

EXIT_OK = 0
EXIT_BLOCK = 2


def read_input() -> Dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def project_dir(data: Dict[str, Any]) -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    cwd = data.get("cwd")
    if isinstance(cwd, str) and cwd:
        return Path(cwd).resolve()
    return Path.cwd().resolve()


def relative_path(file_path: str, root: Path) -> str | None:
    """プロジェクト内なら相対パス（/区切り）を返す。外なら None。"""
    p = Path(file_path)
    if not p.is_absolute():
        p = root / p
    p = Path(os.path.normpath(str(p)))
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return None


def log_event(root: Path, hook: str, decision: str, reason: str, **extra: Any) -> None:
    """止めた記録を .harness/events.jsonl に追記する。失敗してもフックは止めない。"""
    try:
        log_dir = root / ".harness"
        log_dir.mkdir(exist_ok=True)
        record = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "hook": hook,
            "decision": decision,
            "reason": reason,
        }
        record.update(extra)
        with (log_dir / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def block(message: str) -> NoReturn:
    sys.stderr.write(message.rstrip() + "\n")
    sys.exit(EXIT_BLOCK)
