"""
core.py — 하네스 핵심 인프라 (flags.sh + markers.sh + utils.sh 대체).
Python 3.9+ stdlib only.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .config import HarnessConfig, load_config
except ImportError:
    from config import HarnessConfig, load_config

# ═══════════════════════════════════════════════════════════════════════
# 1. StateDir — 상태 파일 관리 (init_state_dir + flag_touch/rm/exists)
# ═══════════════════════════════════════════════════════════════════════

class StateDir:
    """flags.sh의 flag_touch/flag_rm/flag_exists + init_state_dir 대체."""

    def __init__(self, project_root: Path, prefix: str) -> None:
        self.project_root = project_root
        self.prefix = prefix
        self.path = project_root / ".claude" / "harness-state"
        self.path.mkdir(parents=True, exist_ok=True)

    def _flag_path(self, name: str) -> Path:
        return self.path / f"{self.prefix}_{name}"

    def flag_touch(self, name: str) -> None:
        self._flag_path(name).touch()

    def flag_rm(self, name: str) -> None:
        self._flag_path(name).unlink(missing_ok=True)

    def flag_exists(self, name: str) -> bool:
        return self._flag_path(name).exists()


# ═══════════════════════════════════════════════════════════════════════
# 2. Flag enum — flags.sh 상수 1:1 매핑
# ═══════════════════════════════════════════════════════════════════════

class Flag(str, Enum):
    """flags.sh의 FLAG_* 상수와 1:1 대응. 값은 플래그 파일 이름 접미사."""
    # ── 하네스 제어 플래그 ──
    HARNESS_ACTIVE = "harness_active"
    HARNESS_KILL = "harness_kill"
    # ── 검증 단계 플래그 ──
    PLAN_VALIDATION_PASSED = "plan_validation_passed"
    TEST_ENGINEER_PASSED = "test_engineer_passed"
    VALIDATOR_B_PASSED = "validator_b_passed"
    PR_REVIEWER_LGTM = "pr_reviewer_lgtm"
    SECURITY_REVIEW_PASSED = "security_review_passed"
    BUGFIX_VALIDATION_PASSED = "bugfix_validation_passed"
    # ── 설계/디자인 플래그 ──
    LIGHT_PLAN_READY = "light_plan_ready"
    DESIGNER_RAN = "designer_ran"
    DESIGN_CRITIC_PASSED = "design_critic_passed"


# ═══════════════════════════════════════════════════════════════════════
# 3. Marker enum — markers.sh KNOWN_MARKERS 1:1 매핑
# ═══════════════════════════════════════════════════════════════════════

class Marker(str, Enum):
    """markers.sh의 KNOWN_MARKERS 배열과 1:1 대응."""
    # validator
    PASS = "PASS"
    FAIL = "FAIL"
    SPEC_MISSING = "SPEC_MISSING"
    PLAN_VALIDATION_PASS = "PLAN_VALIDATION_PASS"
    PLAN_VALIDATION_FAIL = "PLAN_VALIDATION_FAIL"
    DESIGN_REVIEW_PASS = "DESIGN_REVIEW_PASS"
    DESIGN_REVIEW_FAIL = "DESIGN_REVIEW_FAIL"
    BUGFIX_PASS = "BUGFIX_PASS"
    BUGFIX_FAIL = "BUGFIX_FAIL"
    # test-engineer
    TESTS_PASS = "TESTS_PASS"
    TESTS_FAIL = "TESTS_FAIL"
    # pr-reviewer
    LGTM = "LGTM"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    # security-reviewer
    SECURE = "SECURE"
    VULNERABILITIES_FOUND = "VULNERABILITIES_FOUND"
    # architect
    LIGHT_PLAN_READY = "LIGHT_PLAN_READY"
    READY_FOR_IMPL = "READY_FOR_IMPL"
    SPEC_GAP_FOUND = "SPEC_GAP_FOUND"
    SPEC_GAP_RESOLVED = "SPEC_GAP_RESOLVED"
    PRODUCT_PLANNER_ESCALATION_NEEDED = "PRODUCT_PLANNER_ESCALATION_NEEDED"
    TECH_CONSTRAINT_CONFLICT = "TECH_CONSTRAINT_CONFLICT"
    # product-planner
    PRODUCT_PLAN_READY = "PRODUCT_PLAN_READY"
    PRODUCT_PLAN_UPDATED = "PRODUCT_PLAN_UPDATED"
    # design-critic
    PICK = "PICK"
    ITERATE = "ITERATE"
    ESCALATE = "ESCALATE"
    VARIANTS_APPROVED = "VARIANTS_APPROVED"
    VARIANTS_ALL_REJECTED = "VARIANTS_ALL_REJECTED"
    # harness control
    HARNESS_DONE = "HARNESS_DONE"
    IMPLEMENTATION_ESCALATE = "IMPLEMENTATION_ESCALATE"
    MERGE_CONFLICT_ESCALATE = "MERGE_CONFLICT_ESCALATE"
    # product-planner (정보 부족 에스컬레이션)
    CLARITY_INSUFFICIENT = "CLARITY_INSUFFICIENT"


# ═══════════════════════════════════════════════════════════════════════
# 3.5 HUD — 실시간 진행 상태 표시 + JSON 파일 저장
# ═══════════════════════════════════════════════════════════════════════

class HUD:
    """하네스 실행 중 진행 상태를 시각적으로 표시하고 JSON으로 저장.

    - stdout에 진행 바 블록 출력 (Bash 출력 내)
    - .claude/harness-state/{prefix}_hud.json에 실시간 상태 저장
      (/harness-monitor에서 watch 가능)
    """

    DEPTH_AGENTS = {
        "simple": ["engineer", "pr-reviewer", "merge"],
        "std": ["engineer", "test-engineer", "validator", "pr-reviewer", "merge"],
        "deep": ["engineer", "test-engineer", "validator", "security-reviewer", "pr-reviewer", "merge"],
    }

    def __init__(
        self,
        depth: str,
        prefix: str,
        issue_num: str | int,
        max_attempts: int,
        budget: float,
        state_dir: Optional["StateDir"] = None,
    ) -> None:
        self.depth = depth
        self.prefix = prefix
        self.issue = str(issue_num)
        self.max_attempts = max_attempts
        self.budget = budget
        self.start_time = time.time()
        self.attempt = 0
        self.total_cost = 0.0

        self.agents = self.DEPTH_AGENTS.get(depth, self.DEPTH_AGENTS["std"])
        self.agent_status: Dict[str, Dict[str, Any]] = {
            a: {"status": "pending", "elapsed": 0, "cost": 0.0}
            for a in self.agents
        }

        self._hud_path: Optional[Path] = None
        if state_dir:
            self._hud_path = state_dir.path / f"{prefix}_hud.json"

    def set_attempt(self, n: int) -> None:
        self.attempt = n

    def agent_start(self, agent: str) -> None:
        if agent in self.agent_status:
            self.agent_status[agent] = {
                "status": "running",
                "start": time.time(),
                "elapsed": 0,
                "cost": 0.0,
            }
        self._write_json()
        self._print_block()

    def agent_done(self, agent: str, elapsed: int, cost: float, result: str = "done") -> None:
        if agent in self.agent_status:
            self.agent_status[agent] = {
                "status": result,  # "done", "fail", "skip"
                "elapsed": elapsed,
                "cost": cost,
            }
        self.total_cost += cost
        self._write_json()
        self._print_block()

    def agent_skip(self, agent: str, reason: str = "") -> None:
        if agent in self.agent_status:
            self.agent_status[agent] = {
                "status": "skip",
                "elapsed": 0,
                "cost": 0.0,
                "reason": reason,
            }
        self._write_json()

    def _elapsed_str(self) -> str:
        e = int(time.time() - self.start_time)
        m, s = divmod(e, 60)
        return f"{m}m{s:02d}s"

    def _bar(self, status: str, width: int = 20) -> str:
        if status == "done":
            return "▓" * width + " ✅"
        elif status == "fail":
            return "▓" * width + " ❌"
        elif status == "skip":
            return "░" * width + " ⏭"
        elif status == "running":
            return "▓" * (width // 2) + "░" * (width - width // 2) + " ⏳"
        else:
            return "░" * width + "   "

    def _print_block(self) -> None:
        total = len(self.agents)
        done = sum(1 for a in self.agents if self.agent_status[a]["status"] in ("done", "skip"))
        pct = int(done / total * 100) if total else 0

        print()
        print(f"━━━ 📊 depth={self.depth} | attempt {self.attempt + 1}/{self.max_attempts}"
              f" | ${self.total_cost:.2f}/${self.budget:.0f}"
              f" | {self._elapsed_str()}"
              f" | {pct}% ━━━")

        for i, agent in enumerate(self.agents, 1):
            s = self.agent_status[agent]
            status = s["status"]
            bar = self._bar(status)
            detail = ""
            if status == "done":
                detail = f" {s.get('elapsed', 0)}s ${s.get('cost', 0):.2f}"
            elif status == "running":
                e = int(time.time() - s.get("start", time.time()))
                detail = f" {e}s..."
            print(f" [{i}/{total}] {agent:<20s} {bar}{detail}")

        print()

    def _write_json(self) -> None:
        if not self._hud_path:
            return
        data = {
            "depth": self.depth,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "cost": round(self.total_cost, 4),
            "budget": self.budget,
            "elapsed": int(time.time() - self.start_time),
            "issue": self.issue,
            "agents": [
                {"name": a, **self.agent_status[a]}
                for a in self.agents
            ],
        }
        try:
            self._hud_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def cleanup(self) -> None:
        """하네스 종료 시 HUD에 완료 상태 기록 (파일 유지)."""
        self._write_json()
        if self._hud_path and self._hud_path.exists():
            try:
                data = json.loads(self._hud_path.read_text(encoding="utf-8"))
                data["status"] = "done"
                self._hud_path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except (OSError, json.JSONDecodeError):
                pass


# ═══════════════════════════════════════════════════════════════════════
# 3.6 Second Reviewer — 외부 AI 병렬 리뷰 (Gemini/GPT)
# ═══════════════════════════════════════════════════════════════════════

def start_second_review(
    diff_text: str,
    reviewer: str,
    model: str = "",
) -> Optional[subprocess.Popen]:
    """외부 AI 리뷰를 비동기로 시작. Popen 객체 반환. CLI 없으면 None."""
    cli_map = {
        "gemini": "gemini",
        "gpt": "gpt",
        "copilot": "gh",
    }
    cli_name = cli_map.get(reviewer, reviewer)
    if not shutil.which(cli_name):
        print(f"[HARNESS] second_reviewer '{reviewer}' CLI 없음 — 스킵")
        return None

    prompt = (
        "아래 코드 diff를 리뷰하라. 기능 정확성이 아닌 코드 품질에 집중:\n"
        "- 불필요한 주석이나 console.log\n"
        "- 과도한 추상화나 래퍼 함수\n"
        "- 네이밍 개선점\n"
        "- AI 생성 코드 특유의 패턴 (장황한 에러 메시지, 불필요한 try-catch 등)\n"
        "- 사용되지 않는 import/변수\n"
        "\n"
        "발견한 항목을 bullet list로 출력하라. 없으면 'CLEAN'.\n"
        f"\n=== DIFF ===\n{diff_text[:15000]}"
    )

    if reviewer == "gemini":
        cmd = ["gemini", "-m", model or "gemini-2.5-flash", prompt]
    elif reviewer == "gpt":
        cmd = ["gpt", "-m", model or "gpt-4o-mini", prompt]
    else:
        cmd = [cli_name, prompt]

    try:
        return subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
    except OSError as e:
        print(f"[HARNESS] second_reviewer 실행 실패: {e}")
        return None


def collect_second_review(proc: Optional[subprocess.Popen], timeout: int = 120) -> str:
    """비동기 리뷰 결과 수집. 타임아웃/에러/CLEAN 시 빈 문자열."""
    if proc is None:
        return ""
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        if proc.returncode != 0:
            if stderr and any(kw in stderr.lower() for kw in ("auth", "unauthorized", "api key")):
                print(f"[HARNESS] second_reviewer 인증 에러 — 스킵")
            return ""
        if stdout.strip() and "CLEAN" not in stdout.upper():
            return stdout.strip()
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        print(f"[HARNESS] second_reviewer 타임아웃 — 스킵")
    except Exception:
        pass
    return ""


# ═══════════════════════════════════════════════════════════════════════
# 4. parse_marker — markers.sh의 parse_marker() 대체
# ═══════════════════════════════════════════════════════════════════════

def parse_marker(filepath: str | Path, patterns: str) -> str:
    """에이전트 출력 파일에서 마커를 파싱.

    Args:
        filepath: 에이전트 출력 파일 경로
        patterns: 파이프 구분 마커 목록 (e.g. "PASS|FAIL|SPEC_MISSING")

    Returns:
        매칭된 마커 문자열, 없으면 "UNKNOWN"
    """
    try:
        content = Path(filepath).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "UNKNOWN"

    pattern_list = patterns.split("|")
    joined = "|".join(re.escape(p) for p in pattern_list)

    # 1차: 구조화된 마커 ---MARKER:X---
    m = re.search(rf"---MARKER:({joined})---", content)
    if m:
        return m.group(1)

    # 2차 폴백: 레거시 워드 바운더리 매칭
    m = re.search(rf"\b({joined})\b", content)
    if m:
        return m.group(1)

    return "UNKNOWN"


# ═══════════════════════════════════════════════════════════════════════
# 5. RunLogger — JSONL 이벤트 로거 (rotate_harness_logs + write_run_end)
# ═══════════════════════════════════════════════════════════════════════

class RunLogger:
    """JSONL 이벤트 로거. 기존 rotate_harness_logs() + write_run_end() 대체."""

    def __init__(self, prefix: str, mode: str, issue: str = "") -> None:
        self.prefix = prefix
        self.mode = mode
        self.issue = issue
        self.log_dir = Path.home() / ".claude" / "harness-logs" / prefix
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.run_start = int(time.time())
        self.run_ts = time.strftime("%Y%m%d_%H%M%S")
        # bash 호환: 루프 스크립트가 HARNESS_RUN_TS로 히스토리 디렉토리 생성
        os.environ["HARNESS_RUN_TS"] = self.run_ts

        # FIFO 로테이션: 최신 10개 유지
        self._rotate()

        self.log_file = self.log_dir / f"run_{self.run_ts}.jsonl"

        # run_start 이벤트
        event: Dict[str, Any] = {
            "event": "run_start",
            "prefix": prefix,
            "mode": mode,
            "t": self.run_start,
        }
        if issue:
            event["issue"] = issue
        self._append(event)

        print(f"[HARNESS] 실행 로그: {self.log_file}")
        print(f'[HARNESS] 실시간 확인: tail -f "{self.log_file}"')

    def _rotate(self) -> None:
        """10번째 이후(오래된 것) 삭제."""
        logs = sorted(
            [f for f in self.log_dir.iterdir() if f.name.startswith("run_") and f.suffix == ".jsonl"],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in logs[9:]:  # 새 파일 추가 후 최대 10개
            old.unlink(missing_ok=True)

    def _append(self, event: Dict[str, Any]) -> None:
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    @property
    def path(self) -> Path:
        return self.log_file

    def log_event(self, event: Dict[str, Any]) -> None:
        self._append(event)

    def log_agent_start(self, agent: str, prompt_chars: int) -> None:
        t = int(time.time())
        iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._append({
            "event": "agent_start",
            "agent": agent,
            "t": t,
            "start_ts": iso,
            "prompt_chars": prompt_chars,
        })

    def log_agent_end(
        self,
        agent: str,
        elapsed: int,
        cost: float,
        exit_code: int,
        prompt_chars: int,
    ) -> None:
        t = int(time.time())
        iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._append({
            "event": "agent_end",
            "agent": agent,
            "t": t,
            "end_ts": iso,
            "elapsed": elapsed,
            "duration_s": elapsed,
            "exit": exit_code,
            "cost_usd": cost,
            "prompt_chars": prompt_chars,
        })

    def log_agent_stats(
        self,
        agent: str,
        tools: Dict[str, int],
        files_read: List[str],
        in_tok: int,
        out_tok: int,
    ) -> None:
        self._append({
            "event": "agent_stats",
            "agent": agent,
            "tools": tools,
            "files_read": files_read[:50],
            "in_tok": in_tok,
            "out_tok": out_tok,
        })

    def write_run_end(self, result: str, branch: str = "", issue: str = "") -> None:
        """run_end 이벤트 + 타이밍 요약 출력."""
        if result == "unknown":
            result = "HARNESS_CRASH"
        t_end = int(time.time())
        total_elapsed = t_end - self.run_start
        # 제어문자 제거
        branch = re.sub(r"[\t\n\r]", "", branch)[:100]
        self._append({
            "event": "run_end",
            "t": t_end,
            "elapsed": total_elapsed,
            "result": result,
            "branch": branch,
            "issue": issue or self.issue,
        })
        self._print_timing_summary(total_elapsed)

        # 정책 17 리마인더
        print()
        print(f"[HARNESS] 정책 17: /harness-review 자동 실행 필수 — 결과: {result}")
        print("[HARNESS] Bash stdout을 원문 그대로 유저에게 출력할 것 (재가공 금지)")
        print()

        # 완료 후 자동 리뷰 트리거 (백그라운드)
        review_agent_py = Path.home() / ".claude" / "harness" / "review_agent.py"
        review_agent_sh = Path.home() / ".claude" / "harness" / "review-agent.sh"
        if review_agent_py.exists():
            subprocess.Popen(
                ["python3", str(review_agent_py), str(self.log_file), self.prefix],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif review_agent_sh.exists():
            subprocess.Popen(
                ["bash", str(review_agent_sh), str(self.log_file), self.prefix],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def _print_timing_summary(self, total_elapsed: int) -> None:
        """타이밍 요약 출력 (기존 _print_timing_summary와 동일)."""
        if not self.log_file.exists():
            return

        agents: Dict[str, Dict[str, Any]] = {}
        total_cost = 0.0
        total_in = 0
        total_out = 0

        for line in self.log_file.read_text().splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                if e.get("event") == "agent_end":
                    a = e["agent"]
                    elapsed = e.get("elapsed", 0)
                    cost = float(e.get("cost_usd", 0) or 0)
                    if a not in agents:
                        agents[a] = {"calls": 0, "time": 0, "cost": 0.0, "in_tok": 0, "out_tok": 0}
                    agents[a]["calls"] += 1
                    agents[a]["time"] += elapsed
                    agents[a]["cost"] += cost
                    total_cost += cost
                elif e.get("event") == "agent_stats":
                    a = e.get("agent", "")
                    if a in agents:
                        agents[a]["in_tok"] += e.get("in_tok", 0)
                        agents[a]["out_tok"] += e.get("out_tok", 0)
                        total_in += e.get("in_tok", 0)
                        total_out += e.get("out_tok", 0)
            except Exception:
                pass

        print()
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("  하네스 실행 요약")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        mins, secs = divmod(total_elapsed, 60)
        print(f"  총 실행 시간: {mins}m {secs}s")

        if not agents:
            print("  (에이전트 호출 없음)")
        else:
            print(f"  총 비용: ${total_cost:.4f}")
            print(f"  총 토큰: in={total_in:,} out={total_out:,}")
            print()
            print(f"  {'에이전트':<20s} {'호출':<5s} {'시간':<10s} {'비용':<10s}")
            print(f"  {'─'*20} {'─'*5} {'─'*10} {'─'*10}")
            sorted_agents = sorted(agents.items(), key=lambda x: x[1]["time"], reverse=True)
            for name, s in sorted_agents:
                m, sec = divmod(s["time"], 60)
                print(f"  {name:<20s} {s['calls']:<5d} {m}m{sec:02d}s      ${s['cost']:.4f}")
            slowest_name, slowest_data = sorted_agents[0]
            print()
            print(f"  가장 느린 단계: {slowest_name} ({slowest_data['time']}s)")

        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print()


# ═══════════════════════════════════════════════════════════════════════
# 6. agent_call — _agent_call()의 Python 전환
# ═══════════════════════════════════════════════════════════════════════

def agent_call(
    agent: str,
    timeout_secs: int,
    prompt: str,
    out_file: str | Path,
    run_logger: Optional[RunLogger] = None,
    config: Optional[HarnessConfig] = None,
    hist_dir: Optional[str | Path] = None,
) -> int:
    """에이전트 호출 래퍼 — _agent_call()의 Python 포팅.

    Returns:
        exit code (0=성공, 124/142=타임아웃, etc.)
    """
    out_file = Path(out_file)
    # cost/stats 파일명: bash의 ${out_file%.txt}_cost.txt 와 동일
    stem = str(out_file)
    if stem.endswith(".txt"):
        stem = stem[:-4]
    cost_file = Path(f"{stem}_cost.txt")
    stats_file = Path(f"{stem}_stats.json")

    t_start = int(time.time())
    call_exit = 0

    # 초기화: 파이프라인 실패 시에도 파일 존재 보장
    cost_file.write_text("0")
    stats_file.write_text("{}")
    out_file.write_text("")

    # 히스토리: 인풋 프롬프트 원문 보존
    if hist_dir and Path(hist_dir).is_dir():
        (Path(hist_dir) / f"{agent}.prompt").write_text(prompt, encoding="utf-8")

    # prefix 결정 (active 플래그용)
    if config:
        prefix_for_flag = config.prefix
    else:
        prefix_for_flag = _detect_prefix()

    # agent_start 이벤트
    if run_logger:
        run_logger.log_agent_start(agent, len(prompt))

    # 에이전트별 active 플래그
    active_flag = Path(f"/tmp/{prefix_for_flag}_{agent}_active")
    active_flag.touch()

    # 공통 프리앰블 주입
    preamble_file = Path.home() / ".claude" / "agents" / "preamble.md"
    preamble = ""
    if preamble_file.exists():
        preamble = preamble_file.read_text(encoding="utf-8")

    scope_prefix = (
        "[SCOPE] 프로젝트 소스(src/, docs/, 루트 설정)만 분석 대상. "
        ".claude/, hooks/, harness-*.sh, orchestration-rules.md 등 "
        "하네스 인프라 파일은 읽지도 수정하지도 마라."
    )
    full_prompt = f"{preamble}\n\n{scope_prefix}\n{prompt}"

    # 입력 미리보기 (SCOPE 접두어 제외, 3줄, 160자 캡)
    preview_lines = [
        line for line in full_prompt.splitlines()
        if not line.startswith("[SCOPE]") and line.strip()
    ][:3]
    preview = " ".join(preview_lines).replace("  ", " ")[:160]
    print(f"  → {agent}: {preview}")

    # claude CLI 실행
    base_cmd = [
        "claude", "--agent", agent, "--print", "--verbose",
        "--output-format", "stream-json", "--include-partial-messages",
        "--max-budget-usd", "2.00",
        "--permission-mode", "bypassPermissions",
        "--disallowedTools", "Agent",
        "--fallback-model", "haiku",
    ]
    if config and getattr(config, "isolation", ""):
        base_cmd += ["--isolation", config.isolation]
    cmd = base_cmd + ["-p", full_prompt]

    env = os.environ.copy()
    env["HARNESS_INTERNAL"] = "1"
    env["HARNESS_PREFIX"] = prefix_for_flag

    run_log_path = str(run_logger.path) if run_logger else "/dev/null"

    # stream-json 파싱으로 result/cost/stats 추출
    result_text = ""
    cost = 0.0
    in_tok = 0
    out_tok = 0
    tools: Dict[str, int] = {}
    files_read: List[str] = []
    cur_tool = ""
    cur_input = ""

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=env, text=True,
        )

        log_fh = None
        if run_logger:
            log_fh = open(run_log_path, "a", encoding="utf-8")

        deadline = time.time() + timeout_secs
        assert proc.stdout is not None

        # Watchdog: stdout 블로킹 시에도 타임아웃 강제 (bash timeout 명령 대응)
        import threading
        def _watchdog() -> None:
            remaining = deadline - time.time()
            if remaining > 0:
                time.sleep(remaining)
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        wd = threading.Thread(target=_watchdog, daemon=True)
        wd.start()

        for line in proc.stdout:
            # tee to RUN_LOG
            if log_fh:
                log_fh.write(line)
                log_fh.flush()

            line = line.strip()
            if not line:
                continue

            try:
                o = json.loads(line)
                t = o.get("type", "")

                if t == "result":
                    result_text = o.get("result", "")
                    cost = float(o.get("total_cost_usd", 0) or 0)
                    usage = o.get("usage", {})
                    if usage:
                        in_tok = usage.get("input_tokens", 0)
                        out_tok = usage.get("output_tokens", 0)

                elif t == "stream_event":
                    e = o.get("event", {})
                    et = e.get("type", "")

                    if et == "content_block_start":
                        cb = e.get("content_block", {})
                        if cb.get("type") == "tool_use":
                            name = cb.get("name", "unknown")
                            tools[name] = tools.get(name, 0) + 1
                            cur_tool = name
                            cur_input = ""

                    elif et == "content_block_delta":
                        d = e.get("delta", {})
                        if d.get("type") == "input_json_delta" and cur_tool in ("Read", "Glob", "Grep"):
                            cur_input += d.get("partial_json", "")

                    elif et == "content_block_stop":
                        if cur_tool in ("Read", "Glob") and cur_input:
                            try:
                                inp = json.loads(cur_input)
                                fp = inp.get("file_path", "") or inp.get("pattern", "")
                                if fp:
                                    files_read.append(fp)
                            except Exception:
                                pass
                        cur_tool = ""
                        cur_input = ""

                    elif et == "message_delta":
                        u = e.get("usage", {})
                        if u and in_tok == 0:
                            in_tok += u.get("input_tokens", 0)
                            out_tok += u.get("output_tokens", 0)
            except Exception:
                pass

            # 타임아웃 체크
            if time.time() > deadline:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                call_exit = 124
                break

        if call_exit == 0:
            proc.wait()
            call_exit = proc.returncode or 0

    except Exception as exc:
        call_exit = 1
    finally:
        if log_fh:
            log_fh.close()

    # 결과 파일 기록
    try:
        cost_file.write_text(str(cost))
        out_file.write_text(result_text)
        stats_file.write_text(json.dumps(
            {"tools": tools, "files_read": files_read[:50], "in_tok": in_tok, "out_tok": out_tok},
            ensure_ascii=False,
        ))
    except OSError:
        pass

    t_end = int(time.time())
    duration_s = t_end - t_start

    # agent_end 이벤트
    if run_logger:
        run_logger.log_agent_end(agent, duration_s, cost, call_exit, len(full_prompt))

    # agent_stats 이벤트
    if run_logger:
        run_logger.log_agent_stats(agent, tools, files_read, in_tok, out_tok)

    # 히스토리: 아웃풋 원문 + stats 보존
    if hist_dir and Path(hist_dir).is_dir():
        try:
            import shutil
            shutil.copy2(str(out_file), str(Path(hist_dir) / f"{agent}.out"))
            shutil.copy2(str(stats_file), str(Path(hist_dir) / f"{agent}.stats.json"))
        except Exception:
            pass

    # 에이전트 active 플래그 해제
    active_flag.unlink(missing_ok=True)

    # 토큰 통계 표시
    if call_exit == 0:
        print(f"[HARNESS] ← {agent} 완료 ({duration_s}s | ${cost} | in:{in_tok} out:{out_tok}tok)")
    elif call_exit in (124, 142):
        print(f"[HARNESS] ← {agent} 타임아웃 ({duration_s}s)")
    else:
        print(f"[HARNESS] ← {agent} 실패 ({duration_s}s, exit={call_exit})")

    # 출력 미리보기 (80줄 이하: 전체, 초과: 앞50 + 뒤20)
    if out_file.exists() and out_file.stat().st_size > 0:
        lines = out_file.read_text(encoding="utf-8", errors="replace").splitlines()
        total_lines = len(lines)
        print(f"┌── {agent} 출력 ({total_lines}줄) ────────────────────────────")
        if total_lines <= 80:
            print("\n".join(lines))
        else:
            print("\n".join(lines[:50]))
            print(f"│ ··· ({total_lines - 70}줄 중략) ···")
            print("\n".join(lines[-20:]))
        print("└────────────────────────────────────────────────────────────")

    return call_exit


# ═══════════════════════════════════════════════════════════════════════
# 7. Git 유틸 — utils.sh의 git 관련 함수들
# ═══════════════════════════════════════════════════════════════════════

def _git(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    """git 명령 실행 헬퍼."""
    return subprocess.run(
        ["git"] + list(args),
        capture_output=True, text=True, timeout=30,
        check=check,
    )


def _default_branch() -> str:
    """원격 기본 브랜치 감지."""
    r = _git("symbolic-ref", "refs/remotes/origin/HEAD")
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().replace("refs/remotes/origin/", "")
    return "main"


def create_feature_branch(branch_type: str, issue_num: str | int) -> str:
    """Feature branch 생성. 동일 브랜치 존재 시 재진입."""
    issue_num = str(issue_num)

    # milestone: GitHub 이슈에서 읽기
    milestone = ""
    try:
        r = subprocess.run(
            ["gh", "issue", "view", issue_num, "--json", "milestone", "-q", ".milestone.title"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            milestone = re.sub(r"[^a-z0-9-]", "-", r.stdout.strip().lower())
            milestone = re.sub(r"-+", "-", milestone).strip("-")
    except Exception:
        pass

    # slug: issue title → 영문/숫자, 30자 캡
    slug = ""
    try:
        r = subprocess.run(
            ["gh", "issue", "view", issue_num, "--json", "title", "-q", ".title"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            raw = r.stdout.strip().lower()
            raw = re.sub(r"[^a-z0-9 -]", "", raw)
            raw = re.sub(r"\s+", " ", raw).strip()
            slug = re.sub(r"-+", "-", raw.replace(" ", "-")).strip("-")[:30]
    except Exception:
        pass

    # 브랜치명 조립
    branch_name = f"{branch_type}/"
    if milestone:
        branch_name += f"{milestone}-"
    branch_name += issue_num
    if slug:
        branch_name += f"-{slug}"

    default = _default_branch()

    # 이미 동일 브랜치 존재 → 체크아웃만 (재진입)
    r = _git("show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}")
    if r.returncode == 0:
        _git("checkout", branch_name)
        return branch_name

    _git("checkout", "-b", branch_name, default)
    return branch_name


def merge_to_main(
    branch: str,
    issue: str | int,
    depth: str,
    prefix: str,
    state_dir: Optional[StateDir] = None,
) -> bool:
    """Feature branch → main 머지. 반환: True=성공."""
    default = _default_branch()

    # state_dir 없으면 현재 디렉토리 기준으로 생성
    if state_dir is None:
        state_dir = StateDir(Path.cwd(), prefix)

    # 머지 전 게이트 (depth별 분기)
    if depth in ("fast", "std", "deep"):
        if not state_dir.flag_exists(Flag.PR_REVIEWER_LGTM):
            print(f"[HARNESS] merge 거부: pr_reviewer_lgtm 없음 ({depth})")
            return False
    if depth == "deep":
        if not state_dir.flag_exists(Flag.SECURITY_REVIEW_PASSED):
            print("[HARNESS] merge 거부: security_review_passed 없음 (deep)")
            return False
    if depth == "bugfix":
        if not state_dir.flag_exists(Flag.VALIDATOR_B_PASSED):
            print("[HARNESS] merge 거부: validator_b_passed 없음 (bugfix)")
            return False

    _git("checkout", default)

    merge_msg = f"merge: {branch} (#{issue})"
    r = _git("merge", "--no-ff", "-m", merge_msg, branch)
    if r.returncode != 0:
        _git("merge", "--abort")
        _git("checkout", branch)
        print("MERGE_CONFLICT_ESCALATE")
        return False

    _git("branch", "-d", branch)
    return True


def generate_commit_msg(impl_file: str = "", issue_num: str | int = "") -> str:
    """커밋 메시지 생성."""
    if impl_file:
        impl_name = Path(impl_file).stem
    else:
        impl_name = f"bugfix-{issue_num or 'unknown'}"

    r = _git("diff", "--cached", "--name-only")
    changed = " ".join(r.stdout.strip().splitlines()[:5]) if r.returncode == 0 else "(파일 목록 없음)"

    return (
        f"feat: implement {impl_name} (#{issue_num})\n"
        f"\n"
        f"[왜] Issue #{issue_num} 구현\n"
        f"[변경]\n"
        f"- {changed}\n"
        f"\n"
        f"Closes #{issue_num}\n"
        f"\n"
        f"Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
    )


def collect_changed_files() -> List[str]:
    """변경된 파일 목록. 변경 없으면 빈 리스트."""
    r = _git("status", "--short")
    if r.returncode != 0:
        return []
    files = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if re.match(r"^( M|M |A )", line):
            parts = line.split(None, 1)
            if len(parts) >= 2:
                files.append(parts[1])
    return files


def harness_commit_and_merge(
    branch: str,
    issue: str | int,
    depth: str,
    prefix: str,
    suffix: str = "",
    state_dir: Optional[StateDir] = None,
    impl_file: str = "",
) -> bool:
    """커밋 + 머지 일괄 처리. True=성공(HARNESS_DONE)."""
    changed = collect_changed_files()
    if changed:
        _git("add", "--", *changed)
        msg = generate_commit_msg(impl_file, issue)
        if suffix:
            msg += f" {suffix}"
        _git("commit", "-m", msg)

    if not merge_to_main(branch, issue, depth, prefix, state_dir):
        os.environ["HARNESS_RESULT"] = "MERGE_CONFLICT_ESCALATE"
        print("MERGE_CONFLICT_ESCALATE")
        print(f"branch: {branch}")
        return False

    return True


# ═══════════════════════════════════════════════════════════════════════
# 8. 컨텍스트 빌더 — utils.sh의 컨텍스트 함수들
# ═══════════════════════════════════════════════════════════════════════

def extract_src_refs(filepath: str | Path) -> List[str]:
    """impl 파일에서 참조된 src/ 경로를 추출."""
    try:
        content = Path(filepath).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    matches = re.findall(r"src/[^ `\"']+\.(?:ts|tsx|js|jsx)", content)
    return sorted(set(matches))[:5]


def extract_files_from_error(error_text: str) -> List[str]:
    """error trace에서 src/ 경로 역추적."""
    matches = re.findall(r"src/[^ :()]+\.(?:ts|tsx|js|jsx)", error_text)
    return sorted(set(matches))[:5]


def build_smart_context(
    impl: str | Path,
    attempt_n: int,
    err_trace: str = "",
) -> str:
    """스마트 컨텍스트 구성. 30KB 캡."""
    impl = Path(impl)
    ctx = ""

    if attempt_n == 0:
        try:
            ctx = impl.read_text(encoding="utf-8", errors="replace")
        except OSError:
            ctx = ""
        for f in extract_src_refs(impl):
            fp = Path(f)
            if fp.is_file():
                try:
                    chunk = fp.read_bytes()[:3000].decode("utf-8", errors="replace")
                    ctx += f"\n=== {f} ===\n{chunk}"
                except OSError:
                    pass
    else:
        # retry 시에도 impl 포함 (engineer(N) Read 낭비 방지)
        try:
            ctx = impl.read_bytes()[:6000].decode("utf-8", errors="replace")
        except OSError:
            ctx = ""
        failed_files = extract_files_from_error(err_trace)
        for f in failed_files:
            fp = Path(f)
            if fp.is_file():
                try:
                    content = fp.read_text(encoding="utf-8", errors="replace")
                    ctx += f"\n=== {f} ===\n{content}"
                except OSError:
                    pass

    return ctx[:30000]


def build_loop_context(loop_type: str) -> str:
    """루프 타입별 진입 컨텍스트 구성. 8KB 캡."""
    ctx = ""

    # 공통: 기술 스택 + .env 존재 여부
    pkg_json = Path("package.json")
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text())
            deps = list(data.get("dependencies", {}).keys())[:10]
            dev_deps = list(data.get("devDependencies", {}).keys())[:5]
            all_deps = deps + dev_deps
            if all_deps:
                ctx += "\n=== 기술 스택 ===\n" + "\n".join(all_deps)
        except Exception:
            pass

    env_example = Path(".env.example")
    env_file = Path(".env")
    if env_example.exists():
        try:
            keys = re.findall(r"^[A-Z_]+", env_example.read_text(), re.MULTILINE)[:10]
            if keys:
                ctx += "\n=== 환경변수 키 목록 ===\n" + "\n".join(keys)
        except OSError:
            pass
    elif env_file.exists():
        ctx += "\n=== .env 존재 ===\n(.env 파일 있음 — 내용 생략)"

    if loop_type == "design":
        comp_dir = Path("src/components")
        if comp_dir.is_dir():
            try:
                components = sorted(
                    str(p) for p in comp_dir.rglob("*.tsx")
                )[:20]
                components += sorted(
                    str(p) for p in comp_dir.rglob("*.ts")
                )[:20]
                components = sorted(set(components))[:20]
                if components:
                    ctx += "\n=== src/components/ 트리 ===\n" + "\n".join(components)
            except OSError:
                pass
        if Path("tailwind.config.ts").exists() or Path("tailwind.config.js").exists():
            ctx += "\n=== tailwind config 존재 ===\n(tailwind.config.ts/js 있음)"

    elif loop_type == "bugfix":
        r = _git("log", "--oneline", "-5")
        if r.returncode == 0 and r.stdout.strip():
            ctx += "\n=== 최근 커밋 5개 ===\n" + r.stdout.strip()
        r = _git("diff", "HEAD", "--stat")
        if r.returncode == 0 and r.stdout.strip():
            stat_lines = r.stdout.strip().splitlines()[-5:]
            ctx += "\n=== 현재 변경 통계 ===\n" + "\n".join(stat_lines)

    elif loop_type == "plan":
        docs_dir = Path("docs")
        if docs_dir.is_dir():
            try:
                docs = sorted(str(p) for p in docs_dir.rglob("*.md"))[:15]
                if docs:
                    ctx += "\n=== docs/ 문서 목록 ===\n" + "\n".join(docs)
            except OSError:
                pass
        backlog = Path("backlog.md")
        if backlog.exists():
            try:
                lines = backlog.read_text(encoding="utf-8").splitlines()[:30]
                ctx += "\n=== backlog.md (첫 30줄) ===\n" + "\n".join(lines)
            except OSError:
                pass

    # impl은 build_smart_context()가 담당 — 추가 컨텍스트 없음

    return ctx[:8192]


def build_validator_context(impl_file: str | Path) -> str:
    """validator용 impl + git diff 컨텍스트. 20KB 캡."""
    ctx = ""
    impl_path = Path(impl_file)
    if impl_path.exists():
        try:
            ctx = impl_path.read_bytes()[:10000].decode("utf-8", errors="replace")
        except OSError:
            pass

    r = _git("diff", "HEAD")
    if r.returncode == 0 and r.stdout.strip():
        diff_chunk = r.stdout[:15000]
        ctx += f"\n\n=== git diff (changed files) ===\n{diff_chunk}"

    return ctx[:20000]


def explore_instruction(out_dir: str, hint_file: str = "", handoff_path: str = "") -> str:
    """에이전트 자율 탐색 지시 템플릿. handoff_path가 있으면 인수인계 문서 우선."""
    instr = (
        f"이전 시도의 출력 파일이 아래 경로에 있다:\n"
        f"  {out_dir}/\n"
        f"ls로 attempt-N/ 디렉토리를 확인하고, 각 attempt의 meta.json을 먼저 읽어 개요를 파악하라.\n"
        f"이후 필요한 파일만 선택적으로 읽어라.\n"
        f"[탐색 예산] 최대 5개 파일, 합계 100KB 이내. 초과 금지."
    )
    if hint_file:
        instr += f"\n힌트: {hint_file} 에 직접적인 실패 정보가 있다."
    if handoff_path:
        instr = (
            f"인수인계 문서를 먼저 읽어라:\n"
            f"  {handoff_path}\n"
            f"이 문서에 변경 요약, 결정 사항, 확인할 것이 정리돼 있다.\n"
            f"상세 로그가 필요하면 {out_dir}/ 참조.\n"
            f"[탐색 예산] 최대 5개 파일, 합계 100KB 이내."
        )
    return instr


# ═══════════════════════════════════════════════════════════════════════
# 8.5 Handoff 문서 생성 — 에이전트 간 구조화된 인수인계
# ═══════════════════════════════════════════════════════════════════════

def generate_handoff(
    from_agent: str,
    to_agent: str,
    agent_output: str,
    impl_file: str,
    attempt: int,
    issue_num: str | int = "",
    changed_files: Optional[List[str]] = None,
    acceptance_criteria: Optional[List[str]] = None,
) -> str:
    """에이전트 출력 + git diff에서 handoff 문서 자동 생성.

    에이전트가 직접 작성하지 않음 — 하네스가 자동 생성.
    """
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    # 변경 파일 목록 (미제공 시 git diff에서 추출)
    if changed_files is None:
        r = _git("diff", "HEAD~1", "--stat")
        if r.returncode == 0 and r.stdout.strip():
            changed_files = [
                line.split("|")[0].strip()
                for line in r.stdout.strip().splitlines()[:-1]  # 마지막 summary 줄 제외
                if "|" in line
            ]
        else:
            changed_files = []

    # 결정 사항 추출 (에이전트 출력에서 키워드 주변 문장)
    decisions: List[str] = []
    cautions: List[str] = []
    for line in agent_output.splitlines():
        line_lower = line.lower().strip()
        if not line_lower:
            continue
        # 결정 키워드
        if any(kw in line_lower for kw in ("결정:", "선택:", "트레이드오프:", "이유:", "decision:", "chose")):
            decisions.append(f"- {line.strip()}")
        # 주의 키워드
        if any(kw in line_lower for kw in ("주의:", "warning:", "caution:", "주의사항", "변경 금지", "삭제 금지")):
            cautions.append(f"- {line.strip()}")

    # SPEC_GAP 갭 목록 추출
    gaps: List[str] = []
    in_gap = False
    for line in agent_output.splitlines():
        if "SPEC_GAP_FOUND" in line:
            in_gap = True
            continue
        if in_gap:
            stripped = line.strip()
            if stripped.startswith(("1.", "2.", "3.", "4.", "5.", "-", "*")):
                gaps.append(f"- {stripped.lstrip('0123456789.-* ')}")
            elif stripped.startswith("요청:") or stripped.startswith("request:"):
                break
            elif not stripped:
                if gaps:
                    break

    # 문서 조립
    sections: List[str] = []
    sections.append(f"# Handoff: {from_agent} → {to_agent}")
    sections.append(f"attempt: {attempt}")
    sections.append(f"timestamp: {ts}")
    if impl_file:
        sections.append(f"impl: {impl_file}")
    if issue_num:
        sections.append(f"issue: #{issue_num}")
    sections.append("")

    # 변경 요약
    sections.append("## 변경 요약")
    if changed_files:
        for f in changed_files[:10]:
            sections.append(f"- {f}")
    else:
        sections.append("- (변경 파일 정보 없음)")
    sections.append("")

    # 결정 사항
    if decisions:
        sections.append("## 결정 사항")
        sections.extend(decisions[:5])
        sections.append("")

    # 주의 사항
    if cautions:
        sections.append("## 주의 사항")
        sections.extend(cautions[:5])
        sections.append("")

    # SPEC_GAP 갭 목록
    if gaps:
        sections.append("## SPEC_GAP 항목")
        sections.extend(gaps[:5])
        sections.append("")

    # 다음 단계에서 확인할 것 (수용 기준 기반)
    sections.append("## 다음 단계에서 확인할 것")
    if acceptance_criteria:
        for ac in acceptance_criteria[:8]:
            sections.append(f"- {ac}")
    elif changed_files:
        sections.append(f"- 변경된 파일({len(changed_files)}개)의 기능이 정상 동작하는지 확인")
    else:
        sections.append("- (수용 기준 정보 없음 — impl 파일 참조)")

    return "\n".join(sections) + "\n"


def write_handoff(
    state_dir: "StateDir",
    prefix: str,
    attempt: int,
    from_agent: str,
    to_agent: str,
    content: str,
) -> Path:
    """handoff 문서를 파일로 저장하고 경로 반환."""
    handoff_dir = state_dir.path / f"{prefix}_handoffs" / f"attempt-{attempt}"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{from_agent}-to-{to_agent}.md"
    path = handoff_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


# ═══════════════════════════════════════════════════════════════════════
# 9. 히스토리 관리
# ═══════════════════════════════════════════════════════════════════════

def write_attempt_meta(meta_file: str | Path, **kwargs: Any) -> None:
    """attempt 결과 meta.json 기록 (json 모듈, jq 불필요)."""
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    data = {
        "attempt": kwargs.get("attempt", 0),
        "timestamp": ts,
        "loop": kwargs.get("loop", ""),
        "depth": kwargs.get("depth", ""),
        "result": kwargs.get("result", ""),
        "fail_type": kwargs.get("fail_type", ""),
        "failed_tests": kwargs.get("failed_tests", ""),
        "changed_files": kwargs.get("changed_files", ""),
        "agent_sequence": kwargs.get("agent_sequence", ""),
        "error_summary_oneline": kwargs.get("error_summary", ""),
        "next_action_hints": kwargs.get("next_hints", ""),
    }
    # attempt를 int로 변환 시도
    try:
        data["attempt"] = int(data["attempt"])
    except (ValueError, TypeError):
        pass

    try:
        Path(meta_file).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def prune_history(loop_dir: str | Path, max_runs: int = 5) -> None:
    """히스토리 정리.

    - run_* 디렉토리 N개 초과 → 오래된 run의 .out/.log 삭제 (meta.json + .prompt 보존)
    - 레거시 attempt-* 동일 처리
    - design round-* 3개 초과 → 오래된 round의 screenshots/ + 로그 삭제
    - 단일 로그 > 50KB → 마지막 500줄만 유지
    - 전체 history/ > 5MB → 오래된 로그 삭제
    """
    loop_dir = Path(loop_dir)
    if not loop_dir.is_dir():
        return

    # 조건 1: run_* 디렉토리
    runs = sorted(loop_dir.glob("run_*"), key=lambda p: p.name)
    if len(runs) > max_runs:
        for old_run in runs[: len(runs) - max_runs]:
            for f in old_run.rglob("*"):
                if f.is_file() and f.name not in ("meta.json",) and not f.suffix == ".prompt":
                    f.unlink(missing_ok=True)

    # 레거시: attempt-* 직접 있는 경우
    attempts = sorted(loop_dir.glob("attempt-*"), key=lambda p: p.name)
    if len(attempts) > max_runs:
        for old_att in attempts[: len(attempts) - max_runs]:
            for f in old_att.rglob("*"):
                if f.is_file() and f.name != "meta.json":
                    f.unlink(missing_ok=True)

    # design round-* 3개 초과
    rounds = sorted(loop_dir.glob("round-*"), key=lambda p: p.name)
    if len(rounds) > 3:
        for old_round in rounds[: len(rounds) - 3]:
            screenshots_dir = old_round / "screenshots"
            if screenshots_dir.is_dir():
                import shutil
                shutil.rmtree(screenshots_dir, ignore_errors=True)
            for f in old_round.rglob("*"):
                if f.is_file() and f.name not in ("meta.json", "critic.log"):
                    f.unlink(missing_ok=True)

    # 단일 로그 > 50KB → 마지막 500줄만 유지
    for logf in loop_dir.rglob("*.log"):
        try:
            if logf.stat().st_size > 50 * 1024:
                lines = logf.read_text(encoding="utf-8", errors="replace").splitlines()
                logf.write_text("\n".join(lines[-500:]) + "\n", encoding="utf-8")
        except OSError:
            pass

    # 전체 history/ > 5MB → 오래된 로그 삭제
    hist_root = loop_dir.parent
    try:
        total_size = sum(f.stat().st_size for f in hist_root.rglob("*") if f.is_file())
        if total_size > 5 * 1024 * 1024:
            log_files = sorted(hist_root.rglob("*.log"), key=lambda p: p.name)
            for lf in log_files[:5]:
                lf.unlink(missing_ok=True)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════
# 10. 유틸
# ═══════════════════════════════════════════════════════════════════════

def hlog(msg: str, state_dir: Optional[StateDir] = None, prefix: str = "") -> None:
    """타임스탬프 디버그 로그. bash의 hlog()와 동일 — tee -a 방식."""
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)

    # 로그 파일 경로: HLOG env → state_dir → prefix 폴백 (bash와 동일 우선순위)
    log_path_str = os.environ.get("HLOG", "")
    if log_path_str:
        log_path: Optional[Path] = Path(log_path_str)
    elif state_dir:
        log_path = state_dir.path / f"{state_dir.prefix}-harness-debug.log"
    elif prefix:
        # bash: ${STATE_DIR}/${PREFIX:-mb}-harness-debug.log 폴백
        log_path = Path("/tmp") / f"{prefix}-harness-debug.log"
    else:
        log_path = None

    if log_path:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


def kill_check(state_dir: StateDir) -> None:
    """kill 플래그 확인 → sys.exit."""
    if state_dir.flag_exists(Flag.HARNESS_KILL):
        state_dir.flag_rm(Flag.HARNESS_ACTIVE)
        state_dir.flag_rm(Flag.HARNESS_KILL)
        os.environ["HARNESS_RESULT"] = "HARNESS_KILLED"
        print("HARNESS_KILLED: 사용자 요청으로 중단됨")
        sys.exit(0)


def detect_depth(impl_file: str | Path) -> str:
    """frontmatter depth: 파싱."""
    impl = Path(impl_file)
    if not impl.exists():
        return "std"
    try:
        content = impl.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "std"

    # YAML frontmatter --- ... --- 블록 내 depth: 필드
    in_frontmatter = False
    fence_count = 0
    for line in content.splitlines():
        if line.strip() == "---":
            fence_count += 1
            if fence_count == 1:
                in_frontmatter = True
                continue
            elif fence_count == 2:
                break
        if in_frontmatter:
            m = re.match(r"^depth:\s*(\S+)", line)
            if m:
                val = re.sub(r"\s*#.*", "", m.group(1))
                if val in ("simple", "std", "deep"):
                    return val
                return "std"
    return "std"


# ═══════════════════════════════════════════════════════════════════════
# 11. Plan/Design Validation
# ═══════════════════════════════════════════════════════════════════════

def run_plan_validation(
    impl_file: str,
    issue_num: str | int,
    prefix: str,
    max_rework: int = 1,
    state_dir: Optional[StateDir] = None,
    run_logger: Optional[RunLogger] = None,
    config: Optional[HarnessConfig] = None,
    handoff_path: Optional[str] = None,
) -> bool:
    """Plan Validation 실행. True=PASS, False=ESCALATE."""
    if state_dir is None:
        state_dir = StateDir(Path.cwd(), prefix)

    val_out = str(state_dir.path / f"{prefix}_val_pv_out.txt")

    handoff_hint = f"\n인수인계 문서: {handoff_path}" if handoff_path else ""
    print("[HARNESS] Plan Validation")
    agent_call(
        "validator", 300,
        f"@MODE:VALIDATOR:PLAN_VALIDATION\nimpl: {impl_file} issue: #{issue_num}{handoff_hint}",
        val_out, run_logger, config,
    )
    val_result = parse_marker(val_out, "PLAN_VALIDATION_PASS|PLAN_VALIDATION_FAIL|PASS|FAIL")
    if val_result == "PLAN_VALIDATION_PASS":
        val_result = "PASS"
    if val_result == "PLAN_VALIDATION_FAIL":
        val_result = "FAIL"
    print(f"[HARNESS] Plan Validation 결과: {val_result}")

    if val_result == "PASS":
        state_dir.flag_touch(Flag.PLAN_VALIDATION_PASSED)
        # Handoff: validator → engineer
        try:
            val_content = Path(val_out).read_text(encoding="utf-8", errors="replace")
            _val_handoff = generate_handoff(
                "validator", "engineer", val_content,
                impl_file, 0, str(issue_num),
            )
            write_handoff(state_dir, prefix, 0, "validator", "engineer", _val_handoff)
            if run_logger:
                run_logger.log_event({
                    "event": "handoff", "from": "validator", "to": "engineer",
                    "t": int(time.time()),
                })
        except OSError:
            pass
        return True

    # FAIL → architect 재보강
    for rework in range(1, max_rework + 1):
        print(f"[HARNESS] Plan Validation FAIL → architect 재보강 ({rework}/{max_rework})")
        fail_feedback = ""
        try:
            lines = Path(val_out).read_text().splitlines()
            fail_feedback = "\n".join(lines[-20:])
        except OSError:
            pass

        arch_out = str(state_dir.path / f"{prefix}_arch_fix_out.txt")
        agent_call(
            "architect", 900,
            f"@MODE:ARCHITECT:SPEC_GAP\nPlan Validation FAIL 피드백 반영. impl: {impl_file} feedback: {fail_feedback}",
            arch_out, run_logger, config,
        )

        val_out2 = str(state_dir.path / f"{prefix}_val_pv_out{rework}.txt")
        agent_call(
            "validator", 300,
            f"@MODE:VALIDATOR:PLAN_VALIDATION\nimpl: {impl_file} issue: #{issue_num}",
            val_out2, run_logger, config,
        )
        val_result = parse_marker(val_out2, "PLAN_VALIDATION_PASS|PLAN_VALIDATION_FAIL|PASS|FAIL")
        if val_result == "PLAN_VALIDATION_PASS":
            val_result = "PASS"
        if val_result == "PLAN_VALIDATION_FAIL":
            val_result = "FAIL"
        print(f"[HARNESS] Plan Validation 재검증 결과: {val_result}")

        if val_result == "PASS":
            state_dir.flag_touch(Flag.PLAN_VALIDATION_PASSED)
            return True

    return False


def run_design_validation(
    design_doc: str,
    issue_num: str | int,
    prefix: str,
    max_rework: int = 1,
    state_dir: Optional[StateDir] = None,
    run_logger: Optional[RunLogger] = None,
    config: Optional[HarnessConfig] = None,
) -> bool:
    """Design Validation 실행. True=PASS, False=ESCALATE."""
    if state_dir is None:
        state_dir = StateDir(Path.cwd(), prefix)

    val_out = str(state_dir.path / f"{prefix}_val_dv_out.txt")

    print("[HARNESS] Design Validation")
    agent_call(
        "validator", 300,
        f"@MODE:VALIDATOR:DESIGN_VALIDATION\ndesign_doc: {design_doc} issue: #{issue_num}",
        val_out, run_logger, config,
    )
    val_result = parse_marker(val_out, "DESIGN_REVIEW_PASS|DESIGN_REVIEW_FAIL|PASS|FAIL")
    if val_result == "DESIGN_REVIEW_PASS":
        val_result = "PASS"
    if val_result == "DESIGN_REVIEW_FAIL":
        val_result = "FAIL"
    print(f"[HARNESS] Design Validation 결과: {val_result}")

    if val_result == "PASS":
        return True

    for rework in range(1, max_rework + 1):
        print(f"[HARNESS] Design Validation FAIL → architect 재설계 ({rework}/{max_rework})")
        fail_feedback = ""
        try:
            lines = Path(val_out).read_text().splitlines()
            fail_feedback = "\n".join(lines[-20:])
        except OSError:
            pass

        arch_out = str(state_dir.path / f"{prefix}_arch_dv_fix_out.txt")
        agent_call(
            "architect", 900,
            f"@MODE:ARCHITECT:SYSTEM_DESIGN\n재설계 — Design Validation FAIL 피드백 반영. design_doc: {design_doc} feedback: {fail_feedback}",
            arch_out, run_logger, config,
        )

        val_out2 = str(state_dir.path / f"{prefix}_val_dv_out{rework}.txt")
        agent_call(
            "validator", 300,
            f"@MODE:VALIDATOR:DESIGN_VALIDATION\ndesign_doc: {design_doc} issue: #{issue_num}",
            val_out2, run_logger, config,
        )
        val_result = parse_marker(val_out2, "DESIGN_REVIEW_PASS|DESIGN_REVIEW_FAIL|PASS|FAIL")
        if val_result == "DESIGN_REVIEW_PASS":
            val_result = "PASS"
        if val_result == "DESIGN_REVIEW_FAIL":
            val_result = "FAIL"
        print(f"[HARNESS] Design Validation 재검증 결과: {val_result}")

        if val_result == "PASS":
            return True

    return False


# ═══════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════

def _detect_prefix() -> str:
    """현재 디렉토리의 prefix 감지 (agent_call 내부용)."""
    config_path = Path.cwd() / ".claude" / "harness.config.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
            p = data.get("prefix")
            if p:
                return p
        except Exception:
            pass
    raw = Path.cwd().name.lower()
    return re.sub(r"[^a-z0-9]", "", raw)[:8] or "proj"
