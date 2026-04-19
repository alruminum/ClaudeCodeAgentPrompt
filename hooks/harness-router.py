#!/usr/bin/env python3
"""
Harness Router — UserPromptSubmit hook
Usage: python3 harness-router.py <PREFIX>
  PREFIX: project-specific flag prefix (e.g. "mb" → .claude/harness-state/.flags/mb_plan_validation_passed)

3카테고리 분류: BUG / UI / IMPLEMENTATION → 힌트 주입
나머지 → 즉시 통과 (스킬이 정밀 라우팅 담당)
"""
import sys
import json
import os
import re
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness_common import get_state_dir, get_flags_dir, FLAGS

LOG_FILE = "/tmp/harness-router.log"


def log(prefix, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] [{prefix}] {msg}\n")


def fast_classify(prompt):
    """BUG / UI / IMPLEMENTATION만 잡고 나머지는 None (통과)."""
    p = prompt.strip()

    # 시스템 알림, 슬래시 커맨드 → 즉시 통과
    if re.match(r'^<(task-notification|system-reminder)', p):
        return None
    if re.match(r'^/\w', p) and not re.match(r'^/(Users|tmp|var|etc|opt|home)', p):
        return None

    # ── BUG ──
    if re.search(r'(버그|bug|크래시|crash)', p, re.I) and not re.search(r'(추가|구현|만들)', p):
        return "BUG"
    if re.search(r'(안\s*[되돼]고|안\s*[되돼]요|안\s*됨|깨[졌지]|작동.*안|동작.*안)', p):
        return "BUG"
    if re.search(r'(에러|error|실패|fail|터[졌지]|죽[었었]|뻗[었었])', p, re.I) and not re.search(r'(추가|구현|만들)', p):
        return "BUG"
    if re.search(r'(여전히|아직|still|또\s)', p, re.I) and re.search(r'(Image\s*#|스크린샷|보이|나타|표시|노출|남아)', p, re.I):
        return "BUG"
    if re.search(r'(수정|고친|fix)(한거|된거|됐어|됐나|됐어요).*(맞아|맞나|확인|아직|여전)', p, re.I):
        return "BUG"
    if re.search(r'(이슈|issue).*(수정|고치|고쳐|fix)', p, re.I):
        return "BUG"
    if re.search(r'(고\s*있는데|이는데|하는데).*(야\s*할\s*것\s*같|해야\s*할|멈춰야|되어야|돼야)', p):
        return "BUG"
    if re.search(r'(발생해|발생하고|발생함|발생한다|발생중)', p) and not re.search(r'(추가|구현|만들)', p):
        return "BUG"
    if re.search(r'(아무것도\s*안\s*나|화면.*아무것도|안\s*나[와온]\s*)', p):
        return "BUG"

    # ── UI ── (/ux 스킬 보조)
    if re.search(r'(디자인|시안|UX|레이아웃|화면\s*개선|모양\s*바꿔|UI)', p, re.I) and not re.search(r'(버그|에러|안\s*[되돼])', p):
        return "UI"

    # ── IMPLEMENTATION ──
    if re.search(r'#\d+', p) and re.search(r'(구현|수정|추가|만들|해줘|해주세요|하자|진행)', p):
        return "IMPLEMENTATION"
    if re.search(r'(구현|추가|만들어|생성|작성).*해', p) and not re.search(r'^(왜|어떻게|뭐)', p):
        return "IMPLEMENTATION"
    if re.search(r'(실행|돌려|재실행|적용|배포|빌드|테스트|커밋|푸시).*(해봐|해줘|하자|해|봐)\s*$', p):
        return "IMPLEMENTATION"
    if re.search(r'(삭제|지워|제거|정리|없애|날려).*(해|봐|줘|하자)?\s*$', p):
        return "IMPLEMENTATION"
    if re.search(r'(다시|재)\s*(시도|실행|돌려|해봐|해줘|시작)', p):
        return "IMPLEMENTATION"
    if re.search(r'(수정|고[쳤친]|fix).*(다시|시도|실행|돌려|해봐)', p, re.I):
        return "IMPLEMENTATION"
    if re.search(r'(띄워|올려|내려|꺼줘|죽여|kill|start|stop).*(줘|봐|라|해)?\s*$', p) and re.search(r'(서버|포트|\d{4}|dev|build)', p, re.I):
        return "IMPLEMENTATION"

    return None  # 나머지 → 통과


def _check_invoke_rate(prefix):
    """훅 호출 빈도 체크 — 60초 내 5회 초과 시 블록."""
    MAX_INVOKES = 5
    WINDOW = 60
    rate_file = f"{get_state_dir()}/{prefix}_hook_rate.json"
    now = time.time()
    try:
        data = json.load(open(rate_file)) if os.path.exists(rate_file) else {"count": 0, "window_start": now}
        if now - data["window_start"] > WINDOW:
            data = {"count": 0, "window_start": now}
        data["count"] += 1
        with open(rate_file, "w") as f:
            json.dump(data, f)
        return data["count"] <= MAX_INVOKES
    except Exception:
        return True


def _check_harness_internal_prompt(prompt):
    """하네스 내부에서 생성된 프롬프트 패턴 — HARNESS_INTERNAL 실패 시 2차 방어선."""
    patterns = [
        r'^bug:.*issue:\s*#',
        r'^impl:.*issue:\s*#.*task:',
        r'^Mode\s+[ABCE]\b',
        r'^SPEC_GAP\(',
        r'^System Design\(Mode',
        r'^Module Plan\(Mode',
        r'^구현된 파일:',
        r'^변경 내용 리뷰:',
        r'^보안 리뷰 대상',
        r'^Mode\s+[BC]\s*[-—]\s*',
    ]
    return any(re.match(p, prompt.strip(), re.DOTALL | re.IGNORECASE) for p in patterns)


def main():
    try:
        _main_inner()
    except Exception as e:
        import traceback
        try:
            log("?", f"UNCAUGHT: {e}\n{traceback.format_exc()}")
        except Exception:
            pass
        sys.exit(0)


def _main_inner():
    # 1차 방어: HARNESS_INTERNAL env var — 내부 agent 호출 재트리거 방지
    if os.environ.get('HARNESS_INTERNAL') == '1':
        sys.exit(0)

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

    # Rate Limiter
    if not _check_invoke_rate(prefix):
        log(prefix, "RATE_LIMIT_BLOCK")
        sys.exit(0)

    # Kill Switch — Phase 3: 전역 신호 + 레거시 플래그 파일
    try:
        import session_state as _ss
        if _ss.get_global_signal().get("harness_kill"):
            log(prefix, "KILL_SWITCH(global) — pass-through")
            sys.exit(0)
    except ImportError:
        pass
    if os.path.exists(f"{get_flags_dir()}/{prefix}_{FLAGS.HARNESS_KILL}"):
        log(prefix, "KILL_SWITCH(legacy) — pass-through")
        sys.exit(0)

    # 2차 방어: 하네스 내부 생성 프롬프트 패턴
    if _check_harness_internal_prompt(prompt):
        log(prefix, f"PASS(harness_internal) prompt={prompt[:60]!r}")
        sys.exit(0)

    # 3차 방어: 붙여넣기 콘텐츠 감지
    _PASTE_PATTERNS = [
        r'^\[\d{2}:\d{2}:\d{2}\]\s+\[\w+\]\s+',
        r'❯\s+\S.*\n\s+⎿',
        r'\n✶\s',
    ]
    if any(re.search(p, prompt, re.MULTILINE) for p in _PASTE_PATTERNS):
        log(prefix, f"PASS(pasted_content) prompt={prompt[:60]!r}")
        sys.exit(0)

    # 이슈 번호 추출 → 이슈별 플래그 디렉토리 사용 (worktree 격리 지원)
    _issue_m = re.search(r'#(\d+)', prompt)
    _issue_for_flags = _issue_m.group(1) if _issue_m else ""
    _fdir = get_flags_dir(_issue_for_flags)
    # 이슈별 디렉토리가 없으면 글로벌 fallback
    if _issue_for_flags and not os.path.isdir(_fdir):
        _fdir = get_flags_dir()

    # stale designer_ran 감지
    dr_path = f"{_fdir}/{prefix}_{FLAGS.DESIGNER_RAN}"
    dc_path = f"{_fdir}/{prefix}_{FLAGS.DESIGN_CRITIC_PASSED}"
    if os.path.exists(dr_path) and not os.path.exists(dc_path):
        age_min = (time.time() - os.path.getmtime(dr_path)) / 60
        if age_min > 30:
            os.remove(dr_path)
            log(prefix, f"AUTO_CLEAR stale {FLAGS.DESIGNER_RAN} (age={age_min:.0f}min)")

    # executor 경로
    local_executor = os.path.join(os.getcwd(), ".claude", "harness/executor.py")
    global_executor = os.path.expanduser("~/.claude/harness/executor.py")
    executor_path = local_executor if os.path.exists(local_executor) else global_executor

    # 현재 플래그 상태
    flags = {
        FLAGS.HARNESS_ACTIVE:         os.path.exists(f"{_fdir}/{prefix}_{FLAGS.HARNESS_ACTIVE}"),
        FLAGS.PLAN_VALIDATION_PASSED: os.path.exists(f"{_fdir}/{prefix}_{FLAGS.PLAN_VALIDATION_PASSED}"),
        FLAGS.DESIGNER_RAN:           os.path.exists(f"{_fdir}/{prefix}_{FLAGS.DESIGNER_RAN}"),
        FLAGS.DESIGN_CRITIC_PASSED:   os.path.exists(f"{_fdir}/{prefix}_{FLAGS.DESIGN_CRITIC_PASSED}"),
        FLAGS.TEST_ENGINEER_PASSED:   os.path.exists(f"{_fdir}/{prefix}_{FLAGS.TEST_ENGINEER_PASSED}"),
        FLAGS.VALIDATOR_B_PASSED:     os.path.exists(f"{_fdir}/{prefix}_{FLAGS.VALIDATOR_B_PASSED}"),
        FLAGS.PR_REVIEWER_LGTM:       os.path.exists(f"{_fdir}/{prefix}_{FLAGS.PR_REVIEWER_LGTM}"),
    }
    any_active = any(flags.values())

    # ── 분류 ──
    cat = fast_classify(prompt)
    log(prefix, f"CLASSIFY result={cat} prompt={prompt[:60]!r}")

    # None → 즉시 통과 (스킬이 정밀 라우팅)
    if cat is None:
        if not any_active:
            log(prefix, f"PASS prompt={prompt[:60]!r}")
            sys.exit(0)
        # 워크플로우 진행 중이면 플래그 상태만 전달
        flag_lines = "\n".join(f"  {'OK' if v else 'NG'} {k}" for k, v in flags.items())
        ctx = "[HARNESS ROUTER] 진행 중인 워크플로우 있음\n" + flag_lines
        log(prefix, f"INJECT(active-flags) prompt={prompt[:60]!r}")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}))
        sys.exit(0)

    is_bug = (cat == "BUG")
    flag_lines = "\n".join(f"  {'OK' if v else 'NG'} {k}" for k, v in flags.items())

    # ── BUG → QA 먼저 ──
    if is_bug:
        ctx = (
            "🐛 [HARNESS ROUTER] 버그/이슈 감지\n"
            "→ QA 에이전트를 반드시 먼저 호출하세요. 자체 분석 금지.\n"
            "→ 이슈 생성도 QA 담당. 메인 Claude의 gh issue create / gh api .../issues 직접 호출 금지.\n"
            f"→ QA 완료 후: python3 {executor_path} impl --issue <N> --prefix {prefix}\n"
        )
        log(prefix, f"INJECT(bug) prompt={prompt[:60]!r}")

    # ── UI → ux 스킬 ──
    elif cat == "UI":
        ctx = (
            "🎨 [HARNESS ROUTER] UI/디자인 변경 감지\n"
            "→ /ux 스킬을 사용하세요. designer 에이전트가 Pencil MCP로 시안을 생성합니다.\n"
            "→ 코드 직접 수정 금지. 디자인 확정 후 engineer가 구현합니다.\n"
        )
        log(prefix, f"INJECT(ui) prompt={prompt[:60]!r}")

    # ── IMPLEMENTATION → 플래그 + executor 힌트 ──
    elif cat == "IMPLEMENTATION":
        # 이슈 전환 시 플래그 초기화
        issue_match = re.search(r'#(\d+)', prompt)
        current_issue = issue_match.group(0) if issue_match else None
        issue_file = f"{get_state_dir()}/{prefix}_current_issue"
        stored_issue = open(issue_file).read().strip() if os.path.exists(issue_file) else None
        if current_issue and stored_issue != current_issue:
            all_flag_keys = [
                FLAGS.PLAN_VALIDATION_PASSED, FLAGS.DESIGNER_RAN, FLAGS.DESIGN_CRITIC_PASSED,
                FLAGS.TEST_ENGINEER_PASSED, FLAGS.VALIDATOR_B_PASSED, FLAGS.PR_REVIEWER_LGTM
            ]
            cleared = []
            for f in all_flag_keys:
                p = f"{_fdir}/{prefix}_{f}"
                if os.path.exists(p):
                    os.remove(p)
                    cleared.append(f)
                flags[f] = False
            open(issue_file, 'w').write(current_issue)
            log(prefix, f"TASK_SWITCH {stored_issue}→{current_issue}: cleared={cleared}")
            flag_lines = "\n".join(f"  {'OK' if v else 'NG'} {k}" for k, v in flags.items())

        # harness-memory Known Failure Patterns
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
                        patterns_text = m.group(1).strip()
                        if patterns_text:
                            lines = [l for l in patterns_text.split('\n') if l.strip()][-20:]
                            memory_patterns.append('\n'.join(lines))
                except Exception:
                    pass

        if flags[FLAGS.HARNESS_ACTIVE]:
            ctx = (
                f"⚠️ [HARNESS] {FLAGS.HARNESS_ACTIVE} 플래그 설정됨.\n"
                f"이전 실행이 진행 중이거나 비정상 종료됨.\n"
                f"중복 실행 전 확인: ls {_fdir}/{prefix}_{FLAGS.HARNESS_ACTIVE}\n\n"
                f"[현재 플래그]\n{flag_lines}"
            )
            log(prefix, f"INJECT(impl/harness_active_warn) prompt={prompt[:60]!r}")
        elif flags[FLAGS.PLAN_VALIDATION_PASSED]:
            impl_path_file = f"{get_state_dir()}/{prefix}_impl_path"
            impl_path = open(impl_path_file).read().strip() if os.path.exists(impl_path_file) else "[IMPL_PATH]"
            issue_ref = current_issue or "N"
            ctx = (
                "[HARNESS ROUTER] 현재 워크플로우 상태\n" + flag_lines +
                f"\n\n🔁 plan_validation_passed OK → 아래 Bash 명령을 즉시 실행하라:\n"
                f"python3 {executor_path} impl --impl {impl_path} --issue {issue_ref} --prefix {prefix}\n"
                "engineer 직접 호출 금지. 위 스크립트가 루프를 완주한다.\n"
                "⚠️ 반드시 포어그라운드로 실행 (run_in_background 금지)."
            )
            log(prefix, f"INJECT(impl/reentry) issue={current_issue} prompt={prompt[:60]!r}")
        else:
            ctx = (
                "[HARNESS ROUTER] 현재 워크플로우 상태\n" + flag_lines +
                "\n\n⚠️ src/** 직접 Edit/Write 금지. engineer 에이전트 직접 호출 금지.\n"
                f"올바른 순서: python3 {executor_path} impl --impl [IMPL_PATH] --issue {current_issue or 'N'} --prefix {prefix}\n"
                "⚠️ 반드시 포어그라운드로 실행 (run_in_background 금지)."
            )
            log(prefix, f"INJECT(impl) issue={current_issue} prompt={prompt[:60]!r}")

        if memory_patterns:
            ctx += "\n\n[HARNESS MEMORY] Known Failure Patterns:\n" + "\n---\n".join(memory_patterns)

    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}))


if __name__ == "__main__":
    main()
