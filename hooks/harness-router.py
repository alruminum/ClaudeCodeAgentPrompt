#!/usr/bin/env python3
"""
Harness Router — UserPromptSubmit hook
Usage: python3 harness-router.py <PREFIX>
  PREFIX: project-specific flag prefix (e.g. "mb" → /tmp/mb_plan_validation_passed)
"""
import sys
import json
import os
import re
import time
import subprocess
from datetime import datetime

LOG_FILE = "/tmp/harness-router.log"

def log(prefix, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] [{prefix}] {msg}\n")

def classify_intent_llm(prompt, prefix):
    """LLM 보조 의도 분류 — AMBIGUOUS/불확실 시에만 호출. curl → Anthropic API."""
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return None
    try:
        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 20,
            "messages": [{"role": "user", "content":
                "사용자 프롬프트 의도를 분류. 다음 중 하나만 출력:\n"
                "IMPLEMENTATION QUESTION BUG GREETING GENERIC\n\n"
                f"\"{prompt[:200]}\""}]
        })
        result = subprocess.run(
            ['curl', '-s', '-m', '5',
             'https://api.anthropic.com/v1/messages',
             '-H', f'x-api-key: {api_key}',
             '-H', 'anthropic-version: 2023-06-01',
             '-H', 'content-type: application/json',
             '-d', payload],
            capture_output=True, text=True, timeout=7
        )
        data = json.loads(result.stdout)
        text = data.get('content', [{}])[0].get('text', '')
        for cat in ["IMPLEMENTATION", "BUG", "QUESTION", "GREETING", "GENERIC"]:
            if cat in text.upper():
                log(prefix, f"LLM_CLASSIFY result={cat}")
                return cat
    except Exception as e:
        log(prefix, f"LLM_CLASSIFY_FAIL: {e}")
    return None

def main():
    try:
        _main_inner()
    except Exception as e:
        # 어떤 예외든 graceful exit — hook error 방지
        try:
            log("?", f"UNCAUGHT: {e}")
        except Exception:
            pass
        sys.exit(0)

def _main_inner():
    raw_prefix = sys.argv[1] if len(sys.argv) > 1 else "auto"
    if raw_prefix == "auto":
        config_path = os.path.join(os.getcwd(), ".claude", "harness.config.json")
        if os.path.exists(config_path):
            try:
                config = json.load(open(config_path))
                prefix = config.get("prefix", "proj")
            except Exception:
                prefix = re.sub(r'[^a-z0-9]', '', os.path.basename(os.getcwd()).lower())[:8] or "proj"
        else:
            prefix = re.sub(r'[^a-z0-9]', '', os.path.basename(os.getcwd()).lower())[:8] or "proj"
    else:
        prefix = raw_prefix

    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # prompt 추출 — tool_input.prompt 또는 최상위 prompt 모두 지원
    prompt = (
        d.get("tool_input", {}).get("prompt", "")
        or d.get("prompt", "")
    )

    # 빈 prompt → 즉시 통과
    if not prompt or not prompt.strip():
        sys.exit(0)

    # mtime 기반 스태일 designer_ran 감지 (any_active 계산 전)
    dr_path = f"/tmp/{prefix}_designer_ran"
    dc_path = f"/tmp/{prefix}_design_critic_passed"
    if os.path.exists(dr_path) and not os.path.exists(dc_path):
        age_min = (time.time() - os.path.getmtime(dr_path)) / 60
        if age_min > 30:
            os.remove(dr_path)
            log(prefix, f"AUTO_CLEAR stale designer_ran (age={age_min:.0f}min)")

    # 현재 플래그 상태
    flags = {
        "plan_validation_passed": os.path.exists(f"/tmp/{prefix}_plan_validation_passed"),
        "designer_ran":         os.path.exists(f"/tmp/{prefix}_designer_ran"),
        "design_critic_passed": os.path.exists(f"/tmp/{prefix}_design_critic_passed"),
        "test_engineer_passed": os.path.exists(f"/tmp/{prefix}_test_engineer_passed"),
        "validator_b_passed":   os.path.exists(f"/tmp/{prefix}_validator_b_passed"),
        "pr_reviewer_lgtm":     os.path.exists(f"/tmp/{prefix}_pr_reviewer_lgtm"),
    }
    any_active = any(flags.values())

    # 인사말/짧은 감탄사 → 즉시 통과 (워크플로우 개입 불필요)
    greet_kw = r"^(헤이|안녕|hi|hey|hello|ㅎㅇ|ㅋ+|ㅎ+|응|네|아|오|음|좋아|감사|고마워|ok|okay)[\s!]*$"
    if re.match(greet_kw, prompt.strip(), re.IGNORECASE) and not any_active:
        log(prefix, f"PASS(greeting) prompt={prompt[:60]!r}")
        sys.exit(0)

    # 요청 분류
    impl_kw = r"구현|만들어|추가|수정|변경|바꿔|고쳐|삭제|리팩|implement|fix|add|update|src/|루프돌려|만들어보자|구현루프|시작해"
    q_kw    = r"어떻게|뭐야|왜|뭔가요|하나요|인가요|\?"
    bug_kw  = r"버그|뻐그|문제(가| 있| 생겼| 발생)|오류|에러|이상해|이상한데|이상하네|안 돼|안돼|안됨|안되네|고장|깨졌|망가|대박|말이 돼|왜 이래|왜이래|이게 뭐야|큐에이|큐에이야|큐에이 포함|버그있다|이슈왔다|야 큐에이|ㅋㅋ.{0,10}(버그|문제|오류)|진짜(야|다| 이래)"
    ambiguous = len(prompt.split()) < 5 and not re.search(impl_kw, prompt)

    is_bug = bool(re.search(bug_kw, prompt, re.IGNORECASE))

    if re.search(impl_kw, prompt):
        cat = "IMPLEMENTATION"
    elif re.search(q_kw, prompt):
        cat = "QUESTION"
    elif ambiguous:
        cat = "AMBIGUOUS"
    else:
        cat = "GENERIC"

    # LLM 보조 분류: regex가 불확실(AMBIGUOUS/GENERIC)할 때만 호출
    if cat in ("AMBIGUOUS", "GENERIC") and len(prompt.split()) >= 3:
        llm_cat = classify_intent_llm(prompt, prefix)
        if llm_cat:
            log(prefix, f"LLM_OVERRIDE {cat}→{llm_cat}")
            if llm_cat == "BUG":
                is_bug = True
            cat = llm_cat

    # QUESTION/AMBIGUOUS이고 진행 중인 워크플로우 없으면 아무것도 주입 안 함 (버그 감지 시 예외)
    if cat in ("QUESTION", "AMBIGUOUS") and not any_active and not is_bug:
        log(prefix, f"PASS({cat.lower()}/no-active) prompt={prompt[:60]!r}")
        sys.exit(0)

    flag_lines = "\n".join(
        f"  {'OK' if v else 'NG'} {k}" for k, v in flags.items()
    )

    if cat == "AMBIGUOUS":
        ctx = (
            "[HARNESS ROUTER] 요청이 모호합니다. 구현 시작 전 아래를 명확히 하세요:\n"
            "1. 어떤 파일/컴포넌트가 대상인가?\n"
            "2. 현재 동작 vs 기대 동작은?\n"
            "3. 관련 GitHub 이슈 번호가 있는가?\n"
            "구현 수준 모호성이면 위 3가지 답변 후 재요청. PRD 수준 모호성이면 product-planner 호출."
        )
        log(prefix, f"INJECT(ambiguous) prompt={prompt[:60]!r}")
    elif cat == "IMPLEMENTATION":
        # 이슈 컨텍스트 추적 — 이슈 전환 시 outer gate 플래그 초기화
        issue_match = re.search(r'#(\d+)', prompt)
        current_issue = issue_match.group(0) if issue_match else None
        issue_file = f"/tmp/{prefix}_current_issue"
        stored_issue = open(issue_file).read().strip() if os.path.exists(issue_file) else None
        if current_issue and stored_issue != current_issue:
            all_flag_keys = [
                "plan_validation_passed", "designer_ran", "design_critic_passed",
                "test_engineer_passed", "validator_b_passed", "pr_reviewer_lgtm"
            ]
            cleared = []
            for f in all_flag_keys:
                p = f"/tmp/{prefix}_{f}"
                if os.path.exists(p):
                    os.remove(p)
                    cleared.append(f)
                flags[f] = False
            open(issue_file, 'w').write(current_issue)
            log(prefix, f"TASK_SWITCH {stored_issue}→{current_issue}: cleared={cleared}")

        # flag_lines 재생성 (이슈 전환으로 flags 변경됐을 수 있음)
        flag_lines = "\n".join(
            f"  {'OK' if v else 'NG'} {k}" for k, v in flags.items()
        )
        # harness-memory Known Failure Patterns 읽기
        memory_patterns = []
        for mf in [
            os.path.join(os.getcwd(), ".claude", "harness-memory.md"),
            os.path.expanduser("~/.claude/harness-memory.md"),
        ]:
            if os.path.exists(mf):
                try:
                    content = open(mf).read()
                    m = re.search(
                        r'##?\s*Known Failure Patterns?\s*\n(.*?)(?=\n##|\Z)',
                        content, re.DOTALL | re.IGNORECASE
                    )
                    if m:
                        patterns = m.group(1).strip()
                        if patterns:
                            # 최근 20개 항목만 유지 (컨텍스트 낭비 방지)
                            lines = [l for l in patterns.split('\n') if l.strip()][-20:]
                            memory_patterns.append('\n'.join(lines))
                except Exception:
                    pass

        # harness-executor.sh 라우팅 지시 (설계 스펙: isActionable → runHarnessLoop)
        if flags["plan_validation_passed"]:
            impl_path_file = f"/tmp/{prefix}_impl_path"
            impl_path = open(impl_path_file).read().strip() if os.path.exists(impl_path_file) else "[IMPL_PATH]"
            issue_ref = current_issue or "N"
            harness_directive = (
                f"\n\n🔁 [HARNESS ROUTER] plan_validation_passed OK → 아래 Bash 명령을 즉시 실행하라:\n"
                f"bash .claude/harness-executor.sh impl2 --impl {impl_path} --issue {issue_ref} --prefix {prefix}\n"
                "engineer 직접 호출 금지. 위 스크립트가 루프를 완주한다."
            )
        else:
            harness_directive = (
                "\n\n⚠️ src/** 직접 Edit/Write 금지. engineer 에이전트 직접 호출 금지.\n"
                f"올바른 순서: Bash로 harness-executor.sh 호출.\n"
                f"예: bash .claude/harness-executor.sh impl --impl [IMPL_PATH] --issue {current_issue or 'N'} --prefix {prefix}"
            )

        ctx = (
            "[HARNESS ROUTER] 현재 워크플로우 상태\n"
            + flag_lines
            + "\n\n요청 분류: IMPLEMENTATION"
            + harness_directive
        )
        if memory_patterns:
            ctx += "\n\n[HARNESS MEMORY] Known Failure Patterns:\n" + "\n---\n".join(memory_patterns)
        active_flags = [k for k, v in flags.items() if v]
        log(prefix, f"INJECT(impl) issue={current_issue} prompt={prompt[:60]!r} active={active_flags}")
    else:
        if not any_active and not is_bug:
            log(prefix, f"PASS(generic/no-active) prompt={prompt[:60]!r}")
            sys.exit(0)
        if is_bug and not any_active:
            ctx = "[HARNESS ROUTER] 진행 중인 워크플로우 없음"
        else:
            ctx = "[HARNESS ROUTER] 진행 중인 워크플로우 있음\n" + flag_lines
        log(prefix, f"INJECT(generic/active) prompt={prompt[:60]!r}")

    # 버그/이슈 감지 시 QA 에이전트 힌트 prepend
    if is_bug:
        qa_hint = (
            "🐛 [HARNESS ROUTER] 버그/이슈 감지\n"
            "→ QA 에이전트를 먼저 호출하세요: 원인 분석 + 워크플로우 라우팅 추천\n"
            "→ 원인이 이미 명확하면 QA 생략하고 architect (버그픽스 — Mode B) 직행 가능\n"
        )
        ctx = qa_hint + "\n" + ctx
        log(prefix, f"QA_HINT injected prompt={prompt[:60]!r}")

    print(json.dumps({"hookSpecificOutput": {"additionalContext": ctx}}))


if __name__ == "__main__":
    main()
