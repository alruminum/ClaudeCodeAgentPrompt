#!/usr/bin/env python3
"""
post-agent-flags.py — PostToolUse(Agent) 글로벌 훅
에이전트 완료 후 플래그 생성/삭제 + 문서 신선도 경고.
프로젝트별 인라인 원라이너를 대체.

prefix는 환경변수 HARNESS_PREFIX로 주입 (기본값: mb).
doc_name은 환경변수 HARNESS_DOC_NAME으로 주입 (기본값: domain-logic).
"""
import sys
import json
import os
import re
import time

PREFIX = os.environ.get("HARNESS_PREFIX", "mb")
DOC_NAME = os.environ.get("HARNESS_DOC_NAME", "domain-logic")


def flag_path(name):
    return f"/tmp/{PREFIX}_{name}"


def touch(name):
    try:
        open(flag_path(name), "w").close()
    except Exception:
        pass


def remove(name):
    try:
        p = flag_path(name)
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

    # ── validator PASS → 플래그 생성 ──
    if agent == "validator" and "PASS" in resp:
        if re.search(r"Mode C|Plan Validation", prompt, re.IGNORECASE):
            touch("plan_validation_passed")
        if re.search(r"Mode B", prompt, re.IGNORECASE):
            touch("validator_b_passed")
        # Mode D (Bugfix Validation) BUGFIX_PASS
        if "BUGFIX_PASS" in resp:
            touch("bugfix_validation_passed")

    # ── test-engineer TESTS_PASS → 플래그 생성 ──
    if agent == "test-engineer" and "TESTS_PASS" in resp:
        touch("test_engineer_passed")

    # ── pr-reviewer LGTM → 플래그 생성 ──
    if agent == "pr-reviewer" and "LGTM" in resp and "CHANGES_REQUESTED" not in resp:
        touch("pr_reviewer_lgtm")

    # ── security-reviewer SECURE → 플래그 생성 ──
    if agent == "security-reviewer" and "SECURE" in resp and "VULNERABILITIES_FOUND" not in resp:
        touch("security_review_passed")

    # ── architect Mode B 완료 → 전체 플래그 초기화 ──
    if agent == "architect" and re.search(r"Mode B", prompt, re.IGNORECASE):
        for f in ["plan_validation_passed", "validator_b_passed", "test_engineer_passed",
                   "pr_reviewer_lgtm", "security_review_passed", "designer_ran", "design_critic_passed"]:
            remove(f)

    # ── architect Mode F (Bugfix Plan) → BUGFIX_PLAN_READY 플래그 ──
    if agent == "architect" and "BUGFIX_PLAN_READY" in resp:
        touch("bugfix_plan_ready")

    # ── engineer 완료 → 검증 플래그 삭제 (재검증 강제) ──
    if agent == "engineer":
        for f in ["test_engineer_passed", "pr_reviewer_lgtm", "security_review_passed", "validator_b_passed"]:
            remove(f)

    # ── harness-executor 완료 → harness_active 삭제 ──
    if agent == "harness-executor":
        remove("harness_active")

    # ── 에이전트 완료 → {agent}_active 삭제 (agent-boundary.py 연동) ──
    remove(f"{agent}_active")

    # ── architect 완료 후 문서 신선도 경고 ──
    if agent == "architect":
        base = os.getcwd()
        warns = []
        mode_ac = bool(re.search(r"Mode [AC]", prompt, re.IGNORECASE))
        mode_b = bool(re.search(r"Mode B", prompt, re.IGNORECASE))
        mode_c = bool(re.search(r"Mode C", prompt, re.IGNORECASE))

        trd = os.path.join(base, "trd.md")
        tp = os.path.join(base, "docs", "test-plan.md")
        dd = os.path.join(base, "docs", f"{DOC_NAME}.md")

        def age(path):
            return int(time.time() - os.path.getmtime(path)) if os.path.exists(path) else None

        trd_age, tp_age, dd_age = age(trd), age(tp), age(dd)

        if mode_ac and trd_age and trd_age > 120:
            warns.append(f"trd.md 미업데이트({trd_age}초 전)")
        if mode_b and tp_age and tp_age > 120:
            warns.append(f"docs/test-plan.md 미업데이트({tp_age}초 전)")
        if mode_c and dd_age and dd_age > 120:
            warns.append(f"docs/{DOC_NAME}.md 미업데이트({dd_age}초 전) — 설계 문서 동기화 필요")

        if warns:
            warn(f"⚠️ [HARNESS] architect 완료 후 문서 미업데이트: {', '.join(warns)}. 현행화 규칙 확인.")

    # ── designer 완료 → designer_ran + 이전 플래그 초기화 ──
    if agent == "designer":
        touch("designer_ran")
        remove("design_critic_passed")
        remove("plan_validation_passed")

    # ── design-critic PICK → 플래그 생성 ──
    if agent == "design-critic" and "PICK" in resp and "ITERATE" not in resp and "ESCALATE" not in resp:
        touch("design_critic_passed")

    # ── designer 결과에 PRD 대조 없으면 경고 ──
    if agent == "designer" and not re.search(r"PRD|prd\.md|기획자|product.planner", resp, re.IGNORECASE):
        warn("⚠️ [HARNESS] designer 결과에 PRD 대조 없음. PRD 위반 여부 확인 필요 — "
             "product-planner 에스컬레이션 고려. (orchestration-rules.md Step 0)")

    sys.exit(0)


if __name__ == "__main__":
    main()
