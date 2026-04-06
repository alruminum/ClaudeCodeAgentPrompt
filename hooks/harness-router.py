#!/usr/bin/env python3
"""
Harness Router — UserPromptSubmit hook
S16: runHarnessLoop 구현 — 의도 분류 후 harness-executor.sh 백그라운드 직접 실행
Usage: python3 harness-router.py <PREFIX|auto>
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
                "IMPLEMENTATION QUESTION BUG GREETING GENERIC PLANNING\n\n"
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
        for cat in ["IMPLEMENTATION", "BUG", "PLANNING", "QUESTION", "GREETING", "GENERIC"]:
            if cat in text.upper():
                log(prefix, f"LLM_CLASSIFY result={cat}")
                return cat
    except Exception as e:
        log(prefix, f"LLM_CLASSIFY_FAIL: {e}")
    return None


def get_harness_sh():
    """harness-executor.sh 경로 결정 (프로젝트 우선, 없으면 글로벌)."""
    local = os.path.join(os.getcwd(), ".claude", "harness-executor.sh")
    if os.path.exists(local):
        return local
    globl = os.path.expanduser("~/.claude/harness-executor.sh")
    if os.path.exists(globl):
        return globl
    return None


def run_harness(mode, harness_sh, prefix, issue_num, prompt, extra_args=None):
    """harness-executor.sh를 백그라운드로 실행. 즉시 리턴. 로그 파일 경로 반환."""
    log_file = f"/tmp/{prefix}_harness_output.log"
    args = ['bash', harness_sh, mode,
            '--issue', issue_num,
            '--prefix', prefix,
            '--context', prompt[:400]]
    if extra_args:
        args += extra_args
    with open(log_file, 'w') as lf:
        subprocess.Popen(
            args,
            stdout=lf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=os.getcwd()
        )
    log(prefix, f"HARNESS_POPEN mode={mode} issue={issue_num}")
    return log_file


def main():
    try:
        _main_inner()
    except Exception as e:
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

    prompt = (
        d.get("tool_input", {}).get("prompt", "")
        or d.get("prompt", "")
    )

    if not prompt or not prompt.strip():
        sys.exit(0)

    # stale designer_ran 감지
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
        "designer_ran":           os.path.exists(f"/tmp/{prefix}_designer_ran"),
        "design_critic_passed":   os.path.exists(f"/tmp/{prefix}_design_critic_passed"),
        "test_engineer_passed":   os.path.exists(f"/tmp/{prefix}_test_engineer_passed"),
        "validator_b_passed":     os.path.exists(f"/tmp/{prefix}_validator_b_passed"),
        "pr_reviewer_lgtm":       os.path.exists(f"/tmp/{prefix}_pr_reviewer_lgtm"),
    }
    any_active = any(flags.values())

    # 인사말 → pass-through
    greet_kw = r"^(헤이|안녕|hi|hey|hello|ㅎㅇ|ㅋ+|ㅎ+|응|네|아|오|음|좋아|감사|고마워|ok|okay)[\s!]*$"
    if re.match(greet_kw, prompt.strip(), re.IGNORECASE) and not any_active:
        log(prefix, f"PASS(greeting) prompt={prompt[:60]!r}")
        sys.exit(0)

    # 의도 분류 (regex 1차)
    impl_kw = r"구현|만들어|추가|수정|변경|바꿔|고쳐|삭제|리팩|implement|fix|add|update|src/|루프돌려|만들어보자|구현루프|시작해"
    q_kw    = r"어떻게|뭐야|왜|뭔가요|하나요|인가요|\?"
    bug_kw  = r"버그|뻐그|문제(가| 있| 생겼| 발생)|오류|에러|이상해|이상한데|이상하네|안 돼|안돼|안됨|안되네|고장|깨졌|망가|말이 돼|왜 이래|왜이래|이게 뭐야|버그있다|이슈왔다"
    plan_kw = r"기획|아이디어|뭘.*만들|무엇을.*만들|플랜|로드맵|PRD|TRD|요구사항|스펙"
    ui_kw   = r"화면|컴포넌트|레이아웃|UI|스타일|디자인|색상|애니메이션|오버레이|모달"
    ambiguous = len(prompt.split()) < 5 and not re.search(impl_kw, prompt)

    is_bug  = bool(re.search(bug_kw, prompt, re.IGNORECASE))
    is_ui   = bool(re.search(ui_kw, prompt, re.IGNORECASE))
    is_plan = bool(re.search(plan_kw, prompt, re.IGNORECASE))

    if re.search(impl_kw, prompt):
        cat = "IMPLEMENTATION"
    elif re.search(q_kw, prompt):
        cat = "QUESTION"
    elif is_plan and not any_active:
        cat = "PLANNING"
    elif ambiguous:
        cat = "AMBIGUOUS"
    else:
        cat = "GENERIC"

    # LLM 보조 분류 (AMBIGUOUS/GENERIC일 때만)
    if cat in ("AMBIGUOUS", "GENERIC") and len(prompt.split()) >= 3:
        llm_cat = classify_intent_llm(prompt, prefix)
        if llm_cat:
            log(prefix, f"LLM_OVERRIDE {cat}→{llm_cat}")
            if llm_cat == "BUG":
                is_bug = True
            if llm_cat == "PLANNING":
                cat = "PLANNING"
            else:
                cat = llm_cat

    # QUESTION + 워크플로우 없음 + 버그 아님 → pass-through
    if cat == "QUESTION" and not any_active and not is_bug:
        log(prefix, f"PASS(question/no-active) prompt={prompt[:60]!r}")
        sys.exit(0)

    # AMBIGUOUS + 워크플로우 없음 → product-planner 힌트 (루프 진입 금지)
    if cat == "AMBIGUOUS" and not any_active and not is_bug:
        ctx = (
            "[HARNESS ROUTER] 요청이 모호합니다. 루프 진입 전 명확화 필요.\n\n"
            "구현 수준 모호성 (파일/동작이 불명확):\n"
            "  → 아래 3가지 답변 후 재요청\n"
            "  1. 어떤 파일/컴포넌트가 대상인가?\n"
            "  2. 현재 동작 vs 기대 동작은?\n"
            "  3. 관련 GitHub 이슈 번호가 있는가?\n\n"
            "PRD 수준 모호성 (무엇을 만들지 불명확):\n"
            "  → product-planner 에이전트를 호출하세요 (역질문 → PRD 작성)\n"
            "  → PRD 완료 후 루프 A 진입\n\n"
            "명확한 요청 없이 구현 루프를 시작하지 마세요."
        )
        log(prefix, f"INJECT(ambiguous/product-planner-hint) prompt={prompt[:60]!r}")
        print(json.dumps({"hookSpecificOutput": {"additionalContext": ctx}}))
        sys.exit(0)

    # harness-executor.sh 경로
    harness_sh = get_harness_sh()

    # 이슈 번호 추출 + 이슈 전환 감지
    issue_match   = re.search(r'#(\d+)', prompt)
    current_issue = issue_match.group(0) if issue_match else None
    issue_num     = (current_issue or "N").lstrip('#')
    issue_file    = f"/tmp/{prefix}_current_issue"
    stored_issue  = open(issue_file).read().strip() if os.path.exists(issue_file) else None

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

    flag_lines = "\n".join(
        f"  {'OK' if v else 'NG'} {k}" for k, v in flags.items()
    )

    # ══════════════════════════════════════════════════════════════════
    # runHarnessLoop 라우팅 (S16)
    # ══════════════════════════════════════════════════════════════════

    # BUG → bugfix 루프
    if is_bug and not any_active:
        if harness_sh:
            log_file = run_harness("bugfix", harness_sh, prefix, issue_num, prompt,
                                   ['--bug', prompt[:200]])
            ctx = (
                f"🐛 [HARNESS] bugfix 백그라운드 실행 중 (issue #{issue_num})\n\n"
                f"지금 할 일:\n"
                f"  1. Bash(cat {log_file}) — qa/architect 완료 확인\n"
                f"  2. PLAN_VALIDATION_PASS 확인 후 impl 파일 읽어서 유저에게 보여주기\n"
                f"  3. 승인 후: bash .claude/harness-executor.sh impl2 \\\n"
                f"       --impl $(cat /tmp/{prefix}_impl_path) \\\n"
                f"       --issue {issue_num} --prefix {prefix}"
            )
        else:
            ctx = "🐛 [HARNESS ROUTER] 버그 감지 — harness-executor.sh 없음. QA 에이전트 수동 호출 필요."
        log(prefix, f"INJECT(bugfix/popen) issue={issue_num} prompt={prompt[:60]!r}")
        print(json.dumps({"hookSpecificOutput": {"additionalContext": ctx}}))
        sys.exit(0)

    # PLANNING → plan 루프
    if cat == "PLANNING" and not any_active:
        if harness_sh:
            log_file = run_harness("plan", harness_sh, prefix, issue_num, prompt)
            ctx = (
                f"📋 [HARNESS] plan 백그라운드 실행 중 (issue #{issue_num})\n\n"
                f"지금 할 일:\n"
                f"  1. Bash(cat {log_file}) — product-planner/architect 완료 확인\n"
                f"  2. PLAN_DONE 확인 후 결과 유저에게 보여주기"
            )
        else:
            ctx = "📋 [HARNESS ROUTER] 기획 감지 — harness-executor.sh 없음. product-planner 수동 호출 필요."
        log(prefix, f"INJECT(plan/popen) issue={issue_num} prompt={prompt[:60]!r}")
        print(json.dumps({"hookSpecificOutput": {"additionalContext": ctx}}))
        sys.exit(0)

    # IMPLEMENTATION
    if cat == "IMPLEMENTATION":
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
                            lines = [l for l in patterns.split('\n') if l.strip()][-20:]
                            memory_patterns.append('\n'.join(lines))
                except Exception:
                    pass

        # plan_validation_passed 있음 → impl2 즉시 실행 지시
        if flags["plan_validation_passed"]:
            impl_path_file = f"/tmp/{prefix}_impl_path"
            impl_path = open(impl_path_file).read().strip() if os.path.exists(impl_path_file) else "[IMPL_PATH]"
            ctx = (
                f"🔁 [HARNESS] plan_validation_passed OK\n"
                f"즉시 실행:\n"
                f"bash .claude/harness-executor.sh impl2 \\\n"
                f"  --impl {impl_path} \\\n"
                f"  --issue {current_issue or 'N'} \\\n"
                f"  --prefix {prefix}\n"
                f"\nengineer 직접 호출 금지. 위 스크립트만 사용."
            )
            log(prefix, f"INJECT(impl2/directive) issue={current_issue} prompt={prompt[:60]!r}")

        # plan_validation_passed 없음 → impl 또는 design 백그라운드 실행
        elif harness_sh:
            mode = "design" if is_ui else "impl"
            log_file = run_harness(mode, harness_sh, prefix, issue_num, prompt)
            ctx = (
                f"🔁 [HARNESS] {mode} 백그라운드 실행 중 (issue #{issue_num})\n\n"
                f"지금 할 일:\n"
                f"  1. Bash(cat {log_file}) — architect/validator 완료 확인\n"
                f"  2. PLAN_VALIDATION_PASS / DESIGN_DONE 확인\n"
                f"  3. impl 파일 읽어서 유저에게 보여주고 승인 받기:\n"
                f"     cat $(cat /tmp/{prefix}_impl_path)\n"
                f"  4. 승인 후 impl2 실행:\n"
                f"     bash .claude/harness-executor.sh impl2 \\\n"
                f"       --impl $(cat /tmp/{prefix}_impl_path) \\\n"
                f"       --issue {issue_num} --prefix {prefix}"
            )
            log(prefix, f"INJECT({mode}/popen) issue={issue_num} prompt={prompt[:60]!r}")

        else:
            ctx = (
                f"⚠️ [HARNESS] harness-executor.sh 없음.\n"
                f"수동 실행: bash .claude/harness-executor.sh impl --issue {issue_num} --prefix {prefix}"
            )
            log(prefix, f"INJECT(impl/no-harness) prompt={prompt[:60]!r}")

        if memory_patterns:
            ctx += "\n\n[HARNESS MEMORY] Known Failure Patterns:\n" + "\n---\n".join(memory_patterns)

        active_flags = [k for k, v in flags.items() if v]
        log(prefix, f"active={active_flags}")
        print(json.dumps({"hookSpecificOutput": {"additionalContext": ctx}}))
        sys.exit(0)

    # GENERIC/QUESTION + 워크플로우 활성 → 상태 주입
    if any_active or is_bug:
        ctx = "[HARNESS ROUTER] 진행 중인 워크플로우 있음\n" + flag_lines
        log(prefix, f"INJECT(generic/active) prompt={prompt[:60]!r}")
        print(json.dumps({"hookSpecificOutput": {"additionalContext": ctx}}))
        sys.exit(0)

    # 나머지 → pass-through
    log(prefix, f"PASS(generic/no-active) prompt={prompt[:60]!r}")
    sys.exit(0)


if __name__ == "__main__":
    main()
