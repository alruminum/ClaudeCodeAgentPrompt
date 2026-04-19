#!/usr/bin/env python3
"""
post-agent-flags.py — PostToolUse(Agent) 글로벌 훅
에이전트 완료 후 플래그 생성/삭제 + 문서 신선도 경고.
프로젝트별 인라인 원라이너를 대체.

prefix는 환경변수 HARNESS_PREFIX로 주입 (기본값: mb).
doc_name은 환경변수 HARNESS_DOC_NAME으로 주입 (기본값: domain-logic).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import re
import time
from harness_common import get_prefix, get_flags_dir, flag_path, parse_marker_text, FLAGS
import session_state as ss

PREFIX = get_prefix()
DOC_NAME = os.environ.get("HARNESS_DOC_NAME", "domain-logic")


def touch(name):
    try:
        open(flag_path(PREFIX, name), "w").close()
    except Exception:
        pass


def remove(name):
    try:
        p = flag_path(PREFIX, name)
        if os.path.exists(p):
            os.remove(p)
    except Exception:
        pass


def warn(msg):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": msg
        }
    }))


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    inp = d.get("tool_input", {})
    resp = str(d.get("tool_response", ""))
    agent = inp.get("subagent_type", "")
    prompt = inp.get("prompt", "")

    if not agent:
        sys.exit(0)

    # 구조화된 마커 파싱: ---MARKER:X--- 우선, 레거시 폴백
    def has_marker(name):
        """구조화된 마커 ---MARKER:X--- 를 우선 탐색, 없으면 레거시 워드 매칭."""
        if f"---MARKER:{name}---" in resp:
            return True
        # 레거시 폴백: 단어 경계 매칭
        return bool(re.search(rf'\b{name}\b', resp))

    # ── validator PASS → 플래그 생성 ──
    if agent == "validator" and has_marker("PASS"):
        if re.search(r"Mode C|Plan Validation", prompt, re.IGNORECASE):
            touch(FLAGS.PLAN_VALIDATION_PASSED)
        if re.search(r"Mode B", prompt, re.IGNORECASE):
            touch(FLAGS.VALIDATOR_B_PASSED)
        # Mode D (Bugfix Validation) BUGFIX_PASS
        if has_marker("BUGFIX_PASS"):
            touch(FLAGS.BUGFIX_VALIDATION_PASSED)

    # ── test-engineer TESTS_PASS 또는 TESTS_WRITTEN → 플래그 생성 ──
    if agent == "test-engineer" and (has_marker("TESTS_PASS") or has_marker("TESTS_WRITTEN")):
        touch(FLAGS.TEST_ENGINEER_PASSED)

    # ── pr-reviewer LGTM → 플래그 생성 ──
    if agent == "pr-reviewer" and has_marker("LGTM") and not has_marker("CHANGES_REQUESTED"):
        touch(FLAGS.PR_REVIEWER_LGTM)

    # ── security-reviewer SECURE → 플래그 생성 ──
    if agent == "security-reviewer" and has_marker("SECURE") and not has_marker("VULNERABILITIES_FOUND"):
        touch(FLAGS.SECURITY_REVIEW_PASSED)

    # ── architect Mode B 완료 → 전체 플래그 초기화 ──
    if agent == "architect" and re.search(r"Mode B", prompt, re.IGNORECASE):
        for f in [FLAGS.PLAN_VALIDATION_PASSED, FLAGS.VALIDATOR_B_PASSED, FLAGS.TEST_ENGINEER_PASSED,
                   FLAGS.PR_REVIEWER_LGTM, FLAGS.SECURITY_REVIEW_PASSED, FLAGS.DESIGNER_RAN, FLAGS.DESIGN_CRITIC_PASSED]:
            remove(f)

    # ── architect Light Plan → LIGHT_PLAN_READY 플래그 ──
    if agent == "architect" and has_marker("LIGHT_PLAN_READY"):
        touch(FLAGS.LIGHT_PLAN_READY)

    # ── engineer 완료 → 검증 플래그 삭제 (재검증 강제) ──
    if agent == "engineer":
        for f in [FLAGS.TEST_ENGINEER_PASSED, FLAGS.PR_REVIEWER_LGTM, FLAGS.SECURITY_REVIEW_PASSED, FLAGS.VALIDATOR_B_PASSED]:
            remove(f)

    # ── harness-executor 완료 → harness_active 삭제 ──
    if agent == "harness-executor":
        remove(FLAGS.HARNESS_ACTIVE)

    # ── Phase 3: 에이전트 완료 → live.json.agent 해제 (agent-boundary.py 연동) ──
    # expect_value로 race 방지: 내 agent와 일치할 때만 삭제 (중첩 호출 안전).
    try:
        sid = ss.session_id_from_stdin(d)
        if sid:
            ss.clear_live_field(sid, "agent", expect_value=agent)
    except Exception:
        pass

    # ── architect 완료 후 문서 신선도 경고 ──
    if agent == "architect":
        base = os.getcwd()
        warns = []
        mode_ac = bool(re.search(r"Mode [AC]", prompt, re.IGNORECASE))
        mode_c = bool(re.search(r"Mode C", prompt, re.IGNORECASE))

        trd = os.path.join(base, "trd.md")
        dd = os.path.join(base, "docs", f"{DOC_NAME}.md")

        def age(path):
            return int(time.time() - os.path.getmtime(path)) if os.path.exists(path) else None

        trd_age, dd_age = age(trd), age(dd)

        if mode_ac and trd_age and trd_age > 120:
            warns.append(f"trd.md 미업데이트({trd_age}초 전)")
        if mode_c and dd_age and dd_age > 120:
            warns.append(f"docs/{DOC_NAME}.md 미업데이트({dd_age}초 전) — 설계 문서 동기화 필요")

        if warns:
            warn(f"⚠️ [HARNESS] architect 완료 후 문서 미업데이트: {', '.join(warns)}. 현행화 규칙 확인.")

    # ── designer 완료 → designer_ran + 이전 플래그 초기화 ──
    if agent == "designer":
        touch(FLAGS.DESIGNER_RAN)
        remove(FLAGS.DESIGN_CRITIC_PASSED)
        remove(FLAGS.PLAN_VALIDATION_PASSED)

    # ── design-critic PICK → 플래그 생성 ──
    if agent == "design-critic" and has_marker("PICK") and not has_marker("ITERATE") and not has_marker("ESCALATE"):
        touch(FLAGS.DESIGN_CRITIC_PASSED)

    # ── designer 결과에 PRD 대조 없으면 경고 ──
    if agent == "designer" and not re.search(r"PRD|prd\.md|기획자|product.planner", resp, re.IGNORECASE):
        warn("⚠️ [HARNESS] designer 결과에 PRD 대조 없음. PRD 위반 여부 확인 필요 — "
             "product-planner 에스컬레이션 고려. (orchestration-rules.md Step 0)")

    sys.exit(0)


if __name__ == "__main__":
    main()
