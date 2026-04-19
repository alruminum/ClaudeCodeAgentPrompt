#!/usr/bin/env python3
"""ralph-session-stop.py — ralph-loop 공유 state 파일의 세션 가로채기 방어.

오피셜 `ralph-loop@claude-plugins-official` 훅은 `.claude/ralph-loop.local.md`를
프로젝트 루트에 두고 transcript_path로 세션을 구분한다. 하지만 **첫 stop 전**에는
transcript가 비어 있어서, 다른 세션의 Stop 훅이 자기 transcript에 "Ralph loop
activated" 문구가 들어와 있으면(예: 유저가 ralph-loop 커맨드를 친 적 있음) 오피셜
훅이 그 세션으로 claim을 넘겨버려 "엉뚱한 세션에서 루프2 시작" 사고가 난다.

이 선행 Stop 훅은 오피셜 훅을 수정하지 않고 다음을 한다:
  1. 처음 보는 state 파일이면 현재 CC session_id를 `cc_session_id:` 필드로 기록.
  2. 이미 cc_session_id가 기록된 state를 이 세션이 아닌 쪽에서 만나면 stderr에
     경고를 찍고 **아무 JSON도 출력하지 않고** exit — 오피셜 훅의 판정에
     영향을 주지 않는다. 경고만으로 유저가 교차오염을 인지하도록 한다.

오피셜 훅을 건드리지 않는다는 원칙(orchestration-rules "플러그인 디렉토리 직접
수정 금지")과 일관. 완전한 가로채기 방지는 오피셜 훅 자체의 claim 로직을 바꿔야
가능하므로 Phase 4 스코프에서 재검토.
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS_DIR))

import session_state as ss  # noqa: E402

STATE_FILENAME = ".claude/ralph-loop.local.md"
CC_SID_FIELD = "cc_session_id"


def _read_stdin_json() -> dict:
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _find_state_file(start: Path) -> Path | None:
    """프로젝트 루트(.claude/가 있는 디렉토리) 내의 .claude/ralph-loop.local.md만 본다.
    파일시스템 루트까지 올라가면 우연히 `/.claude/ralph-loop.local.md` 같은 게 있을 때
    오탐하므로, session_state의 프로젝트 루트 탐색 규칙을 재사용한다."""
    project_root = ss._find_project_root(start)
    candidate = project_root / STATE_FILENAME
    return candidate if candidate.exists() else None


def _parse_cc_sid(content: str) -> str:
    m = re.search(rf"^{CC_SID_FIELD}:\s*(\S+)\s*$", content, flags=re.MULTILINE)
    return m.group(1) if m else ""


def _inject_cc_sid(content: str, sid: str) -> str:
    """frontmatter에 cc_session_id 필드 주입 (atomic write 대상)."""
    lines = content.splitlines(keepends=True)
    if not lines or not lines[0].strip() == "---":
        return content
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            insert = f"{CC_SID_FIELD}: {sid}\n"
            return "".join(lines[:i] + [insert] + lines[i:])
    return content


def main() -> int:
    data = _read_stdin_json()
    sid = ss.session_id_from_stdin(data) or ss.current_session_id()
    if not sid:
        return 0

    start = Path(data.get("cwd") or os.getcwd())
    try:
        state_file = _find_state_file(start.resolve())
    except OSError:
        return 0
    if state_file is None:
        return 0

    try:
        content = state_file.read_text(encoding="utf-8")
    except OSError:
        return 0

    recorded = _parse_cc_sid(content)
    if not recorded:
        updated = _inject_cc_sid(content, sid)
        if updated != content:
            try:
                # UUID로 tmp 이름 충돌 방지 (session_state.atomic_write_json과 동일 패턴).
                tmp = state_file.with_suffix(state_file.suffix + f".{uuid.uuid4().hex}.tmp")
                tmp.write_text(updated, encoding="utf-8")
                os.replace(tmp, state_file)
            except OSError:
                pass
        return 0

    if recorded != sid:
        print(
            f"⚠️  ralph-loop: state 파일이 다른 세션({recorded[:8]}…) 소유입니다. "
            f"현재 세션({sid[:8]}…)에서는 이 state를 claim하지 마세요. "
            f"필요하면 `rm {state_file}` 로 잔재를 정리하세요.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
