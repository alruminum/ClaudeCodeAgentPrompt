#!/usr/bin/env python3
"""
harness-drift-check.py — PreToolUse(Bash) 훅
git commit 시 orchestration-rules.md 또는 agents/*.md가 변경됐지만
관련 스크립트(harness/executor.sh, harness/impl_{fast,std,deep}.sh 등)가 함께 변경되지 않으면 경고.

동작:
  - git commit 명령 감지 → staged 파일 확인
  - 규칙/에이전트 파일만 변경되고 대응 스크립트 미변경 → 1회 deny + 안내
  - bypass 플래그 존재 시 (이전 경고 후 재시도) → 통과
  - bypass 플래그는 사용 후 자동 삭제 (1회용)
"""
import sys
import json
import subprocess
import re
import os
import time

BYPASS_FLAG = "/tmp/_harness_drift_bypass"
BYPASS_TTL = 300  # 5분 내 재시도만 허용

# 규칙/에이전트 → 연동 스크립트 매핑
DRIFT_MAP = {
    'orchestration-rules.md': [
        'harness/executor.sh',
        'harness/impl.sh', 'harness/impl_simple.sh', 'harness/impl_std.sh',
        'harness/impl_deep.sh', 'harness/impl_helpers.sh',
        'harness/plan.sh', 'harness/utils.sh',
    ],
    'agents/qa.md': ['commands/qa.md'],
    'agents/architect.md': ['harness/impl.sh', 'harness/plan.sh'],
    'agents/validator.md': [
        'harness/impl_simple.sh', 'harness/impl_std.sh', 'harness/impl_deep.sh',
        'harness/impl.sh', 'harness/plan.sh',
    ],
    'agents/engineer.md': ['harness/impl_std.sh', 'harness/impl_deep.sh', 'harness/impl_helpers.sh'],
    'agents/test-engineer.md': ['harness/impl_std.sh', 'harness/impl_deep.sh'],
    # designer/design-critic는 하네스 루프 밖 (v4). ux 스킬이 직접 호출.
    # harness/design.sh는 DEPRECATED — 드리프트 체크 대상에서 제외.
    'agents/designer.md': ['commands/ux.md'],
    'agents/design-critic.md': ['orchestration/design.md'],
    'agents/product-planner.md': ['harness/plan.sh'],
    'agents/pr-reviewer.md': ['harness/impl_simple.sh', 'harness/impl_std.sh', 'harness/impl_deep.sh'],
    'agents/security-reviewer.md': ['harness/impl_deep.sh'],
}


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    command = d.get("tool_input", {}).get("command", "")

    # git commit 명령이 아니면 통과
    if not re.search(r'git\s+commit', command):
        sys.exit(0)

    # bypass 플래그 확인 (이전 경고 후 재시도)
    if os.path.exists(BYPASS_FLAG):
        age = time.time() - os.path.getmtime(BYPASS_FLAG)
        if age < BYPASS_TTL:
            os.remove(BYPASS_FLAG)
            sys.exit(0)
        else:
            os.remove(BYPASS_FLAG)

    # staged 파일 목록
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only'],
            capture_output=True, text=True, timeout=5
        )
        staged = set(result.stdout.strip().splitlines())
    except Exception:
        sys.exit(0)

    if not staged:
        sys.exit(0)

    # 변경된 규칙/에이전트 파일 → 필요한 스크립트 수집
    changed_rules = []
    needed_scripts = set()
    for rule_pattern, scripts in DRIFT_MAP.items():
        for sf in staged:
            if sf.endswith(rule_pattern):
                changed_rules.append(sf)
                needed_scripts.update(scripts)
                break

    if not changed_rules or not needed_scripts:
        sys.exit(0)

    # 필요한 스크립트가 staged에 있는지 확인
    missing = []
    for script in needed_scripts:
        if not any(s.endswith(script) for s in staged):
            missing.append(script)

    if not missing:
        sys.exit(0)

    # 드리프트 감지 → 1회 deny + bypass 플래그 설정
    open(BYPASS_FLAG, "w").close()

    rules_str = ", ".join(os.path.basename(r) for r in changed_rules)
    scripts_str = ", ".join(missing)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"⚠️ [drift-check] 규칙/에이전트 변경됨: {rules_str}\n"
                f"   관련 스크립트 미변경: {scripts_str}\n"
                f"   스크립트도 업데이트가 필요한지 확인하세요.\n"
                f"   이미 확인했다면 다시 커밋하면 통과됩니다 (5분 내)."
            )
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
