#!/usr/bin/env python3
"""
harness-drift-check.py — PreToolUse(Bash) 훅

git commit 시 **경로 패턴 기반**으로 Change-Type을 분류하고, 각 Change-Type에
매핑된 **필수 동반 파일**이 staged에 포함됐는지 검증한다.

거버넌스 개요:
  - Task-ID + WHAT/WHY 로그는 orchestration/update-record.md, rationale-history.md 참조
  - Change-Type은 update-record.md §Change-Type 토큰 표와 동기화
  - Document-Exception: diff의 **추가 라인**에 명시된 경우에만 유효 (과거 누적 엔트리 무효)

동작:
  - git commit 명령 감지 → staged 파일 + cached diff 추출
  - 변경 파일을 PATH_RULES로 카테고리 분류
  - 각 카테고리의 REQUIRED 동반 파일이 staged에 있는지 확인
  - 누락 시 1회 deny + bypass 플래그 설정 (5분 TTL) → 재커밋 시 통과 (advisory 운영)
  - diff 추가 라인에 `Document-Exception:` 있으면 해당 diff에만 한정 예외
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

# 화이트리스트 가드 import
_sys_path = os.path.dirname(os.path.abspath(__file__))
if _sys_path not in sys.path:
    sys.path.insert(0, _sys_path)
from harness_common import is_harness_enabled  # noqa: E402

BYPASS_FLAG = "/tmp/_harness_drift_bypass"
BYPASS_TTL = 300  # 5분 내 재시도만 허용 (advisory)

# ─────────────────────────────────────────────────────────────
# PATH_RULES — 경로 정규식 → (카테고리, [필수 동반 파일 정규식])
#
# 동반 파일은 "변경 시 함께 살펴야 하는 문서". 1개 이상 매칭되면 통과.
# 카테고리 라벨은 update-record.md Change-Type 토큰과 동기화.
# ─────────────────────────────────────────────────────────────
PATH_RULES: list[tuple[str, str, list[str]]] = [
    # (regex, category, required_alternates)

    # 에이전트 정의 변경 → 경계 문서 + changelog
    (r"^agents/[^/]+\.md$", "agents",
     [r"^orchestration/agent-boundaries\.md$",
      r"^orchestration/changelog\.md$",
      r"^orchestration/update-record\.md$"]),

    # 훅 변경 → settings.json 또는 setup-harness.sh (훅 등록·주석)
    (r"^hooks/[^/]+\.py$", "hooks",
     [r"^settings\.json$",
      r"^setup-harness\.sh$",
      r"^orchestration/update-record\.md$"]),

    # plan_loop 변경 → plan.md + changelog
    (r"^harness/plan_loop\.py$", "plan-loop",
     [r"^orchestration/plan\.md$",
      r"^orchestration/changelog\.md$",
      r"^orchestration/update-record\.md$"]),

    # impl_loop/router 변경 → impl_*.md 중 하나 + changelog
    (r"^harness/impl_(loop|router)\.py$", "impl-loop",
     [r"^orchestration/impl(_simple|_std|_deep|)\.md$",
      r"^orchestration/changelog\.md$",
      r"^orchestration/update-record\.md$"]),

    # harness core/helpers/config → changelog + tests
    (r"^harness/(core|helpers|config)\.py$", "harness-core",
     [r"^orchestration/changelog\.md$",
      r"^orchestration/update-record\.md$",
      r"^harness/tests/.+$"]),

    # 커맨드/스킬 변경 → update-record
    (r"^commands/[^/]+\.md$", "commands",
     [r"^orchestration/update-record\.md$"]),

    # orchestration-rules 자체 변경 → changelog + update-record
    (r"^orchestration-rules\.md$", "orchestration",
     [r"^orchestration/changelog\.md$",
      r"^orchestration/update-record\.md$"]),

    # orchestration/*.md 변경 → update-record 동반 (doc의 doc)
    (r"^orchestration/(?!update-record|rationale-history)[^/]+\.md$", "orchestration",
     [r"^orchestration/update-record\.md$"]),
]


def _read_stdin() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def _git(args: list[str], timeout: int = 5) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception:
        return ""


def _staged_files() -> list[str]:
    out = _git(["git", "diff", "--cached", "--name-only"])
    return [l for l in out.splitlines() if l.strip()]


def _diff_added_lines() -> str:
    """cached diff의 추가 라인만 반환 (Document-Exception 스코핑용)."""
    out = _git(["git", "diff", "--cached", "-U0"])
    added = []
    for line in out.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
    return "\n".join(added)


def _has_document_exception(added: str) -> tuple[bool, str]:
    """현재 diff 추가 라인에 `Document-Exception:` 있으면 True + 사유 반환."""
    m = re.search(r"Document-Exception:\s*(\S+)\s+(.+)", added)
    if m:
        return True, f"{m.group(1)} {m.group(2).strip()}"
    return False, ""


def _bypass_check() -> bool:
    """재커밋 advisory — 5분 내 이전 경고 직후 재시도면 통과."""
    if not os.path.exists(BYPASS_FLAG):
        return False
    age = time.time() - os.path.getmtime(BYPASS_FLAG)
    try:
        os.remove(BYPASS_FLAG)
    except OSError:
        pass
    return age < BYPASS_TTL


def _check_rules(staged: list[str]) -> list[tuple[str, str, list[str]]]:
    """
    staged 파일을 PATH_RULES로 분류 후, 카테고리별 필수 동반 파일 미충족 항목 반환.

    Returns:
        list of (matched_file, category, missing_alternates).
        missing_alternates: 매핑된 후보 중 staged에 아무것도 없으면 전체 후보 리턴.
    """
    issues: list[tuple[str, str, list[str]]] = []
    for f in staged:
        for pattern, category, alternates in PATH_RULES:
            if re.match(pattern, f):
                # 최소 1개 대체 경로가 staged에 포함돼있으면 통과
                if not any(re.match(alt, s) for s in staged for alt in alternates):
                    issues.append((f, category, alternates))
    return issues


def main():
    if not is_harness_enabled():
        sys.exit(0)

    d = _read_stdin()
    cmd = d.get("tool_input", {}).get("command", "")
    if not re.search(r"\bgit\s+commit\b", cmd):
        sys.exit(0)

    # advisory bypass
    if _bypass_check():
        sys.exit(0)

    staged = _staged_files()
    if not staged:
        sys.exit(0)

    # 1) Document-Exception 스코프 체크 (현재 diff 추가 라인만)
    added = _diff_added_lines()
    has_exc, exc_reason = _has_document_exception(added)

    # 2) 경로 패턴 규칙 검증
    issues = _check_rules(staged)

    # Exception 있으면 전역 통과
    if has_exc and issues:
        print(
            f"[drift-check] Document-Exception 수용: {exc_reason}",
            file=sys.stderr,
        )
        sys.exit(0)

    if not issues:
        sys.exit(0)

    # 3) 이슈 정리 — 같은 카테고리는 한 줄로 묶기
    by_cat: dict[str, set[str]] = {}
    by_cat_missing: dict[str, list[str]] = {}
    for f, cat, alts in issues:
        by_cat.setdefault(cat, set()).add(f)
        by_cat_missing[cat] = alts  # 동일 카테고리는 동일 alternates

    lines = []
    for cat, files in by_cat.items():
        fs = ", ".join(sorted(files))
        alts = by_cat_missing[cat]
        # 정규식을 사람 읽기 편한 형태로 요약
        alts_readable = ", ".join(a.replace("^", "").replace("$", "").replace("\\", "") for a in alts)
        lines.append(
            f"  • [{cat}] 변경됨: {fs}\n"
            f"    → 아래 중 최소 1개 동반 필요: {alts_readable}"
        )

    # bypass 플래그 (advisory: 5분 내 재커밋 시 통과)
    open(BYPASS_FLAG, "w").close()

    msg = (
        "⚠️ [drift-check] 경로 기반 거버넌스 위반\n"
        + "\n".join(lines)
        + "\n\n"
        "해결 옵션:\n"
        "  1) 위 동반 파일 중 하나를 함께 staged하고 재커밋\n"
        "  2) 의도적 예외면 커밋 메시지·diff에 "
        "`Document-Exception: HARNESS-CHG-YYYYMMDD-NN <사유>` 추가\n"
        "  3) 이미 확인했다면 그대로 재커밋 (5분 내 bypass)"
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": msg,
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
