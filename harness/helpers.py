"""
helpers.py — impl_helpers.sh 대체.
impl 루프(simple/std/deep)에서 공유하는 헬퍼 함수 모음.
Python 3.9+ stdlib only.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Callable, Optional, Tuple

try:
    from .core import (
        Flag, RunLogger, StateDir, hlog, write_attempt_meta,
    )
except ImportError:
    from core import (
        Flag, RunLogger, StateDir, hlog, write_attempt_meta,
    )


# ═══════════════════════════════════════════════════════════════════════
# 1. _load_constraints — Phase 0: constraints 로드
# ═══════════════════════════════════════════════════════════════════════

def load_constraints(config: object = None) -> str:
    """harness-memory.md(글로벌+로컬) + CLAUDE.md에서 제약사항을 수집.

    impl_helpers.sh의 _load_constraints()와 동일.
    """
    mem_global = Path.home() / ".claude" / "harness-memory.md"
    mem_local = Path(".claude") / "harness-memory.md"

    # 로컬 메모리 파일 초기화
    if not mem_local.exists():
        mem_local.parent.mkdir(parents=True, exist_ok=True)
        mem_local.write_text(
            "# Harness Memory\n\n## impl 패턴\n\n## design 패턴\n\n"
            "## bugfix 패턴\n\n## Auto-Promoted Rules\n\n"
            "## Known Failure Patterns\n\n## Success Patterns\n",
            encoding="utf-8",
        )
    else:
        content = mem_local.read_text(encoding="utf-8")
        for sec in ("impl 패턴", "design 패턴", "bugfix 패턴"):
            if f"## {sec}" not in content:
                with open(mem_local, "a", encoding="utf-8") as f:
                    f.write(f"\n## {sec}\n")

    constraints = ""
    for mf in (mem_global, mem_local):
        if mf.exists():
            text = mf.read_text(encoding="utf-8")
            # Auto-Promoted Rules 섹션에서 PROMOTED 항목 추출
            promoted_lines = []
            in_section = False
            for line in text.splitlines():
                if line.startswith("## Auto-Promoted Rules"):
                    in_section = True
                    continue
                if in_section and line.startswith("##"):
                    break
                if in_section and line.startswith("- PROMOTED:"):
                    promoted_lines.append(line)
                    if len(promoted_lines) >= 10:
                        break

            if promoted_lines:
                constraints += (
                    "\n[AUTO-PROMOTED RULES — 반복 실패 패턴, 반드시 회피]:\n"
                    + "\n".join(promoted_lines)
                )

            # Success Patterns 섹션에서 성공 패턴 추출
            success_lines = []
            in_success = False
            for line in text.splitlines():
                if line.startswith("## Success Patterns"):
                    in_success = True
                    continue
                if in_success and line.startswith("##"):
                    break
                if in_success and line.startswith("- "):
                    success_lines.append(line)
                    if len(success_lines) >= 5:
                        break

            if success_lines:
                constraints += (
                    "\n[SUCCESS PATTERNS — 이전 성공에서 배운 접근법, 참고]:\n"
                    + "\n".join(success_lines)
                )

    # 글로벌/로컬 각각 tail 20줄
    if mem_global.exists():
        lines = mem_global.read_text(encoding="utf-8").splitlines()
        constraints += "\n" + "\n".join(lines[-20:])
    if mem_local.exists():
        lines = mem_local.read_text(encoding="utf-8").splitlines()
        constraints += "\n" + "\n".join(lines[-20:])

    # CLAUDE.md에서 개발 명령어/작업 순서/Git 섹션 추출
    claude_md = Path("CLAUDE.md")
    if claude_md.exists():
        text = claude_md.read_text(encoding="utf-8")
        extracted = ""
        for section in ("## 개발 명령어", "## 작업 순서", "## Git"):
            pattern = rf"(^{re.escape(section)}.*?)(?=^---|\Z)"
            m = re.search(pattern, text, re.MULTILINE | re.DOTALL)
            if m:
                extracted += m.group(1) + "\n"
        constraints += "\n" + extracted[:10000]

    return constraints


# ═══════════════════════════════════════════════════════════════════════
# 2. append_failure — 실패 기록 + 자동 프로모션
# ═══════════════════════════════════════════════════════════════════════

def append_failure(
    impl_file: str,
    fail_type: str,
    error: str,
    state_dir: StateDir,
    prefix: str,
) -> None:
    """실패 기록을 harness-memory.md에 append. 3회 이상 반복 시 자동 프로모션."""
    date_str = time.strftime("%Y-%m-%d")
    impl_name = Path(impl_file).stem
    err_1line = error.splitlines()[0][:100] if error else ""
    mem_local = Path(".claude") / "harness-memory.md"

    # 실패 기록 append
    entry = f"- {date_str} | {impl_name} | {fail_type} | {err_1line}\n"
    with open(mem_local, "a", encoding="utf-8") as f:
        f.write(entry)

    # 패턴 카운트 + 자동 프로모션
    pattern_key = f"{impl_name}|{fail_type}"
    try:
        content = mem_local.read_text(encoding="utf-8")
        # 엔트리 라인에서 impl_name과 fail_type이 모두 있는 줄 카운트
        # (bash grep -Fc는 spaces 때문에 매칭 안 되는 버그가 있으므로 개선)
        count = sum(
            1 for line in content.splitlines()
            if impl_name in line and fail_type in line and "PROMOTED:" not in line
        )
    except OSError:
        count = 0

    if count >= 3:
        content = mem_local.read_text(encoding="utf-8")
        if "## Auto-Promoted Rules" not in content:
            with open(mem_local, "a", encoding="utf-8") as f:
                f.write("\n## Auto-Promoted Rules\n\n")

        if f"PROMOTED: {pattern_key}" not in content:
            promo = f"- PROMOTED: {pattern_key} | {count}회 반복 | {date_str} | MUST NOT: {err_1line}\n"
            with open(mem_local, "a", encoding="utf-8") as f:
                f.write(promo)
            print(f"[HARNESS] 실패 패턴 자동 프로모션: {pattern_key} ({count}회)")

    # memory_candidate.md에 후보 기록
    candidate_file = state_dir.path / f"{prefix}_memory_candidate.md"
    try:
        existing = candidate_file.read_text(encoding="utf-8") if candidate_file.exists() else ""
    except OSError:
        existing = ""

    if pattern_key not in existing:
        with open(candidate_file, "a", encoding="utf-8") as f:
            f.write(
                f"---\ndate: {date_str}\nimpl: {impl_name}\ntype: {fail_type}\n"
                f'pattern: {err_1line}\nsuggestion: "impl 파일에 관련 제약 추가 '
                f'또는 에이전트 지시 보강 검토"\n'
            )


# ═══════════════════════════════════════════════════════════════════════
# 3. append_success — 성공 기록
# ═══════════════════════════════════════════════════════════════════════

def append_success(
    impl_file: str,
    attempt_num: int,
    eng_out: str = "",
    attempt_dir: str = "",
) -> None:
    """성공 기록 + 성공 패턴 추출하여 harness-memory.md에 append."""
    date_str = time.strftime("%Y-%m-%d")
    impl_name = Path(impl_file).stem
    mem_local = Path(".claude") / "harness-memory.md"
    entry = f"- {date_str} | {impl_name} | success | attempt {attempt_num}\n"
    with open(mem_local, "a", encoding="utf-8") as f:
        f.write(entry)

    # ── 성공 패턴 추출 (REFLECTION) ──
    eng_content = ""
    if eng_out and Path(eng_out).exists():
        try:
            eng_content = Path(eng_out).read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    elif attempt_dir:
        eng_log = Path(attempt_dir) / "engineer.log"
        if eng_log.exists():
            try:
                eng_content = eng_log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass

    if eng_content:
        reflection = _extract_reflection(impl_name, eng_content, attempt_num)
        if reflection:
            _write_reflection(mem_local, impl_name, date_str, reflection)


# ═══════════════════════════════════════════════════════════════════════
# 4. rollback_attempt — 롤백 이벤트 기록
# ═══════════════════════════════════════════════════════════════════════

def rollback_attempt(
    attempt_num: int,
    run_logger: Optional[RunLogger] = None,
) -> None:
    """JSONL rollback 이벤트 기록."""
    if run_logger:
        run_logger.log_event({
            "event": "rollback",
            "attempt": attempt_num,
            "method": "keep-on-branch",
            "t": int(time.time()),
        })
    hlog(f"ROLLBACK attempt={attempt_num} — changes kept on feature branch")


# ═══════════════════════════════════════════════════════════════════════
# 5. check_agent_output — 에이전트 출력 확인
# ═══════════════════════════════════════════════════════════════════════

def check_agent_output(agent_name: str, out_file: str | Path) -> bool:
    """출력 파일 존재/비어있지 않음 확인."""
    p = Path(out_file)
    if not p.exists() or p.stat().st_size == 0:
        hlog(f"WARNING: {agent_name} 출력 파일 없음 또는 비어있음 — agent 호출 실패")
        print(f"[HARNESS] WARNING: {agent_name} agent가 출력을 생성하지 못함")
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════
# 6. run_automated_checks — 자동화된 체크
# ═══════════════════════════════════════════════════════════════════════

def run_automated_checks(
    impl_file: str,
    config: object,
    state_dir: StateDir,
    prefix: str,
) -> Tuple[bool, str]:
    """자동화된 체크. (성공여부, 에러메시지) 반환."""
    import subprocess

    out_file = state_dir.path / f"{prefix}_autocheck_fail.txt"
    out_file.unlink(missing_ok=True)

    # 1. 변경 파일 확인 (bash: git status --short | grep -qE "^ M|^M |^A ")
    r = subprocess.run(
        ["git", "status", "--short"],
        capture_output=True, text=True, timeout=10,
    )
    has_changes = bool(re.search(r"^ M|^M |^A ", r.stdout, re.MULTILINE))

    if not has_changes:
        msg = "no_changes: engineer가 아무 파일도 수정하지 않음"
        out_file.write_text(msg, encoding="utf-8")
        print("AUTOMATED_CHECKS_FAIL: no_changes")
        return False, msg

    # 2. package.json 새 의존성 감지
    r_show = subprocess.run(
        ["git", "show", "HEAD:package.json"],
        capture_output=True, text=True, timeout=5,
    )
    if r_show.returncode == 0:
        r_diff = subprocess.run(
            ["git", "diff", "HEAD", "--", "package.json"],
            capture_output=True, text=True, timeout=5,
        )
        if re.search(r'^\+\s+"[a-z@]', r_diff.stdout, re.MULTILINE):
            msg = "new_deps: package.json에 새 의존성이 추가됨 (사전 승인 필요)"
            out_file.write_text(msg, encoding="utf-8")
            print("AUTOMATED_CHECKS_FAIL: new_deps")
            return False, msg

    # 3. PROTECTED 파일 변경 감지
    try:
        impl_content = Path(impl_file).read_text(encoding="utf-8")
        protected = re.findall(r"\(PROTECTED\)\s+(\S+)", impl_content)
    except OSError:
        protected = []

    for pf in protected:
        if not pf:
            continue
        r_diff = subprocess.run(
            ["git", "diff", "HEAD", "--", pf],
            capture_output=True, text=True, timeout=5,
        )
        if re.search(r"^[-+]", r_diff.stdout, re.MULTILINE):
            msg = f"file_unchanged: 변경 금지 파일 수정됨: {pf}"
            out_file.write_text(msg, encoding="utf-8")
            print(f"AUTOMATED_CHECKS_FAIL: file_unchanged ({pf})")
            return False, msg

    print("AUTOMATED_CHECKS_PASS")
    return True, ""


# ═══════════════════════════════════════════════════════════════════════
# 7. budget_check — 비용 체크
# ═══════════════════════════════════════════════════════════════════════

def budget_check(
    agent_name: str,
    out_file: str | Path,
    total_cost: float,
    max_cost: float,
    state_dir: Optional[StateDir] = None,
    prefix: str = "",
    config: object = None,
) -> float:
    """비용 + 토큰 확인. 누적 비용 반환. 상한 초과 시 sys.exit."""
    import json as _json

    stem = str(out_file)
    if stem.endswith(".txt"):
        stem = stem[:-4]
    cost_file = Path(f"{stem}_cost.txt")
    stats_file = Path(f"{stem}_stats.json")

    try:
        agent_cost = float(cost_file.read_text().strip())
    except (OSError, ValueError):
        agent_cost = 0.0

    total_cost += agent_cost
    hlog(f"COST: {agent_name} ${agent_cost} | total: ${total_cost}/{max_cost}")

    if total_cost > max_cost:
        hlog(f"BUDGET EXCEEDED (${total_cost} > ${max_cost})")
        os.environ["HARNESS_RESULT"] = "HARNESS_BUDGET_EXCEEDED"
        print(f"HARNESS_BUDGET_EXCEEDED: ${total_cost} spent, limit ${max_cost}")
        if state_dir:
            state_dir.flag_rm(Flag.HARNESS_ACTIVE)
        sys.exit(1)

    # ── 토큰 예산 체크 ──
    if config and getattr(config, "token_budget", None):
        try:
            stats = _json.loads(stats_file.read_text()) if stats_file.exists() else {}
        except (OSError, ValueError):
            stats = {}

        in_tok = stats.get("in_tok", 0)
        out_tok = stats.get("out_tok", 0)
        used_tok = in_tok + out_tok

        limit = config.token_budget.get(agent_name, config.token_budget.get("default", 0))
        if limit > 0 and used_tok > 0:
            ratio = used_tok / limit
            if ratio >= 0.85:
                hlog(f"TOKEN WARNING: {agent_name} {used_tok}/{limit} ({ratio:.0%})")
                print(f"[HARNESS] TOKEN WARNING: {agent_name} {ratio:.0%} of budget ({used_tok}/{limit}tok)")
            if ratio > 1.0:
                hlog(f"TOKEN BUDGET EXCEEDED: {agent_name} {used_tok} > {limit}")
                print(f"[HARNESS] TOKEN BUDGET EXCEEDED: {agent_name}")

    return total_cost


# ═══════════════════════════════════════════════════════════════════════
# 8. generate_pr_body — PR 본문 생성
# ═══════════════════════════════════════════════════════════════════════

def generate_pr_body(
    impl_file: str,
    issue_num: str | int,
    attempt_num: int,
    max_attempts: int,
    state_dir: StateDir,
    prefix: str,
) -> str:
    """PR 본문 생성."""
    impl_name = Path(impl_file).stem

    # 테스트 요약
    test_out = state_dir.path / f"{prefix}_test_out.txt"
    test_summary = "PASS"
    if test_out.exists():
        lines = [
            l for l in test_out.read_text(encoding="utf-8").splitlines()
            if re.search(r"Tests |passed|failed", l)
        ]
        test_summary = " ".join(lines[-3:]) if lines else "PASS"

    # 보안 등급
    sec_out = state_dir.path / f"{prefix}_sec_out.txt"
    sec_level = "LOW"
    if sec_out.exists():
        m = re.search(r"\b(HIGH|MEDIUM|LOW)\b", sec_out.read_text(encoding="utf-8"))
        if m:
            sec_level = m.group(1)

    # PR 리뷰 노트
    pr_out = state_dir.path / f"{prefix}_pr_out.txt"
    pr_notes = "없음"
    if pr_out.exists():
        text = pr_out.read_text(encoding="utf-8")
        # nice to have / 권고사항 다음의 bullet 항목
        in_section = False
        notes = []
        for line in text.splitlines():
            if re.search(r"nice to have|권고사항", line, re.IGNORECASE):
                in_section = True
                continue
            if in_section and re.match(r"^[-•*]", line):
                notes.append(line)
                if len(notes) >= 3:
                    break
            elif in_section and line.strip() and not re.match(r"^[-•*]", line):
                break
        if notes:
            pr_notes = " ".join(notes)

    # 결정 근거
    why = f"Issue #{issue_num} 구현"
    try:
        impl_text = Path(impl_file).read_text(encoding="utf-8")
        in_section = False
        for line in impl_text.splitlines():
            if line.strip().startswith("## 결정 근거"):
                in_section = True
                continue
            if in_section and line.startswith("- "):
                why = line[2:].strip()
                break
    except OSError:
        pass

    return (
        f"## What / Why\n"
        f"Issue #{issue_num} — `{impl_name}`\n"
        f"{why}\n\n"
        f"## 작동 증거\n"
        f"- test: {test_summary}\n"
        f"- 시도: {attempt_num}/{max_attempts}회 성공\n\n"
        f"## 위험 + AI 역할\n"
        f"- 보안 최고 등급: {sec_level}\n"
        f"- AI(Claude) 구현·테스트·검증·리뷰 완료. 인간 최종 확인 권장: 비즈니스 로직\n\n"
        f"## 리뷰 포커스\n"
        f"{pr_notes}"
    )


# ═══════════════════════════════════════════════════════════════════════
# 9. save_impl_meta — write_attempt_meta 래퍼
# ═══════════════════════════════════════════════════════════════════════

def save_impl_meta(
    adir: str | Path,
    anum: int,
    result: str,
    depth: str,
    fail_type: str = "",
    hints: str = "",
) -> None:
    """attempt meta.json 기록 래퍼."""
    import subprocess
    adir = Path(adir)

    # 변경 파일 목록
    try:
        r = subprocess.run(
            ["git", "diff", "HEAD~1", "--name-only"],
            capture_output=True, text=True, timeout=5,
        )
        changed = ",".join(r.stdout.strip().splitlines()[:5]) if r.returncode == 0 else ""
    except Exception:
        changed = ""

    # 실패 테스트
    ftests = ""
    test_results = adir / "test-results.log"
    if test_results.exists():
        lines = [
            l for l in test_results.read_text(encoding="utf-8").splitlines()
            if re.search(r"✗| FAIL |× ", l)
        ][:3]
        ftests = ",".join(lines)[:200]

    # 에러 요약
    err1 = ""
    eng_log = adir / "engineer.log"
    if eng_log.exists():
        first_line = eng_log.read_text(encoding="utf-8").splitlines()
        err1 = first_line[0][:150] if first_line else ""

    write_attempt_meta(
        str(adir / "meta.json"),
        attempt=anum, loop="impl", depth=depth, result=result,
        fail_type=fail_type, failed_tests=ftests, changed_files=changed,
        agent_sequence="engineer,test-engineer,validator,pr-reviewer",
        error_summary=err1, next_hints=hints,
    )


# ═══════════════════════════════════════════════════════════════════════
# 10. setup_hlog — hlog 클로저
# ═══════════════════════════════════════════════════════════════════════

def setup_hlog(state_dir: StateDir, prefix: str) -> Callable:
    """attempt 번호를 포함하는 hlog 클로저 반환."""
    log_path = state_dir.path / f"{prefix}-harness-debug.log"
    os.environ["HLOG"] = str(log_path)
    _attempt = [0]  # mutable container for closure

    def _hlog(msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] [attempt={_attempt[0]}] {msg}"
        print(line)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    _hlog.set_attempt = lambda n: _attempt.__setitem__(0, n)
    return _hlog


# ═══════════════════════════════════════════════════════════════════════
# 11. log_decision — JSONL decision 이벤트
# ═══════════════════════════════════════════════════════════════════════

def log_decision(
    key: str,
    value: str,
    reason: str,
    run_logger: Optional[RunLogger] = None,
    attempt: int = 0,
) -> None:
    if run_logger:
        run_logger.log_event({
            "event": "decision",
            "key": key,
            "value": value,
            "reason": reason,
            "t": int(time.time()),
            "attempt": attempt,
        })


# ═══════════════════════════════════════════════════════════════════════
# 12. log_phase — JSONL phase 이벤트
# ═══════════════════════════════════════════════════════════════════════

def log_phase(
    phase: str,
    run_logger: Optional[RunLogger] = None,
    attempt: int = 0,
) -> None:
    if run_logger:
        run_logger.log_event({
            "event": "phase",
            "name": phase,
            "t": int(time.time()),
            "attempt": attempt,
        })


# ═══════════════════════════════════════════════════════════════════════
# 13. _extract_reflection / _write_reflection — 성공 패턴 추출
# ═══════════════════════════════════════════════════════════════════════

def _extract_reflection(impl_name: str, eng_content: str, attempt_num: int) -> str:
    """engineer 출력에서 성공 패턴/핵심 접근법을 추출.

    마지막 500줄에서 핵심 키워드가 포함된 문장 추출.
    attempt > 1이면 재시도 성공이므로 "무엇이 달라져서 성공했나"에 초점.
    """
    lines = eng_content.splitlines()[-500:]

    # 패턴 1: 명시적 해결 마커
    summary_lines = [
        l.strip() for l in lines
        if re.search(r"해결|수정|완료|fixed|resolved|solution|approach", l, re.IGNORECASE)
        and len(l.strip()) > 20
    ]

    # 패턴 2: 파일 변경 + 이유 설명 라인
    change_lines = [
        l.strip() for l in lines
        if re.search(r"\.(ts|tsx|js|jsx|py|css|json)\b", l)
        and re.search(r"변경|추가|수정|삭제|refactor|add|update|fix|remove", l, re.IGNORECASE)
        and len(l.strip()) > 15
    ]

    candidates = summary_lines[:3] + change_lines[:2]
    if not candidates:
        return ""

    result = [c[:150] for c in candidates[:5]]
    prefix = f"[attempt={attempt_num}] " if attempt_num > 1 else ""
    return prefix + " | ".join(result)


def _write_reflection(mem_local: Path, impl_name: str, date_str: str, reflection: str) -> None:
    """## Success Patterns 섹션에 reflection 기록."""
    try:
        content = mem_local.read_text(encoding="utf-8") if mem_local.exists() else ""
    except OSError:
        content = ""

    if "## Success Patterns" not in content:
        with open(mem_local, "a", encoding="utf-8") as f:
            f.write("\n## Success Patterns\n")

    # 중복 방지: 같은 impl에 대해 같은 날짜 기록이 있으면 스킵
    parts = content.split("## Success Patterns")
    if len(parts) > 1 and f"{date_str} | {impl_name}" in parts[-1]:
        return

    entry = f"- {date_str} | {impl_name} | {reflection}\n"
    with open(mem_local, "a", encoding="utf-8") as f:
        f.write(entry)


# ═══════════════════════════════════════════════════════════════════════
# 14. extract_acceptance_criteria — impl 파일에서 수용 기준 추출
# ═══════════════════════════════════════════════════════════════════════

def extract_acceptance_criteria(impl_file: str) -> list:
    """impl 파일의 ## 수용 기준 섹션에서 항목 추출.

    (TEST), (BROWSER:DOM), (MANUAL) 태그가 있는 행을 파싱.
    태그 없는 항목도 포함 (handoff에는 전부 필요).
    """
    try:
        content = Path(impl_file).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    criteria = []
    in_section = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## 수용 기준") or stripped.startswith("## Acceptance Criteria"):
            in_section = True
            continue
        if in_section:
            if stripped.startswith("## "):
                break
            if stripped.startswith(("- ", "* ", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
                criteria.append(stripped.lstrip("- *0123456789. "))
    return criteria[:15]


# ═══════════════════════════════════════════════════════════════════════
# 15. extract_polish_items — pr-reviewer 출력에서 NICE TO HAVE 항목 추출
# ═══════════════════════════════════════════════════════════════════════

def extract_polish_items(pr_out_file: str) -> str:
    """pr-reviewer 출력에서 NICE TO HAVE / 권고사항 / 개선 제안 항목을 추출.

    빈 문자열이면 polish 불필요.
    """
    try:
        content = Path(pr_out_file).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    items: list = []
    in_section = False
    for line in content.splitlines():
        lower = line.lower().strip()
        # 섹션 시작 감지
        if any(kw in lower for kw in (
            "nice to have", "권고사항", "개선 제안", "cosmetic",
            "polish", "optional", "제안", "선택적",
        )):
            in_section = True
            continue
        # 섹션 종료 감지
        if in_section and (lower.startswith("## ") or lower.startswith("---")):
            break
        # 항목 수집
        if in_section and line.strip().startswith(("-", "*", "•")):
            items.append(line.strip())
            if len(items) >= 10:
                break

    return "\n".join(items)
