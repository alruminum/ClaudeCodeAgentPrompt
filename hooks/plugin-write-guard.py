#!/usr/bin/env python3
"""plugin-write-guard.py — PreToolUse(Write/Edit) 훅: 플러그인 디렉토리 직접 수정 차단.

`~/.claude/plugins/{cache,marketplaces,data}/**` 는 CC 플러그인 매니저가 관리하는
영역이다. 수동 수정은 재설치 시 증발하거나 원본과 drift를 만들어 추적 불가능한
오염을 남긴다. 과거 ralph 래퍼를 플러그인 내부에 넣었다가 `~/.claude/commands/`로
옮긴 뒤 잔재가 갈라진 사고가 반복됐기에, 이 훅으로 물리적 차단한다.

예외: `CLAUDE_ALLOW_PLUGIN_EDIT=1` 환경 변수가 설정된 플러그인 개발 세션.

관련: orchestration-rules.md "플러그인 디렉토리 직접 수정 금지" 섹션.
차단 메커니즘은 다른 훅과 동일하게 `harness_common.deny()` — PreToolUse JSON
(permissionDecision: deny). exit 2 대신 JSON payload로 통일해 훅 체인이 결정을
일관되게 집계한다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS_DIR))

from harness_common import deny  # noqa: E402

ALLOW_ENV = "CLAUDE_ALLOW_PLUGIN_EDIT"
PLUGIN_SUBDIRS = ("cache", "marketplaces", "data")


def _norm(p: str) -> str:
    try:
        return str(Path(p).expanduser().resolve(strict=False))
    except OSError:
        return os.path.abspath(os.path.expanduser(p))


def _plugin_roots() -> list[str]:
    base = Path.home() / ".claude" / "plugins"
    return [_norm(str(base / sub)) for sub in PLUGIN_SUBDIRS]


def _is_under(target: str, root: str) -> bool:
    return target == root or target.startswith(root + os.sep)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        return

    if data.get("tool_name") not in ("Write", "Edit"):
        return

    fp = data.get("tool_input", {}).get("file_path", "")
    if not fp:
        return

    if os.environ.get(ALLOW_ENV) == "1":
        return

    target = _norm(fp)
    for root in _plugin_roots():
        if _is_under(target, root):
            deny(
                f"[plugin-write-guard] 플러그인 디렉토리 직접 수정 금지: {fp}\n"
                "CC 플러그인 매니저가 관리하는 영역입니다. 재설치 시 변경이 증발하거나\n"
                "원본과 drift가 생겨 추적 불가능한 오염을 만듭니다.\n"
                "- 커스텀 스킬/커맨드는 ~/.claude/commands/*.md 에 두세요.\n"
                "- 에이전트 프로젝트 컨텍스트는 .claude/agent-config/*.md 에 두세요.\n"
                "- 오피셜 플러그인 버그는 선행 훅(~/.claude/hooks/*.py)으로 우회하세요.\n"
                f"- 정말 필요하면 {ALLOW_ENV}=1 환경 변수로 일시 허용."
            )


if __name__ == "__main__":
    main()
