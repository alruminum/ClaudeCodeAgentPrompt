"""
config.py — HarnessConfig 데이터클래스 + harness.config.json 로더.
Python 3.9+ stdlib only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class HarnessConfig:
    prefix: str = "proj"
    test_command: str = ""
    lint_command: str = ""
    max_total_cost: float = 20.0
    token_budget: dict = field(default_factory=dict)
    isolation: str = ""  # "" (없음) 또는 "worktree"
    second_reviewer: str = ""  # "gemini", "gpt", "" (비활성)
    second_reviewer_model: str = ""  # "gemini-2.5-flash", "gpt-4o-mini" 등


def load_config(project_root: Path | None = None) -> HarnessConfig:
    """harness.config.json을 로드하여 HarnessConfig를 반환.

    project_root가 None이면 cwd부터 상위 순회하며 .claude/harness.config.json 탐색.
    파일이 없으면 기본값을 반환한다.
    """
    if project_root is None:
        project_root = _find_project_root()

    config_path = project_root / ".claude" / "harness.config.json"
    if not config_path.exists():
        # prefix를 디렉토리명에서 유도 (harness_common.py의 get_prefix와 동일 로직)
        import re
        raw = project_root.name.lower()
        fallback_prefix = re.sub(r"[^a-z0-9]", "", raw)[:8] or "proj"
        return HarnessConfig(prefix=fallback_prefix)

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return HarnessConfig()

    return HarnessConfig(
        prefix=data.get("prefix", "proj"),
        test_command=data.get("test_command", ""),
        lint_command=data.get("lint_command", ""),
        max_total_cost=float(data.get("max_total_cost", 20.0)),
        token_budget=data.get("token_budget", {}) if isinstance(data.get("token_budget", {}), dict) else {},
        isolation=data.get("isolation", ""),
        second_reviewer=data.get("second_reviewer", ""),
        second_reviewer_model=data.get("second_reviewer_model", ""),
    )


def _find_project_root() -> Path:
    """cwd부터 상위로 순회하며 .claude/ 디렉토리가 있는 프로젝트 루트를 찾는다."""
    cwd = Path.cwd().resolve()
    cur = cwd
    while True:
        if (cur / ".claude").is_dir():
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return cwd
