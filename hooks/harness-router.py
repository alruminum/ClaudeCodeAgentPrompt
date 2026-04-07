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
import urllib.request
from datetime import datetime

LOG_FILE = "/tmp/harness-router.log"


def log(prefix, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] [{prefix}] {msg}\n")


def fast_classify(prompt):
    """2단계 regex 즉시 분류 — LLM 호출 없이 ~0ms."""
    p = prompt.strip()
    # GREETING — 완전 일치에 가까운 짧은 반응어
    if re.match(r'^(ㅇㅇ|응|네|좋아|좋아요|ok|okay|ㅎㅎ|고마워|감사|알겠어|잘\s*했어|오케이|수고|ㅋ+|ㅎ+|good|great|thanks|thank\s*you|thx|ty|nice|cool|awesome|lgtm|done)[\s!.]*$', p, re.I):
        return "GREETING"
    # BUG — QUESTION보다 먼저 체크 ("수정한거 맞아?" 같은 패턴이 ?로 QUESTION에 빠지는 것 방지)
    if re.search(r'(버그|bug|크래시|crash)', p, re.I) and not re.search(r'(추가|구현|만들)', p):
        return "BUG"
    if re.search(r'(안\s*[되돼]고|안\s*[되돼]요|안\s*됨|깨[졌지]|작동.*안|동작.*안)', p):
        return "BUG"
    # BUG — "여전히/아직/또" + 증상/스크린샷 → 수정 후 재발 리포트
    if re.search(r'(여전히|아직|still|또\s)', p, re.I) and re.search(r'(Image\s*#|스크린샷|보이|나타|표시|노출|남아)', p, re.I):
        return "BUG"
    # BUG — 수정 확인 질문 ("수정한거 맞아/고친됐나/fix됐어 아직")
    if re.search(r'(수정|고친|fix)(한거|된거|됐어|됐나|됐어요).*(맞아|맞나|확인|아직|여전)', p, re.I):
        return "BUG"
    # QUESTION — 물음표로 끝나면 (BUG 패턴에 안 걸린 경우만)
    if re.search(r'\?\s*$', p):
        return "QUESTION"
    # IMPLEMENTATION — 이슈번호 + 명령형 동사 조합
    if re.search(r'#\d+', p) and re.search(r'(구현|수정|추가|만들|해줘|해주세요|하자|진행)', p):
        return "IMPLEMENTATION"
    if re.search(r'(구현|추가|만들어|생성|작성).*해', p) and not re.search(r'^(왜|어떻게|뭐)', p):
        return "IMPLEMENTATION"
    return None  # → LLM 폴백


def _call_haiku(prompt_text, max_tokens, prefix):
    """Haiku 호출 — API 직접(urllib) 우선, 실패 시 --agent socrates CLI 폴백."""
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if api_key:
        try:
            body = json.dumps({
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt_text}]
            }).encode()
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01"
                }
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                result = data["content"][0]["text"].strip()
                log(prefix, f"HAIKU_API_OK len={len(result)}")
                return result
        except Exception as e:
            log(prefix, f"HAIKU_API_FAIL: {e}")

    # CLI 폴백 (OAuth/구독 환경용) — socrates 에이전트로 Haiku 모델 사용
    try:
        env = {**os.environ, 'HARNESS_INTERNAL': '1'}
        result = subprocess.run(
            ['claude', '--agent', 'socrates',
             '--print', '--output-format', 'text',
             '-p', prompt_text],
            env=env, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            log(prefix, "HAIKU_CLI_OK")
            return result.stdout.strip()
    except Exception as e:
        log(prefix, f"HAIKU_CLI_FAIL: {e}")
    return None


def extract_intent(prompt, prefix):
    """PRIMARY 분류기 — Haiku로 유저 의도 추출."""
    prompt_text = (
        "소프트웨어 개발 어시스턴트 채팅에서 사용자 메시지 의도를 분류하라.\n"
        "먼저: 소프트웨어·코딩과 관련 없으면 → GENERIC 또는 GREETING.\n"
        "다음 중 하나만 출력 (다른 말 금지):\n"
        "GREETING — 인사·긍정·짧은 반응 (ㅇㅇ, 응, 좋아, ok, hi, ㅎㅎ, 맞아, 고마워)\n"
        "GENERIC — 소프트웨어와 무관한 모든 것 (날씨, 음식, 일상, 감상, 짧은 단답)\n"
        "QUESTION — 코드·시스템에 대한 질문 (왜, 어떻게, 설명해줘, ?)\n"
        "IMPLEMENTATION — 코드 구현·수정 요청 (이슈 번호, 고쳐, 만들어, fix)\n"
        "BUG — 버그·오류 보고 (버그, 안돼, 이상해, 깨졌어, 에러)\n"
        "AMBIGUOUS — 소프트웨어 요청인 것 같지만 대상·범위 불명확\n\n"
        f"\"{prompt[:200]}\""
    )
    text = _call_haiku(prompt_text, 20, prefix)
    if text:
        for cat in ["IMPLEMENTATION", "BUG", "QUESTION", "GREETING", "AMBIGUOUS", "GENERIC"]:
            if cat in text.upper():
                log(prefix, f"INTENT result={cat}")
                return cat
    return None


def _run_interview_turn(history, original_prompt, prefix):
    """Haiku로 다음 인터뷰 질문 생성. DONE이면 None 반환."""
    if not history:
        content = (
            f"사용자 요청: \"{original_prompt}\"\n\n"
            "이 요청을 구현하기 전에 가장 중요한 첫 번째 명확화 질문 하나를 생성하라.\n"
            "출력 형식: QUESTION: <질문>"
        )
    else:
        qa_text = "\n".join(f"Q{i+1}: {h['q']}\nA{i+1}: {h['a']}" for i, h in enumerate(history))
        content = (
            f"원래 요청: \"{original_prompt}\"\n\n"
            f"지금까지 수집된 요구사항:\n{qa_text}\n\n"
            "구현을 시작하기에 충분한가?\n"
            "충분하면: DONE\n부족하면: QUESTION: <가장 중요한 추가 질문 하나>"
        )
    text = _call_haiku(content, 80, prefix)
    if not text:
        return None
    if "DONE" in text.upper():
        return None
    m = re.search(r'QUESTION:\s*(.+)', text)
    return m.group(1).strip() if m else None


def _load_interview(path, prefix):
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log(prefix, f"INTERVIEW_STATE_PARSE_ERROR: {e}")
        try:
            os.remove(path)
        except OSError:
            pass
        return None


def _save_interview(path, state):
    with open(path, 'w') as f:
        json.dump(state, f)


def _check_invoke_rate(prefix):
    """훅 호출 빈도 체크 — 60초 내 5회 초과 시 블록."""
    MAX_INVOKES = 5
    WINDOW = 60
    rate_file = f"/tmp/{prefix}_hook_rate.json"
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
        try:
            log("?", f"UNCAUGHT: {e}")
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

    # prompt 추출 — tool_input.prompt 또는 최상위 prompt 모두 지원
    prompt = (
        d.get("tool_input", {}).get("prompt", "")
        or d.get("prompt", "")
    )

    # 빈 prompt → 즉시 통과
    if not prompt or not prompt.strip():
        sys.exit(0)

    # Rate Limiter — 60초 내 5회 초과 시 블록
    if not _check_invoke_rate(prefix):
        log(prefix, "RATE_LIMIT_BLOCK — 60초 내 훅 호출 5회 초과")
        sys.exit(0)

    # Kill Switch 체크
    if os.path.exists(f"/tmp/{prefix}_harness_kill"):
        log(prefix, "KILL_SWITCH — pass-through")
        sys.exit(0)

    # 2차 방어: 하네스 내부 생성 프롬프트 패턴 감지
    if _check_harness_internal_prompt(prompt):
        log(prefix, f"PASS(harness_internal_pattern) prompt={prompt[:60]!r}")
        sys.exit(0)

    # 3차 방어: 붙여넣기 콘텐츠 감지 — 로그/대화 기록을 유저 명령으로 오인 방지
    _PASTE_PATTERNS = [
        r'^\[\d{2}:\d{2}:\d{2}\]\s+\[\w+\]\s+',
        r'❯\s+\S.*\n\s+⎿',
        r'\n✶\s',
    ]
    if any(re.search(p, prompt, re.MULTILINE) for p in _PASTE_PATTERNS):
        log(prefix, f"PASS(pasted_content) prompt={prompt[:60]!r}")
        sys.exit(0)

    # mtime 기반 스태일 designer_ran 감지
    dr_path = f"/tmp/{prefix}_designer_ran"
    dc_path = f"/tmp/{prefix}_design_critic_passed"
    if os.path.exists(dr_path) and not os.path.exists(dc_path):
        age_min = (time.time() - os.path.getmtime(dr_path)) / 60
        if age_min > 30:
            os.remove(dr_path)
            log(prefix, f"AUTO_CLEAR stale designer_ran (age={age_min:.0f}min)")

    # executor 경로 감지 (프로젝트 → 글로벌 폴백)
    local_executor = os.path.join(os.getcwd(), ".claude", "harness-executor.sh")
    global_executor = os.path.expanduser("~/.claude/harness-executor.sh")
    executor_path = local_executor if os.path.exists(local_executor) else global_executor

    # 현재 플래그 상태
    flags = {
        "harness_active":         os.path.exists(f"/tmp/{prefix}_harness_active"),
        "plan_validation_passed": os.path.exists(f"/tmp/{prefix}_plan_validation_passed"),
        "designer_ran":           os.path.exists(f"/tmp/{prefix}_designer_ran"),
        "design_critic_passed":   os.path.exists(f"/tmp/{prefix}_design_critic_passed"),
        "test_engineer_passed":   os.path.exists(f"/tmp/{prefix}_test_engineer_passed"),
        "validator_b_passed":     os.path.exists(f"/tmp/{prefix}_validator_b_passed"),
        "pr_reviewer_lgtm":       os.path.exists(f"/tmp/{prefix}_pr_reviewer_lgtm"),
    }
    any_active = any(flags.values())

    # ── 분류 ──────────────────────────────────────────────────────────
    # ≤2자 표현은 API 절약 위해 즉시 GREETING 처리
    interview_path = f"/tmp/{prefix}_interview_state.json"
    if len(prompt.strip()) <= 2:
        cat = "GREETING"
    else:
        cat = fast_classify(prompt)
        if cat:
            log(prefix, f"FAST_CLASSIFY result={cat} prompt={prompt[:60]!r}")
        else:
            cat = extract_intent(prompt, prefix) or "AMBIGUOUS"

    is_bug = (cat == "BUG")

    # 인터뷰 진행 중이면 cat을 AMBIGUOUS로 고정
    if os.path.exists(interview_path) and not any_active and not is_bug:
        cat = "AMBIGUOUS"

    # GREETING → 즉시 통과
    if cat == "GREETING" and not any_active:
        log(prefix, f"PASS(greeting) prompt={prompt[:60]!r}")
        sys.exit(0)

    # QUESTION이고 진행 중인 워크플로우 없으면 통과
    if cat == "QUESTION" and not any_active and not is_bug:
        log(prefix, f"PASS(question/no-active) prompt={prompt[:60]!r}")
        sys.exit(0)

    # AMBIGUOUS + 진행 중 워크플로우 없음 → Adaptive Interview
    if cat == "AMBIGUOUS" and not any_active and not is_bug:
        if os.path.exists(interview_path):
            state = _load_interview(interview_path, prefix)
            if state:
                state['history'].append({'q': state['current_q'], 'a': prompt})
                state['turn'] = state.get('turn', 0) + 1

                if state['turn'] >= 4:
                    next_q = None  # max_turn 하드캡
                    log(prefix, "INTERVIEW_MAX_TURN_REACHED")
                else:
                    next_q = _run_interview_turn(state['history'], state['original'], prefix)

                if next_q is None:
                    # 인터뷰 완료 → plan 힌트 주입 (Popen 아님!)
                    try:
                        os.remove(interview_path)
                    except OSError:
                        pass
                    qa_lines = "\n".join(f"Q: {h['q']}\nA: {h['a']}" for h in state['history'])
                    ctx = (
                        f"✅ [INTERVIEW] 요구사항 수집 완료.\n\n"
                        f"수집된 요구사항:\n{qa_lines}\n\n"
                        f"→ product-planner 에이전트를 호출하세요 (위 요구사항을 컨텍스트로 전달)\n"
                        f"→ PRD 완료 후 루프 A 진입"
                    )
                    log(prefix, f"INJECT(interview/done→plan-hint) prompt={prompt[:60]!r}")
                else:
                    state['current_q'] = next_q
                    _save_interview(interview_path, state)
                    ctx = (
                        "[HARNESS ROUTER] 아래 질문을 한 글자도 수정하지 말고 "
                        "그대로 유저에게 전달하라:\n"
                        f"{next_q}"
                    )
                    log(prefix, f"INJECT(interview/next_q) prompt={prompt[:60]!r}")
            else:
                ctx = "[HARNESS ROUTER] 인터뷰 상태 오류. 요청을 다시 입력해주세요."
                log(prefix, "INJECT(interview/state_error)")
        else:
            # 첫 진입 — 첫 질문 생성
            first_q = _run_interview_turn([], prompt, prefix)
            if first_q:
                state = {'history': [], 'current_q': first_q, 'original': prompt, 'turn': 0}
                _save_interview(interview_path, state)
                ctx = (
                    "[HARNESS ROUTER] 아래 질문을 한 글자도 수정하지 말고 "
                    "그대로 유저에게 전달하라:\n"
                    f"{first_q}"
                )
                log(prefix, f"INJECT(interview/start) prompt={prompt[:60]!r}")
            else:
                # Haiku 실패 → static hint 폴백
                ctx = (
                    "[HARNESS ROUTER] 요청이 모호합니다. 루프 진입 전 명확화 필요.\n\n"
                    "1. 어떤 파일/컴포넌트가 대상인가?\n"
                    "2. 현재 동작 vs 기대 동작은?\n"
                    "3. 관련 GitHub 이슈 번호가 있는가?\n\n"
                    "명확한 요청 없이 구현 루프를 시작하지 마세요."
                )
                log(prefix, f"PASS(ambiguous/no-question) prompt={prompt[:60]!r}")

        print(json.dumps({"hookSpecificOutput": {"additionalContext": ctx}}))
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
                            lines = [l for l in patterns.split('\n') if l.strip()][-20:]
                            memory_patterns.append('\n'.join(lines))
                except Exception:
                    pass

        if flags["harness_active"]:
            ctx = (
                f"⚠️ [HARNESS] harness_active 플래그가 설정되어 있습니다.\n"
                f"이전 실행이 아직 진행 중이거나 비정상 종료된 것일 수 있습니다.\n"
                f"중복 실행 전 확인하세요: ls /tmp/{prefix}_harness_active\n\n"
                f"[현재 플래그]\n{flag_lines}"
            )
            log(prefix, f"INJECT(impl/harness_active_warn) prompt={prompt[:60]!r}")
        elif flags["plan_validation_passed"]:
            impl_path_file = f"/tmp/{prefix}_impl_path"
            impl_path = open(impl_path_file).read().strip() if os.path.exists(impl_path_file) else "[IMPL_PATH]"
            issue_ref = current_issue or "N"
            harness_directive = (
                f"\n\n🔁 [HARNESS ROUTER] plan_validation_passed OK → 아래 Bash 명령을 즉시 실행하라:\n"
                f"bash {executor_path} impl2 --impl {impl_path} --issue {issue_ref} --prefix {prefix}\n"
                "engineer 직접 호출 금지. 위 스크립트가 루프를 완주한다.\n"
                "⚠️ 반드시 포어그라운드로 실행 (run_in_background 금지)."
            )
            ctx = (
                "[HARNESS ROUTER] 현재 워크플로우 상태\n"
                + flag_lines
                + "\n\n요청 분류: IMPLEMENTATION"
                + harness_directive
            )
            log(prefix, f"INJECT(impl/impl2) issue={current_issue} prompt={prompt[:60]!r}")
        else:
            harness_directive = (
                "\n\n⚠️ src/** 직접 Edit/Write 금지. engineer 에이전트 직접 호출 금지.\n"
                f"올바른 순서: Bash로 harness-executor.sh 호출.\n"
                f"예: bash {executor_path} impl --impl [IMPL_PATH] --issue {current_issue or 'N'} --prefix {prefix}\n"
                "⚠️ 반드시 포어그라운드로 실행 (run_in_background 금지)."
            )
            ctx = (
                "[HARNESS ROUTER] 현재 워크플로우 상태\n"
                + flag_lines
                + "\n\n요청 분류: IMPLEMENTATION"
                + harness_directive
            )
            log(prefix, f"INJECT(impl) issue={current_issue} prompt={prompt[:60]!r}")

        if memory_patterns:
            ctx += "\n\n[HARNESS MEMORY] Known Failure Patterns:\n" + "\n---\n".join(memory_patterns)
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
