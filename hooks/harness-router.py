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

def extract_intent(prompt, prefix):
    """
    PRIMARY 분류기 — Haiku로 유저 의도 추출.
    반환: GREETING | QUESTION | IMPLEMENTATION | BUG | AMBIGUOUS | GENERIC
    실패 시: None (호출자에서 AMBIGUOUS 폴백)
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return None
    try:
        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 20,
            "messages": [{"role": "user", "content":
                "소프트웨어 개발 어시스턴트 채팅에서 사용자 메시지를 분류하라.\n"
                "먼저: 소프트웨어·코딩과 관련 없으면 → GENERIC 또는 GREETING.\n"
                "다음 중 하나만 출력 (다른 말 금지):\n"
                "GREETING — 인사·긍정·짧은 반응·감탄 (ㅇㅇ, 응, 좋아, ok, hi, ㅎㅎ, 맞아, 고마워, 알겠어)\n"
                "GENERIC — 소프트웨어와 무관한 모든 것 (날씨, 음식, 일상, 감상, 짧은 단답)\n"
                "QUESTION — 코드·시스템에 대한 질문 (왜, 어떻게, 설명해줘, ?)\n"
                "IMPLEMENTATION — 코드 구현·수정 요청 (이슈 번호 포함, 구체적 기능 변경)\n"
                "BUG — 버그·오류 보고 (버그, 안돼, 이상해, 깨졌어, 에러)\n"
                "AMBIGUOUS — 소프트웨어 요청인 것 같지만 대상·범위 불명확\n\n"
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
        for cat in ["IMPLEMENTATION", "BUG", "QUESTION", "GREETING", "AMBIGUOUS", "GENERIC"]:
            if cat in text.upper():
                log(prefix, f"INTENT result={cat}")
                return cat
    except Exception as e:
        log(prefix, f"INTENT_FAIL: {e}")
    return None


def run_interview_turn(history, original_prompt, prefix):
    """
    Haiku로 다음 인터뷰 질문 생성 (적응형).
    - history 비어있으면: 첫 질문 생성
    - history 있으면: 충분하면 None(DONE), 부족하면 다음 질문 문자열 반환
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return None

    if not history:
        content = (
            f"사용자 요청: \"{original_prompt}\"\n\n"
            "이 요청을 구현하기 전에 가장 중요한 첫 번째 명확화 질문 하나를 생성하라.\n"
            "출력 형식: QUESTION: <질문>"
        )
    else:
        qa_text = "\n".join(
            f"Q{i+1}: {h['q']}\nA{i+1}: {h['a']}"
            for i, h in enumerate(history)
        )
        content = (
            f"원래 요청: \"{original_prompt}\"\n\n"
            f"지금까지 수집된 요구사항:\n{qa_text}\n\n"
            "구현을 시작하기에 충분한가?\n"
            "충분하면: DONE\n"
            "부족하면: QUESTION: <가장 중요한 추가 질문 하나>"
        )

    try:
        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 80,
            "messages": [{"role": "user", "content": content}]
        })
        result = subprocess.run(
            ['curl', '-s', '-m', '15',
             'https://api.anthropic.com/v1/messages',
             '-H', f'x-api-key: {api_key}',
             '-H', 'anthropic-version: 2023-06-01',
             '-H', 'content-type: application/json',
             '-d', payload],
            capture_output=True, text=True, timeout=17
        )
        text = json.loads(result.stdout)['content'][0]['text'].strip()
        if 'DONE' in text.upper():
            log(prefix, "INTERVIEW_DONE")
            return None
        if 'QUESTION:' in text:
            q = text.split('QUESTION:', 1)[1].strip()
            log(prefix, f"INTERVIEW_Q: {q[:60]}")
            return q
    except Exception as e:
        log(prefix, f"INTERVIEW_FAIL: {e}")
    return None  # Haiku 실패 → DONE 처리 (static hint fallback으로 이어짐)


HARNESS_LOCK_TTL = 120  # seconds — 이 시간 동안 갱신 없으면 stale로 판단


def get_harness_sh():
    """harness-executor.sh 경로 — 프로젝트 로컬 우선, 없으면 글로벌."""
    local = os.path.join(os.getcwd(), ".claude", "harness-executor.sh")
    if os.path.exists(local):
        return local
    globl = os.path.expanduser("~/.claude/harness-executor.sh")
    return globl if os.path.exists(globl) else None


def _lease_age(lock_path):
    """JSON lease의 heartbeat 기준 경과 시간(초). 파싱 실패 시 mtime fallback."""
    try:
        with open(lock_path) as f:
            lease = json.load(f)
        return time.time() - lease["heartbeat"]
    except (json.JSONDecodeError, KeyError, OSError):
        return time.time() - os.path.getmtime(lock_path)


def try_spawn_harness(mode, harness_sh, prefix, issue_num, extra_args=None):
    """
    harness-executor.sh를 백그라운드로 1회만 spawn.
    - Atomic O_CREAT|O_EXCL: race condition 방지 (OS 커널 보장)
    - TTL 120s: stale lock 자동 해제 (크래시 후 복구)
    반환값: log_file 경로(spawn 성공) 또는 None(이미 실행 중)
    """
    lock = f"/tmp/{prefix}_harness_active"

    # 0. Spawn rate limiter — 60초 내 3회 초과 시 하드 블록 (재귀 루프 최후 방어)
    if not _check_spawn_rate(prefix):
        log(prefix, f"RATE_LIMIT_BLOCK mode={mode} — 60초 내 spawn 3회 초과")
        return None

    # 1. TTL 체크 — JSON lease heartbeat 기준 120초 초과 시 stale로 판단하고 제거
    if os.path.exists(lock):
        age = _lease_age(lock)
        if age < HARNESS_LOCK_TTL:
            log(prefix, f"SKIP(already_active age={age:.0f}s) mode={mode}")
            return None  # 진짜 실행 중 → spawn 금지
        # stale lock → 제거 후 계속
        try:
            os.remove(lock)
            log(prefix, f"STALE_LOCK_REMOVED age={age:.0f}s mode={mode}")
        except OSError:
            return None  # 다른 프로세스가 먼저 제거 중 → 안전하게 skip

    # 2. Atomic create — O_CREAT|O_EXCL: 파일이 이미 있으면 즉시 FileExistsError
    #    두 UserPromptSubmit이 동시에 도달해도 하나만 통과 (커널 레벨 보장)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.close(fd)
    except FileExistsError:
        log(prefix, f"SKIP(race_lost) mode={mode}")
        return None

    # 3. Spawn
    log_file = f"/tmp/{prefix}_harness_output.log"
    args = ["bash", harness_sh, mode,
            "--issue", str(issue_num),
            "--prefix", prefix]
    if extra_args:
        args += extra_args
    try:
        with open(log_file, "w") as lf:
            subprocess.Popen(
                args,
                stdout=lf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                cwd=os.getcwd()
            )
        log(prefix, f"SPAWNED mode={mode} issue={issue_num} lock={lock}")
    except Exception as e:
        # spawn 실패 시 lock 해제
        try:
            os.remove(lock)
        except OSError:
            pass
        log(prefix, f"SPAWN_FAILED mode={mode} err={e}")
        return None

    return log_file


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

def _check_harness_internal_prompt(prompt):
    """하네스 내부에서 생성된 프롬프트 패턴 — HARNESS_INTERNAL 실패 시 2차 방어선."""
    patterns = [
        r'^bug:.*issue:\s*#',           # _agent_call qa: "bug: ... issue: #N"
        r'^impl:.*issue:\s*#.*task:',   # _agent_call engineer
        r'^Mode\s+[ABCE]\b',            # architect 호출
        r'^SPEC_GAP\(',                 # architect SPEC_GAP
        r'^System Design\(Mode',        # architect Mode A
        r'^Module Plan\(Mode',          # architect Mode B
        r'^구현된 파일:',                # test-engineer
        r'^변경 내용 리뷰:',             # pr-reviewer
        r'^보안 리뷰 대상',              # security-reviewer
        r'^Mode\s+[BC]\s*[-—]\s*',     # validator
    ]
    return any(re.match(p, prompt.strip(), re.DOTALL | re.IGNORECASE) for p in patterns)


def _check_spawn_rate(prefix):
    """
    Spawn rate limiter — 60초 내 MAX_SPAWNS 초과 시 하드 블록.
    재귀 루프 폭주 방지용 최후 방어선.
    """
    MAX_SPAWNS = 3
    WINDOW = 60  # seconds
    rate_file = f"/tmp/{prefix}_spawn_rate.json"
    now = time.time()
    try:
        data = json.load(open(rate_file)) if os.path.exists(rate_file) else {"count": 0, "window_start": now}
        if now - data["window_start"] > WINDOW:
            data = {"count": 0, "window_start": now}
        data["count"] += 1
        with open(rate_file, "w") as f:
            json.dump(data, f)
        return data["count"] <= MAX_SPAWNS
    except Exception:
        return True  # 파일 오류 시 허용 (기능 장애보다 과금이 낫다)


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

    # 2차 방어: 하네스 내부 생성 프롬프트 패턴 감지 — HARNESS_INTERNAL 실패 시 백업
    if _check_harness_internal_prompt(prompt):
        log(raw_prefix if raw_prefix != "auto" else "?", f"PASS(harness_internal_pattern) prompt={prompt[:60]!r}")
        sys.exit(0)

    # 3차 방어: 붙여넣기 콘텐츠 감지 — 로그/대화 기록을 유저 명령으로 오인 방지
    _PASTE_PATTERNS = [
        r'^\[\d{2}:\d{2}:\d{2}\]\s+\[\w+\]\s+',   # [HH:MM:SS] [prefix] 로그 라인
        r'❯\s+\S.*\n\s+⎿',                           # Claude Code UI 대화 기록 (❯ + ⎿)
        r'\n✶\s',                                      # 어시스턴트 턴 마커
    ]
    if any(re.search(p, prompt, re.MULTILINE) for p in _PASTE_PATTERNS):
        log(raw_prefix if raw_prefix != "auto" else "?", f"PASS(pasted_content) prompt={prompt[:60]!r}")
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
        "harness_active":         os.path.exists(f"/tmp/{prefix}_harness_active"),
        "plan_validation_passed": os.path.exists(f"/tmp/{prefix}_plan_validation_passed"),
        "designer_ran":           os.path.exists(f"/tmp/{prefix}_designer_ran"),
        "design_critic_passed":   os.path.exists(f"/tmp/{prefix}_design_critic_passed"),
        "test_engineer_passed":   os.path.exists(f"/tmp/{prefix}_test_engineer_passed"),
        "validator_b_passed":     os.path.exists(f"/tmp/{prefix}_validator_b_passed"),
        "pr_reviewer_lgtm":       os.path.exists(f"/tmp/{prefix}_pr_reviewer_lgtm"),
    }
    any_active = any(flags.values())

    # ── LLM PRIMARY 분류 ─────────────────────────────────────────────
    # ≤2자 표현은 API 절약 위해 즉시 GREETING 처리 (ㅇㅇ, 응, 네, ok 등)
    interview_path = f"/tmp/{prefix}_interview_state.json"
    if len(prompt.strip()) <= 2:
        cat = "GREETING"
    else:
        cat = extract_intent(prompt, prefix) or "AMBIGUOUS"

    is_bug = (cat == "BUG")

    # 인터뷰 진행 중이면 cat을 AMBIGUOUS로 고정
    if os.path.exists(interview_path) and not any_active and not is_bug:
        cat = "AMBIGUOUS"

    # GREETING → 즉시 통과
    if cat == "GREETING" and not any_active:
        log(prefix, f"PASS(greeting/llm) prompt={prompt[:60]!r}")
        sys.exit(0)

    # QUESTION이고 진행 중인 워크플로우 없으면 아무것도 주입 안 함 (버그 감지 시 예외)
    if cat == "QUESTION" and not any_active and not is_bug:
        log(prefix, f"PASS(question/no-active) prompt={prompt[:60]!r}")
        sys.exit(0)

    # AMBIGUOUS + 진행 중 워크플로우 없음 → S18 Adaptive Interview Harness
    if cat == "AMBIGUOUS" and not any_active and not is_bug:
        if os.path.exists(interview_path):
            # 진행 중인 인터뷰 — 이 메시지는 답변
            try:
                with open(interview_path) as f:
                    state = json.load(f)
            except (json.JSONDecodeError, OSError):
                try:
                    os.remove(interview_path)
                except OSError:
                    pass
                state = None

            if state:
                state['history'].append({'q': state['current_q'], 'a': prompt})
                state['turn'] = state.get('turn', 0) + 1

                # max_turn=4 하드캡 — Haiku가 DONE을 안 내도 강제 종료
                if state['turn'] >= 4:
                    next_q = None
                    log(prefix, "INTERVIEW_MAX_TURN_REACHED")
                else:
                    next_q = run_interview_turn(state['history'], state['original'], prefix)

                if next_q is None:
                    # 인터뷰 완료 → plan spawn
                    try:
                        os.remove(interview_path)
                    except OSError:
                        pass
                    qa_lines = "\n".join(
                        f"Q: {h['q']}\nA: {h['a']}" for h in state['history']
                    )
                    qa_ctx = f"원래요청: {state['original']}\n\n{qa_lines}"
                    harness_sh = get_harness_sh()
                    log_file = (try_spawn_harness("plan", harness_sh, prefix, "N",
                                                  ["--context", qa_ctx])
                                if harness_sh else None)
                    fallback_log = f"/tmp/{prefix}_harness_output.log"
                    watch_sh = os.path.expanduser("~/.claude/harness-watch.sh")
                    actual_log = log_file or fallback_log
                    ctx = (
                        f"✅ [INTERVIEW] 요구사항 수집 완료. 계획 수립 시작.\n"
                        f"[액션] 지금 즉시 Bash 도구로 실행하라 (timeout=660000):\n"
                        f"bash {watch_sh} {actual_log}"
                    )
                    log(prefix, f"INJECT(interview/done→plan) prompt={prompt[:60]!r}")
                else:
                    state['current_q'] = next_q
                    with open(interview_path, 'w') as f:
                        json.dump(state, f)
                    ctx = f"[INTERVIEW] {next_q}"
                    log(prefix, f"INJECT(interview/next_q) prompt={prompt[:60]!r}")
            else:
                # 파싱 실패 → 첫 질문부터 재시작
                ctx = "[HARNESS ROUTER] 인터뷰 상태 오류. 요청을 다시 입력해주세요."
                log(prefix, "INJECT(interview/state_error)")
        else:
            # 첫 진입 — 첫 질문 생성
            first_q = run_interview_turn([], prompt, prefix)
            if first_q:
                state = {'history': [], 'current_q': first_q, 'original': prompt, 'turn': 0}
                with open(interview_path, 'w') as f:
                    json.dump(state, f)
                ctx = f"[INTERVIEW] {first_q}"
                log(prefix, f"INJECT(interview/start) prompt={prompt[:60]!r}")
            else:
                # Haiku 실패 → static hint fallback
                ctx = (
                    "[HARNESS ROUTER] 요청이 모호합니다. 루프 진입 전 명확화 필요.\n\n"
                    "1. 어떤 파일/컴포넌트가 대상인가?\n"
                    "2. 현재 동작 vs 기대 동작은?\n"
                    "3. 관련 GitHub 이슈 번호가 있는가?\n\n"
                    "명확한 요청 없이 구현 루프를 시작하지 마세요."
                )
                log(prefix, f"INJECT(ambiguous/fallback) prompt={prompt[:60]!r}")

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
                            # 최근 20개 항목만 유지 (컨텍스트 낭비 방지)
                            lines = [l for l in patterns.split('\n') if l.strip()][-20:]
                            memory_patterns.append('\n'.join(lines))
                except Exception:
                    pass

        issue_ref = (current_issue or "N").lstrip("#")
        harness_sh = get_harness_sh()

        if flags["harness_active"]:
            # 이미 실행 중 → spawn 금지, 로그 확인 안내만
            log_file = f"/tmp/{prefix}_harness_output.log"
            watch_sh = os.path.expanduser("~/.claude/harness-watch.sh")
            ctx = (
                f"⏳ [HARNESS] 이미 실행 중입니다. 중복 실행 금지.\n"
                f"[액션] 지금 즉시 Bash 도구로 실행하라 (timeout=660000):\n"
                f"bash {watch_sh} {log_file}\n\n"
                f"[현재 플래그]\n{flag_lines}"
            )
            log(prefix, f"INJECT(impl/already_active) prompt={prompt[:60]!r}")
        elif harness_sh:
            # spawn 시도
            if flags["plan_validation_passed"]:
                impl_path_file = f"/tmp/{prefix}_impl_path"
                impl_path = open(impl_path_file).read().strip() if os.path.exists(impl_path_file) else ""
                if impl_path:
                    extra = ["--impl", impl_path]
                    log_file = try_spawn_harness("impl2", harness_sh, prefix, issue_ref, extra)
                    mode_label = "impl2"
                else:
                    # impl_path 없음 → plan_validation_passed 스테일 → impl로 강등
                    try:
                        os.remove(f"/tmp/{prefix}_plan_validation_passed")
                    except OSError:
                        pass
                    log(prefix, "STALE_PLAN_VALIDATION: impl_path missing → downgrade impl")
                    log_file = try_spawn_harness("impl", harness_sh, prefix, issue_ref)
                    mode_label = "impl"
            else:
                log_file = try_spawn_harness("impl", harness_sh, prefix, issue_ref)
                mode_label = "impl"

            if log_file:
                watch_sh = os.path.expanduser("~/.claude/harness-watch.sh")
                ctx = (
                    f"🔁 [HARNESS] {mode_label} 루프 실행 시작 (issue #{issue_ref})\n"
                    f"[액션] 지금 즉시 Bash 도구로 실행하라 (timeout=660000):\n"
                    f"bash {watch_sh} {log_file}\n"
                    f"HARNESS_DONE / ESCALATE / PASS 메시지 확인 후 유저에게 결과를 한국어로 보고하라.\n\n"
                    f"[현재 플래그]\n{flag_lines}"
                )
            else:
                log_file = f"/tmp/{prefix}_harness_output.log"
                watch_sh = os.path.expanduser("~/.claude/harness-watch.sh")
                ctx = (
                    f"⏳ [HARNESS] 동시 실행 충돌. 이미 실행 중.\n"
                    f"[액션] 지금 즉시 Bash 도구로 실행하라 (timeout=660000):\n"
                    f"bash {watch_sh} {log_file}"
                )
            log(prefix, f"INJECT(impl/{mode_label}) issue={issue_ref} prompt={prompt[:60]!r}")
        else:
            # harness_sh 없음 → fallback
            harness_directive = (
                "\n\n⚠️ src/** 직접 Edit/Write 금지. engineer 에이전트 직접 호출 금지.\n"
                "harness-executor.sh를 찾을 수 없습니다. 수동으로 실행하세요."
            )
            ctx = "[HARNESS ROUTER] 현재 워크플로우 상태\n" + flag_lines + harness_directive
            log(prefix, f"INJECT(impl/no-harness-sh) prompt={prompt[:60]!r}")

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

    # 버그/이슈 감지 시 bugfix harness 직접 spawn
    if is_bug and not flags["harness_active"]:
        harness_sh = get_harness_sh()
        issue_match_bug = re.search(r'#(\d+)', prompt)
        issue_ref = issue_match_bug.group(1) if issue_match_bug else "N"
        if harness_sh:
            log_file = try_spawn_harness("bugfix", harness_sh, prefix, issue_ref,
                                         ["--bug", prompt[:200]])
            watch_sh = os.path.expanduser("~/.claude/harness-watch.sh")
            if log_file:
                ctx = (
                    f"🐛 [HARNESS] bugfix 루프 실행 시작 (issue #{issue_ref})\n"
                    f"[액션] 지금 즉시 Bash 도구로 실행하라 (timeout=660000):\n"
                    f"bash {watch_sh} {log_file}\n"
                    f"완료 메시지 확인 후 유저에게 결과를 한국어로 보고하라."
                )
            else:
                log_file = f"/tmp/{prefix}_harness_output.log"
                ctx = (
                    f"⏳ [HARNESS] 이미 실행 중.\n"
                    f"[액션] 지금 즉시 Bash 도구로 실행하라 (timeout=660000):\n"
                    f"bash {watch_sh} {log_file}"
                )
        else:
            ctx = (
                "🐛 [HARNESS ROUTER] 버그 감지 — harness-executor.sh 없음.\n"
                "→ QA 에이전트를 수동으로 호출하세요."
            )
        log(prefix, f"INJECT(bugfix) issue={issue_ref} prompt={prompt[:60]!r}")
        print(json.dumps({"hookSpecificOutput": {"additionalContext": ctx}}))
        sys.exit(0)
    elif is_bug and flags["harness_active"]:
        log_file = f"/tmp/{prefix}_harness_output.log"
        ctx = f"⏳ [HARNESS] 이미 실행 중. 버그 처리 포함됨. 확인: Bash(tail -20 {log_file})"
        log(prefix, f"INJECT(bugfix/already_active) prompt={prompt[:60]!r}")
        print(json.dumps({"hookSpecificOutput": {"additionalContext": ctx}}))
        sys.exit(0)

    print(json.dumps({"hookSpecificOutput": {"additionalContext": ctx}}))


if __name__ == "__main__":
    main()
