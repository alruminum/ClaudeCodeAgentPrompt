#!/usr/bin/env python3
"""
harness-review.py — JSONL 하네스 로그 파서 + 낭비 패턴 진단

사용법:
  python3 harness-review.py <jsonl_path>
  python3 harness-review.py --prefix mb          # 최신 로그 자동 탐색
  python3 harness-review.py --prefix mb --last 3  # 최근 3개 로그 분석
"""

import sys
import json
import os
import glob
import argparse
from datetime import datetime
from collections import defaultdict

# ── 상수 ──────────────────────────────────────────────────────────────

INFRA_PATTERNS = [
    ".claude/", "harness-", "orchestration-rules", "setup-harness",
    ".claude/hooks/", "settings.json", "harness-utils", "harness-loop",
    "harness-executor",
]

# agent-config/는 의도된 프로젝트 컨텍스트, handoff/는 에이전트 간 인수인계 — INFRA 분류 제외
INFRA_EXCLUSIONS = ["agent-config/", "handoff"]

EXPECTED_ELAPSED = {
    "engineer": 900,
    "test-engineer": 600,
    "validator": 300,
    "pr-reviewer": 180,
    "security-reviewer": 180,
    "qa": 300,
    "architect": 300,
    "designer": 300,
}

# 모드별 예상 에이전트 순서 (orchestration-rules.md 기준)
EXPECTED_SEQUENCE = {
    "bugfix": {
        "functional_bug": ["qa", "architect", "engineer", "validator"],
        "architect":       ["qa", "architect", "validator", "engineer"],
        "design":          ["qa", "designer", "design-critic"],
    },
    "impl": {
        "plan_only": ["architect", "validator"],
        "fast": ["engineer"],
        "simple": ["engineer", "pr-reviewer"],
        "std":  ["test-engineer", "engineer", "validator"],
        "deep": ["test-engineer", "engineer", "validator", "pr-reviewer", "security-reviewer"],
    },
    "design": ["designer", "design-critic"],
    "plan":   ["product-planner", "ux-architect", "validator"],
}

LOG_DIR = os.path.expanduser("~/.claude/harness-logs")


# ── 파서 ──────────────────────────────────────────────────────────────

def parse_jsonl(filepath):
    events = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                pass
    return events


def _reviewed_marker(jsonl_path):
    """JSONL 파일에 대응하는 .reviewed 마커 경로."""
    return jsonl_path.replace(".jsonl", ".reviewed")


def _is_reviewed(jsonl_path):
    return os.path.exists(_reviewed_marker(jsonl_path))


def _mark_reviewed(jsonl_path):
    open(_reviewed_marker(jsonl_path), "w").close()


def find_latest_logs(prefix, count=1):
    d = os.path.join(LOG_DIR, prefix)
    if os.path.isdir(d):
        files = sorted(glob.glob(os.path.join(d, "run_*.jsonl")), key=os.path.getmtime, reverse=True)
        return files[:count]
    # prefix가 run_ 패턴이면 전체 하위 디렉토리에서 JSONL 파일명 검색
    if prefix.startswith("run_"):
        stem = prefix.replace(".jsonl", "")
        matches = sorted(glob.glob(os.path.join(LOG_DIR, "*", f"{stem}.jsonl")),
                         key=os.path.getmtime, reverse=True)
        return matches[:count]
    return []


def find_unreviewed_logs(prefix):
    """prefix 디렉토리에서 .reviewed 마커가 없는 로그를 시간순(오래된 것 먼저) 반환."""
    d = os.path.join(LOG_DIR, prefix)
    if not os.path.isdir(d):
        return []
    files = sorted(glob.glob(os.path.join(d, "run_*.jsonl")), key=os.path.getmtime)
    return [f for f in files if not _is_reviewed(f)]


# ── 타임라인 추출 ────────────────────────────────────────────────────

def extract_run_info(events):
    info = {"prefix": "?", "mode": "?", "t_start": 0, "t_end": 0, "elapsed": 0}
    for e in events:
        if e.get("event") == "run_start":
            info["prefix"] = e.get("prefix", "?")
            info["mode"] = e.get("mode", "?")
            info["t_start"] = e.get("t", 0)
        elif e.get("event") == "run_end":
            info["t_end"] = e.get("t", 0)
            info["elapsed"] = e.get("elapsed", 0)
            info["run_end_result"] = e.get("result", "")
    if info["t_end"] == 0 and info["t_start"] > 0:
        # 비정상 종료 — 마지막 하네스 이벤트 시각 사용 (stream_event 제외)
        for e in reversed(events):
            t = e.get("t", 0)
            if t > 0 and e.get("type") != "stream_event":
                info["t_end"] = t
                info["elapsed"] = t - info["t_start"]
                break
        # 그래도 못 찾으면 stream_event에서 message timestamp 추출 시도
        if info["t_end"] == 0:
            last_ts = _find_last_timestamp(events)
            if last_ts > 0:
                info["t_end"] = last_ts
                info["elapsed"] = last_ts - info["t_start"]
    return info


def _find_last_timestamp(events):
    """stream_event 내 message.created_at 또는 하네스 이벤트 t 중 마지막 값"""
    last = 0
    for e in events:
        t = e.get("t", 0)
        if t > last:
            last = t
        # stream_event 내 message timestamp
        if e.get("type") == "stream_event":
            msg = e.get("event", {}).get("message", {})
            created = msg.get("created_at", 0)
            if isinstance(created, (int, float)) and created > last:
                last = int(created)
    return last


def extract_config(events):
    for e in events:
        if e.get("event") == "config":
            return e
    return {}


def extract_timeline(events):
    agents = []
    pending = {}
    for e in events:
        ev = e.get("event", "")
        if ev == "agent_start":
            agent = e.get("agent", "?")
            pending[agent] = {
                "agent": agent,
                "t_start": e.get("t", 0),
                "prompt_chars": e.get("prompt_chars", 0),
            }
        elif ev == "agent_end":
            agent = e.get("agent", "?")
            entry = pending.pop(agent, {"agent": agent, "t_start": 0, "prompt_chars": 0})
            entry.update({
                "t_end": e.get("t", 0),
                "elapsed": e.get("elapsed", 0),
                "exit": e.get("exit", 0),
                "cost_usd": e.get("cost_usd", 0),
                "prompt_chars": e.get("prompt_chars", entry.get("prompt_chars", 0)),
            })
            agents.append(entry)
    # 미완료 에이전트 (타임아웃/킬) — elapsed 추정
    run_end_t = 0
    for e in events:
        t = e.get("t", 0)
        if t > run_end_t and e.get("type") != "stream_event":
            run_end_t = t
    if run_end_t == 0:
        run_end_t = _find_last_timestamp(events)

    for agent, entry in pending.items():
        t_start = entry.get("t_start", 0)
        estimated = run_end_t - t_start if run_end_t > t_start else 0
        entry["t_end"] = run_end_t
        entry["elapsed"] = estimated
        entry["exit"] = -1
        entry["cost_usd"] = 0
        entry["status"] = "incomplete"
        agents.append(entry)
    return agents


def extract_agent_stats(events):
    """agent_stats 이벤트에서 도구 사용 + 파일 목록 추출"""
    stats = {}
    for e in events:
        if e.get("event") == "agent_stats":
            agent = e.get("agent", "?")
            stats[agent] = {
                "tools": e.get("tools", {}),
                "files_read": e.get("files_read", []),
                "in_tok": e.get("in_tok", 0),
                "out_tok": e.get("out_tok", 0),
            }
    return stats


def extract_tool_usage_from_stream(events):
    """stream_event에서 tool_use 직접 추출 (old format 호환)"""
    tools = defaultdict(int)
    files_read = []
    cur_tool = ""
    cur_input = ""

    for e in events:
        if e.get("type") != "stream_event":
            continue
        se = e.get("event", {})
        et = se.get("type", "")

        if et == "content_block_start":
            cb = se.get("content_block", {})
            if cb.get("type") == "tool_use":
                name = cb.get("name", "unknown")
                tools[name] += 1
                cur_tool = name
                cur_input = ""

        elif et == "content_block_delta":
            d = se.get("delta", {})
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

    return dict(tools), files_read


def extract_decisions(events):
    return [e for e in events if e.get("event") == "decision"]


def extract_phases(events):
    return [e for e in events if e.get("event") == "phase"]


def extract_contexts(events):
    return [e for e in events if e.get("event") == "context"]


# ── 낭비 패턴 탐지 ──────────────────────────────────────────────────

def detect_waste(timeline, agent_stats, stream_tools, stream_files, decisions, events=None):
    patterns = []

    # 핸드오프 이벤트에서 커버된 에이전트 쌍 추출
    handoff_pairs = set()
    if events:
        for e in events:
            if e.get("event") == "handoff":
                handoff_pairs.add((e.get("from", ""), e.get("to", "")))

    # 에이전트별 파일 목록 (new format 우선, 없으면 stream 파싱)
    all_files = {}
    for entry in timeline:
        agent = entry["agent"]
        if agent in agent_stats and agent_stats[agent]["files_read"]:
            all_files[agent] = agent_stats[agent]["files_read"]
        elif stream_files:
            all_files[agent] = stream_files  # old format: 에이전트 구분 불가

    all_tools = {}
    for entry in timeline:
        agent = entry["agent"]
        if agent in agent_stats and agent_stats[agent]["tools"]:
            all_tools[agent] = agent_stats[agent]["tools"]
        elif stream_tools:
            all_tools[agent] = stream_tools

    # WASTE_INFRA_READ: 인프라 파일 탐색
    for agent, files in all_files.items():
        infra_hits = [f for f in files if any(p in f for p in INFRA_PATTERNS) and not any(e in f for e in INFRA_EXCLUSIONS)]
        if infra_hits:
            patterns.append({
                "type": "WASTE_INFRA_READ",
                "severity": "HIGH",
                "agent": agent,
                "detail": f"{agent}가 인프라 파일 {len(infra_hits)}개 탐색",
                "files": infra_hits,
                "fix": f"~/.claude/agents/{agent}.md 프롬프트에 인프라 탐색 금지 강화",
            })

    # WASTE_SUB_AGENT: 서브에이전트 과다 스폰
    for agent, tools in all_tools.items():
        agent_count = tools.get("Agent", 0)
        if agent_count >= 2:
            patterns.append({
                "type": "WASTE_SUB_AGENT",
                "severity": "HIGH",
                "agent": agent,
                "detail": f"{agent}가 서브에이전트 {agent_count}개 스폰",
                "fix": f"~/.claude/agents/{agent}.md에 'Agent 도구 사용 금지' 추가",
            })

    # WASTE_TIMEOUT: 타임아웃 직전 + 결과 없음, 또는 incomplete(킬/중단)
    for entry in timeline:
        agent = entry["agent"]
        expected = EXPECTED_ELAPSED.get(agent, 300)
        is_timeout = entry["elapsed"] >= expected * 0.9 and entry["exit"] != 0
        is_incomplete = entry.get("status") == "incomplete" and entry["elapsed"] > 0
        if is_timeout or is_incomplete:
            status = "incomplete(킬/중단)" if is_incomplete else f"exit={entry['exit']}"
            patterns.append({
                "type": "WASTE_TIMEOUT",
                "severity": "MEDIUM",
                "agent": agent,
                "detail": f"{agent} {entry['elapsed']}s 소요 (한도 {expected}s) {status}",
                "fix": f"프롬프트 간결화 또는 타임아웃 조정",
            })

    # WASTE_NO_OUTPUT: 정상 종료인데 출력 없음
    for entry in timeline:
        if entry["exit"] == 0 and entry.get("status") == "incomplete":
            patterns.append({
                "type": "WASTE_NO_OUTPUT",
                "severity": "MEDIUM",
                "agent": entry["agent"],
                "detail": f"{entry['agent']} 정상 종료했으나 출력 비어있음",
                "fix": "에이전트 프롬프트에 출력 형식 명시",
            })

    # WASTE_HARNESS_EXEC: 에이전트가 하네스 스크립트 실행 시도
    for agent, tools in all_tools.items():
        bash_count = tools.get("Bash", 0)
        if bash_count > 0 and agent in ("qa", "validator", "pr-reviewer", "design-critic"):
            patterns.append({
                "type": "WASTE_HARNESS_EXEC",
                "severity": "HIGH",
                "agent": agent,
                "detail": f"{agent}(ReadOnly)가 Bash {bash_count}회 호출",
                "fix": f"~/.claude/agents/{agent}.md에 Bash 도구 사용 금지 명시",
            })

    # SLOW_PHASE: 비정상 지연 (기대값 2배 초과)
    for entry in timeline:
        agent = entry["agent"]
        expected = EXPECTED_ELAPSED.get(agent, 300)
        if entry["elapsed"] > expected * 2 and entry["exit"] == 0:
            patterns.append({
                "type": "SLOW_PHASE",
                "severity": "LOW",
                "agent": agent,
                "detail": f"{agent} {entry['elapsed']}s (기대 {expected}s의 {entry['elapsed']/expected:.1f}배)",
                "fix": "컨텍스트 크기 확인 — prompt_chars 과다 여부",
            })

    # RETRY_SAME_FAIL: 연속 동일 실패
    fail_types = [d["value"] for d in decisions if d.get("key") == "fail_type"]
    for i in range(1, len(fail_types)):
        if fail_types[i] == fail_types[i - 1]:
            patterns.append({
                "type": "RETRY_SAME_FAIL",
                "severity": "MEDIUM",
                "agent": "harness-loop",
                "detail": f"attempt {i}→{i+1} 동일 실패: {fail_types[i]}",
                "fix": "fail_type별 수정 전략 강화 또는 impl 파일 보강",
            })

    # CONTEXT_BLOAT: 프롬프트 크기 경고
    for entry in timeline:
        pc = entry.get("prompt_chars", 0)
        if pc > 40000:
            patterns.append({
                "type": "CONTEXT_BLOAT",
                "severity": "MEDIUM",
                "agent": entry["agent"],
                "detail": f"{entry['agent']} prompt_chars={pc} (40KB 초과)",
                "fix": "build_smart_context 50KB 캡 확인, impl 파일 정리",
            })

    # WASTE_CONTEXT_EXCESS: 에이전트 역할 대비 과도한 프롬프트
    # qa/validator/pr-reviewer는 분석 에이전트 — 20KB면 충분
    # architect는 설계 — 25KB면 충분
    PROMPT_LIMITS = {
        "qa": 20000, "validator": 20000, "pr-reviewer": 20000,
        "design-critic": 15000, "security-reviewer": 20000,
        "architect": 25000,
    }
    for entry in timeline:
        agent = entry["agent"]
        pc = entry.get("prompt_chars", 0)
        limit = PROMPT_LIMITS.get(agent)
        if limit and pc > limit:
            ratio = pc / limit
            patterns.append({
                "type": "WASTE_CONTEXT_EXCESS",
                "severity": "HIGH" if ratio > 3 else "MEDIUM",
                "agent": agent,
                "detail": f"{agent} prompt_chars={pc:,} (적정 {limit:,}의 {ratio:.1f}배)",
                "fix": f"harness/executor.sh에서 {agent} 호출 시 전달 컨텍스트 축소 — 전체 소스 대신 관련 부분만 전달",
            })

    # WASTE_SPARSE_PROMPT: 너무 적은 컨텍스트 → 에이전트가 MCP/Read로 재조회
    # architect/engineer에 500자 미만 프롬프트 + MCP 또는 Read 3회 이상이면 낭비
    SPARSE_AGENTS = {"architect", "engineer"}
    for entry in timeline:
        agent = entry["agent"]
        pc = entry.get("prompt_chars", 0)
        if agent not in SPARSE_AGENTS or pc == 0:
            continue
        if pc < 500:
            # 도구 사용량 확인
            tools = {}
            if agent in agent_stats and agent_stats[agent]["tools"]:
                tools = agent_stats[agent]["tools"]
            elif stream_tools:
                tools = stream_tools
            read_count = tools.get("Read", 0) + tools.get("Grep", 0) + tools.get("Glob", 0)
            mcp_count = sum(v for k, v in tools.items() if k.startswith("mcp__"))
            fetch_count = read_count + mcp_count
            if fetch_count >= 3:
                patterns.append({
                    "type": "WASTE_SPARSE_PROMPT",
                    "severity": "HIGH",
                    "agent": agent,
                    "detail": f"{agent} prompt {pc}자인데 Read/MCP {fetch_count}회 호출 — 컨텍스트 부족으로 재조회",
                    "fix": f"harness/executor.sh에서 {agent} 호출 시 qa_out/impl 내용을 프롬프트에 포함",
                })

    # WASTE_DUPLICATE_READ: 여러 에이전트가 동일 파일 중복 읽기
    file_readers = defaultdict(list)
    for agent, files in all_files.items():
        for f in files:
            # 인프라 파일은 이미 WASTE_INFRA_READ에서 잡으므로 제외
            if not any(p in f for p in INFRA_PATTERNS) or any(e in f for e in INFRA_EXCLUSIONS):
                file_readers[f].append(agent)
    for filepath, readers in file_readers.items():
        if len(readers) >= 3:
            # 핸드오프가 커버하는 에이전트 쌍인지 확인
            has_handoff = False
            if handoff_pairs:
                for i in range(len(readers) - 1):
                    if (readers[i], readers[i + 1]) in handoff_pairs:
                        has_handoff = True
                        break
            if has_handoff:
                patterns.append({
                    "type": "WASTE_DUPLICATE_READ",
                    "severity": "LOW",
                    "agent": readers[0],
                    "detail": f"`{os.path.basename(filepath)}` {len(readers)}개 에이전트가 중복 읽기: {', '.join(readers)} (핸드오프 있음)",
                    "fix": "에이전트 프롬프트에서 핸드오프 문서 우선 참조 지시 강화",
                })
            else:
                patterns.append({
                    "type": "WASTE_DUPLICATE_READ",
                    "severity": "MEDIUM",
                    "agent": readers[0],
                    "detail": f"`{os.path.basename(filepath)}` {len(readers)}개 에이전트가 중복 읽기: {', '.join(readers)}",
                    "fix": "generate_handoff 추가하여 에이전트 간 인수인계 문서 전달",
                })

    return patterns


def scan_session_log(session_jsonl, run_start_ts=0, run_end_ts=0):
    """메인 Claude 세션 JSONL에서 게이트 모순 시그널을 추출한다.

    시그널:
    - FLAG_BYPASS: rm/touch harness-state/ 명령 (메인 Claude가 게이트 수동 우회)
    - HOOK_BLOCK: hook이 도구 호출 차단 (is_error=true)
    - CONTRADICTION: HOOK_BLOCK → FLAG_BYPASS → 재시도 시퀀스 (게이트 모순 확정)
    """
    if not session_jsonl or not os.path.exists(session_jsonl):
        return []

    import re

    signals = []
    events_seq = []  # (event_idx, type, detail) 시퀀스 추적용

    try:
        with open(session_jsonl) as f:
            for i, line in enumerate(f):
                try:
                    e = json.loads(line)
                except Exception:
                    continue

                if e.get("type") == "assistant":
                    content = e.get("message", {}).get("content", [])
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        # FLAG_BYPASS: Bash로 rm/touch harness-state
                        if block.get("type") == "tool_use" and block.get("name") == "Bash":
                            cmd = block.get("input", {}).get("command", "")
                            if "harness-state" in cmd and re.search(r"\b(rm|touch)\b", cmd):
                                flags = re.findall(r"harness-state/\S+", cmd)
                                signals.append({
                                    "type": "FLAG_BYPASS",
                                    "severity": "HIGH",
                                    "detail": f"메인 Claude가 플래그 수동 조작: {cmd[:120]}",
                                    "flags": [f.split("/")[-1] for f in flags],
                                    "event_idx": i,
                                })
                                events_seq.append((i, "FLAG_BYPASS", cmd[:80]))

                elif e.get("type") == "user":
                    content = e.get("message", {}).get("content", "")
                    blocks = content if isinstance(content, list) else [content]
                    for block in blocks:
                        if not isinstance(block, dict):
                            continue
                        # HOOK_BLOCK: tool_result with is_error + hook
                        if block.get("type") == "tool_result" and block.get("is_error"):
                            text = str(block.get("content", ""))
                            if "hook" in text.lower() and ("denied" in text.lower() or "blocking" in text.lower()):
                                events_seq.append((i, "HOOK_BLOCK", text[:120]))
                                signals.append({
                                    "type": "HOOK_BLOCK",
                                    "severity": "MEDIUM",
                                    "detail": f"훅이 도구 호출 차단: {text[:120]}",
                                    "event_idx": i,
                                })
    except Exception:
        return []

    # CONTRADICTION 감지: HOOK_BLOCK → FLAG_BYPASS 시퀀스 (10 이벤트 이내)
    for j in range(len(events_seq)):
        if events_seq[j][1] == "HOOK_BLOCK":
            for k in range(j + 1, min(j + 5, len(events_seq))):
                if events_seq[k][1] == "FLAG_BYPASS":
                    signals.append({
                        "type": "GATE_CONTRADICTION",
                        "severity": "HIGH",
                        "detail": (
                            f"게이트 모순: 훅 차단 → 플래그 수동 우회\n"
                            f"  차단: {events_seq[j][2]}\n"
                            f"  우회: {events_seq[k][2]}"
                        ),
                        "event_idx": events_seq[j][0],
                    })
                    break

    return signals


def detect_waste_with_context(patterns, run_info, config, events):
    """실행 컨텍스트 기반 추가 낭비 패턴을 탐지한다."""
    depth = config.get("depth", "") if config else ""
    mode = run_info.get("mode", "")

    # WASTE_DEPTH_MISS: LIGHT_PLAN 경로(버그픽스)인데 depth=std/deep
    if mode == "impl" and depth in ("std", "deep"):
        is_light_plan = any(
            "LIGHT_PLAN" in str(e.get("marker", "")) or "LIGHT_PLAN" in str(e.get("event", ""))
            for e in events
        )
        if is_light_plan:
            patterns.append({
                "type": "WASTE_DEPTH_MISS",
                "severity": "HIGH",
                "agent": "harness",
                "detail": f"LIGHT_PLAN(버그픽스) 경로인데 depth={depth} — simple이었으면 test-engineer+validator+pr-reviewer 스킵 가능",
                "fix": "impl.sh LIGHT_PLAN 프롬프트의 depth 가이드 확인, architect가 simple 선택하도록 유도",
            })

    # WASTE_BOUNDARY_BLOCK: agent-boundary deny로 인한 attempt 낭비
    for e in events:
        if e.get("event") == "agent_boundary_deny":
            patterns.append({
                "type": "WASTE_BOUNDARY_BLOCK",
                "severity": "HIGH",
                "agent": e.get("agent", "unknown"),
                "detail": f"{e.get('agent', '?')}가 {e.get('fp', '?')} 접근 차단됨 — ALLOW_MATRIX 패턴 불일치",
                "fix": f"hooks/agent-boundary.py ALLOW_MATRIX['{e.get('agent', '?')}'] 패턴 확인",
            })

    # WASTE_REPEATED_SPEC_GAP: 동일 SPEC_GAP 2회 이상
    decisions = [e for e in events if e.get("event") == "decision"]
    spec_gaps = [d for d in decisions if d.get("key") == "spec_gap"]
    if len(spec_gaps) >= 2:
        patterns.append({
            "type": "WASTE_REPEATED_SPEC_GAP",
            "severity": "HIGH",
            "agent": "architect",
            "detail": f"SPEC_GAP {len(spec_gaps)}회 발생 — architect SPEC_GAP 해결 반복 실패",
            "fix": "impl 파일 보강 또는 architect SPEC_GAP 프롬프트 개선",
        })

    return patterns


# ── 흐름 진단 (비정상 종료 / 라우팅 불일치 / 단계 누락) ──────────


def detect_flow_issues(run_info, timeline, events):
    """orchestration-rules 기준으로 실제 흐름의 이상을 진단한다."""
    issues = []
    mode = run_info.get("mode", "?")
    agents_ran = [e["agent"] for e in timeline]
    has_run_end = any(e.get("event") == "run_end" for e in events)
    # run_end.result 필드 체크 (S52) + 기존 문자열 매칭 폴백
    run_end_result = ""
    for e in events:
        if e.get("event") == "run_end":
            run_end_result = e.get("result", "")
    has_done_marker = run_end_result in (
        "HARNESS_DONE", "IMPLEMENTATION_ESCALATE", "HARNESS_KILLED",
        "HARNESS_BUDGET_EXCEEDED", "KNOWN_ISSUE",
        # 의도적 일시정지 마커 (유저 게이트 대기)
        "PLAN_VALIDATION_PASS", "PLAN_DONE", "DESIGN_DONE",
        "UI_DESIGN_REQUIRED",
    ) or "ESCALATE" in run_end_result or any(
        "HARNESS_DONE" in str(e) or "ESCALATE" in str(e) or "KNOWN_ISSUE" in str(e)
        for e in events if e.get("event") in ("phase", "decision")
    )

    # ABNORMAL_END: run_end 없거나 incomplete agent 존재
    incomplete = [e for e in timeline if e.get("status") == "incomplete"]
    if not has_run_end:
        last_agent = agents_ran[-1] if agents_ran else "?"
        issues.append({
            "type": "ABNORMAL_END",
            "severity": "HIGH",
            "detail": f"run_end 이벤트 없음 — {last_agent} 단계에서 중단",
            "diagnosis": _diagnose_abort(last_agent, mode, events),
        })
    elif incomplete:
        for entry in incomplete:
            issues.append({
                "type": "ABNORMAL_END",
                "severity": "HIGH",
                "detail": f"{entry['agent']} 미완료 (elapsed ~{entry['elapsed']}s)",
                "diagnosis": _diagnose_abort(entry["agent"], mode, events),
            })

    # EARLY_EXIT: run_end는 있지만 HARNESS_DONE/ESCALATE 마커 없음
    if has_run_end and not has_done_marker and mode in ("bugfix", "impl"):
        issues.append({
            "type": "EARLY_EXIT",
            "severity": "HIGH",
            "detail": f"모드 {mode} 정상 종료했으나 HARNESS_DONE/ESCALATE 마커 없음",
            "diagnosis": "조기 exit 0 — 라우팅 분기에서 루프 미진입 가능성",
        })

    # MISSING_PHASE: 예상 단계 대비 누락
    expected = _get_expected_agents(mode, events)
    if expected and agents_ran:
        missing = [a for a in expected if a not in agents_ran]
        if missing:
            issues.append({
                "type": "MISSING_PHASE",
                "severity": "MEDIUM",
                "detail": f"예상 단계 {expected} 중 {missing} 누락",
                "diagnosis": f"실제 실행: {agents_ran}",
            })

    # ROUTING_MISMATCH: qa 출력 타입과 실제 다음 agent 불일치 (bugfix 모드)
    if mode == "bugfix" and len(agents_ran) >= 2 and agents_ran[0] == "qa":
        qa_type = _extract_qa_type(events)
        next_agent = agents_ran[1] if len(agents_ran) > 1 else None
        expected_next = {
            "FUNCTIONAL_BUG": "architect",   # v6: QA → impl 루프 (architect LIGHT_PLAN → depth별 라우팅)
            "SPEC_ISSUE": "architect",       # 동일
            "DESIGN_ISSUE": "designer",
        }
        if qa_type and next_agent:
            exp = expected_next.get(qa_type)
            if exp and next_agent != exp:
                issues.append({
                    "type": "ROUTING_MISMATCH",
                    "severity": "HIGH",
                    "detail": f"QA 판정 {qa_type} → 예상 다음 {exp}, 실제 {next_agent}",
                    "diagnosis": "harness/executor.sh grep 파싱 확인 필요",
                })

    return issues


def _get_expected_agents(mode, events):
    """모드+설정에서 예상 에이전트 순서를 반환한다."""
    if mode == "bugfix":
        # bugfix는 qa 라우팅에 따라 다름 — qa는 무조건 첫 번째
        return ["qa"]  # 최소한 qa는 있어야 함
    elif mode == "impl":
        depth = None
        for e in events:
            if e.get("event") == "config":
                depth = e.get("depth")
                break
        seq = EXPECTED_SEQUENCE.get("impl", {})
        if depth:
            return seq.get(depth, seq.get("std", []))
        else:
            return seq.get("plan_only", [])
    elif mode == "design":
        return EXPECTED_SEQUENCE.get("design", [])
    elif mode == "plan":
        return EXPECTED_SEQUENCE.get("plan", [])
    return []


def _extract_qa_type(events):
    """stream_event에서 QA 출력의 타입 분류를 추출한다."""
    # agent_end 직후의 qa 출력, 또는 stream에서 QA_REPORT 패턴 탐색
    qa_text = ""
    in_qa = False
    for e in events:
        if e.get("event") == "agent_start" and e.get("agent") == "qa":
            in_qa = True
        elif e.get("event") == "agent_end" and e.get("agent") == "qa":
            in_qa = False
        elif in_qa and e.get("type") == "stream_event":
            se = e.get("event", {})
            if se.get("type") == "content_block_delta":
                delta = se.get("delta", {})
                if delta.get("type") == "text_delta":
                    qa_text += delta.get("text", "")

    for t in ("FUNCTIONAL_BUG", "SPEC_ISSUE", "DESIGN_ISSUE"):
        if t in qa_text:
            return t
    return None


def _diagnose_abort(agent, mode, events):
    """중단된 에이전트와 모드를 기반으로 가능한 원인을 추론한다."""
    hints = []
    if agent == "qa":
        hints.append("QA 분석 중 중단 — 타임아웃 또는 mcp__github__create_issue 실패 가능")
        hints.append("확인: agents/qa.md 이슈 등록 규칙, mcp 도구 권한")
    elif agent == "architect":
        hints.append("architect 중단 — impl 파일 생성 실패 또는 타임아웃")
        hints.append("확인: agents/architect.md Mode F/B 프롬프트")
    elif agent == "engineer":
        hints.append("engineer 중단 — 코드 수정 중 타임아웃 또는 agent-boundary 차단")
        hints.append("확인: /tmp/{prefix}_engineer_active 플래그, agent-boundary.py 로그")
    elif agent == "validator":
        hints.append("validator 중단 — 검증 중 타임아웃")
    elif agent == "designer":
        hints.append("designer 중단 — variant 생성 중 타임아웃")
    else:
        hints.append(f"{agent} 중단 — agents/{agent}.md 제약 사항 확인")

    if mode == "bugfix":
        hints.append("루프 D 흐름: qa → (FUNCTIONAL_BUG: architect Mode F → engineer) / (SPEC_ISSUE: architect Mode B → validator → 루프 C)")

    return " | ".join(hints)


# ── 호출 흐름도 ──────────────────────────────────────────────────────

def generate_flow_diagram(run_info, timeline, events):
    """타임라인에서 ASCII 트리 형태의 호출 흐름도를 생성한다."""
    mode = run_info.get("mode", "?")
    lines = []
    lines.append(f"harness-executor {mode}")

    agents_ran = [e["agent"] for e in timeline]

    # stream_event에서 Agent tool_use 감지 → 서브에이전트 매핑
    sub_agents = defaultdict(list)  # parent_agent -> [(name, elapsed_approx)]
    current_parent = None
    for e in events:
        if e.get("event") == "agent_start":
            current_parent = e.get("agent")
        elif e.get("event") == "agent_end":
            current_parent = None
        elif current_parent and e.get("type") == "stream_event":
            se = e.get("event", {})
            if se.get("type") == "content_block_start":
                cb = se.get("content_block", {})
                if cb.get("type") == "tool_use" and cb.get("name") == "Agent":
                    sub_agents[current_parent].append(cb.get("id", "?"))

    # QA routing 추출
    qa_type = _extract_qa_type(events)

    # 예상 시퀀스
    expected = []
    if mode == "bugfix":
        seq_map = EXPECTED_SEQUENCE.get("bugfix", {})
        if qa_type == "FUNCTIONAL_BUG":
            expected = seq_map.get("functional_bug", [])
        elif qa_type == "DESIGN_ISSUE":
            expected = seq_map.get("design", [])
        else:
            expected = seq_map.get("architect", [])
    elif mode in EXPECTED_SEQUENCE:
        seq = EXPECTED_SEQUENCE[mode]
        if isinstance(seq, list):
            expected = seq
        elif isinstance(seq, dict):
            # depth 기반
            for e in events:
                if e.get("event") == "config":
                    depth = e.get("depth", "std")
                    expected = seq.get(depth, seq.get("std", []))
                    break

    for i, entry in enumerate(timeline):
        agent = entry["agent"]
        is_last = (i == len(timeline) - 1)
        prefix = "└─" if is_last else "├─"
        exit_str = f"exit={entry['exit']}" if entry.get("status") != "incomplete" else "INCOMPLETE"
        cost_str = f"${entry.get('cost_usd', 0):.2f}"
        line = f"{prefix} {agent} ({entry['elapsed']}s, {cost_str}, {exit_str})"
        lines.append(line)

        # QA routing 표시
        if agent == "qa" and qa_type:
            routing = "functional_bug" if qa_type == "FUNCTIONAL_BUG" else \
                      "design" if qa_type == "DESIGN_ISSUE" else "architect_full"
            sub_prefix = "│  └─" if not is_last else "   └─"
            lines.append(f"{sub_prefix} routing: {routing} ({qa_type})")

        # 서브에이전트 표시
        if agent in sub_agents:
            for sa_id in sub_agents[agent]:
                sub_prefix = "│  └─" if not is_last else "   └─"
                lines.append(f"{sub_prefix} Agent→sub-agent ({sa_id})")

    # 미진입 에이전트 표시
    missing = [a for a in expected if a not in agents_ran]
    for m in missing:
        lines.append(f"❌ {m} 미진입")

    return "\n".join(lines)


# ── 리포트 생성 ──────────────────────────────────────────────────────

def fmt_time(ts):
    if ts <= 0:
        return "?"
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def generate_report(filepath, run_info, config, timeline, agent_stats,
                    stream_tools, stream_files, waste, decisions, phases, contexts,
                    flow_issues=None, events=None, session_signals=None):
    lines = []
    basename = os.path.basename(filepath)

    # 요약
    total_cost = sum(e.get("cost_usd", 0) for e in timeline)
    lines.append(f"# Harness Review: {run_info['prefix']}/{basename}")
    lines.append("")
    run_end_result = run_info.get("run_end_result", "")
    lines.append("## 요약")
    lines.append("| 항목 | 값 |")
    lines.append("|------|-----|")
    lines.append(f"| 모드 | {run_info['mode']} |")
    lines.append(f"| depth | {config.get('depth', '(미적용)') if config else '(미적용)'} |")
    lines.append(f"| 소요 | {run_info['elapsed']}s |")
    lines.append(f"| 에이전트 | {len(timeline)}개 |")
    lines.append(f"| 비용 | ${total_cost:.2f} |")
    lines.append(f"| 결과 | {run_end_result or '?'} |")
    if config:
        lines.append(f"| impl | {config.get('impl_file', '?')} |")
    lines.append("")

    # 호출 흐름도
    lines.append("## 호출 흐름도")
    lines.append("```")
    lines.append(generate_flow_diagram(run_info, timeline, events or []))
    lines.append("```")
    lines.append("")

    # 타임라인
    lines.append("## 타임라인")
    lines.append("| 시간 | 에이전트 | 소요(s) | 비용($) | exit | in_tok | out_tok | prompt(KB) | 도구 |")
    lines.append("|------|---------|---------|---------|------|--------|---------|------------|------|")
    for entry in timeline:
        agent = entry["agent"]
        tools_str = ""
        if agent in agent_stats and agent_stats[agent]["tools"]:
            tools_str = " ".join(f"{k}:{v}" for k, v in agent_stats[agent]["tools"].items())
        elif stream_tools:
            tools_str = " ".join(f"{k}:{v}" for k, v in stream_tools.items())
        # 토큰 정보 (agent_stats에서 추출)
        in_tok_str = ""
        out_tok_str = ""
        if agent in agent_stats:
            in_tok_str = str(agent_stats[agent].get("in_tok", ""))
            out_tok_str = str(agent_stats[agent].get("out_tok", ""))
        pc_kb = f"{entry.get('prompt_chars', 0) / 1024:.1f}"
        exit_str = "KILLED" if entry.get("status") == "incomplete" else str(entry["exit"])
        elapsed_str = f"~{entry['elapsed']}" if entry.get("status") == "incomplete" else str(entry["elapsed"])
        lines.append(
            f"| {fmt_time(entry.get('t_start', 0))} | {agent} "
            f"| {elapsed_str} | {entry.get('cost_usd', 0):.2f} "
            f"| {exit_str} | {in_tok_str} | {out_tok_str} | {pc_kb} | {tools_str} |"
        )
    lines.append("")

    # 에이전트별 상세
    lines.append("## 에이전트별 상세")
    for entry in timeline:
        agent = entry["agent"]
        lines.append(f"### {agent} ({entry['elapsed']}s, ${entry.get('cost_usd', 0):.2f})")

        files = []
        if agent in agent_stats:
            files = agent_stats[agent].get("files_read", [])
        elif stream_files:
            files = stream_files

        if files:
            lines.append("Read/Glob 대상:")
            for f in files:
                flag = ""
                if any(p in f for p in INFRA_PATTERNS) and not any(e in f for e in INFRA_EXCLUSIONS):
                    flag = " **INFRA**"
                lines.append(f"- `{f}`{flag}")
        lines.append("")

    # 분기 결정
    if decisions:
        lines.append("## 분기 결정")
        for d in decisions:
            lines.append(
                f"- attempt {d.get('attempt', '?')}: "
                f"{d.get('key', '?')}={d.get('value', '?')} ({d.get('reason', '')})"
            )
        lines.append("")

    # 컨텍스트 크기
    if contexts:
        lines.append("## 컨텍스트 크기")
        for c in contexts:
            lines.append(f"- attempt {c.get('attempt', '?')}: {c.get('chars', 0):,} chars")
        lines.append("")

    # 낭비 패턴
    if waste:
        lines.append("## WASTE 패턴")
        lines.append("| # | 심각도 | 패턴 | 에이전트 | 상세 | 수정 |")
        lines.append("|---|--------|------|---------|------|------|")
        for i, w in enumerate(waste, 1):
            lines.append(
                f"| {i} | {w['severity']} | {w['type']} | {w.get('agent', '')} "
                f"| {w['detail']} | {w['fix']} |"
            )
            if "files" in w:
                for f in w["files"]:
                    lines.append(f"|   |        |      |         | `{f}` |      |")
        lines.append("")

        # 수정 제안 테이블
        lines.append("## 수정 제안")
        lines.append("| 우선순위 | 파일 | 변경 내용 |")
        lines.append("|---------|------|-----------|")
        seen = set()
        for w in sorted(waste, key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(x["severity"], 3)):
            key = w["fix"]
            if key not in seen:
                seen.add(key)
                fix_file = f"`~/.claude/agents/{w['agent']}.md`" if w.get("agent") else ""
                lines.append(f"| {w['severity']} | {fix_file} | {w['fix']} |")
        lines.append("")
    else:
        lines.append("## WASTE 패턴 없음")
        lines.append("")

    # 흐름 진단
    if flow_issues:
        lines.append("## 흐름 진단")
        lines.append("| # | 심각도 | 유형 | 상세 | 진단 |")
        lines.append("|---|--------|------|------|------|")
        for i, fi in enumerate(flow_issues, 1):
            lines.append(
                f"| {i} | {fi['severity']} | {fi['type']} "
                f"| {fi['detail']} | {fi['diagnosis']} |"
            )
        lines.append("")
    else:
        lines.append("## 흐름 정상")
        lines.append("")

    # 세션 로그 모순 (메인 Claude 행동 분석)
    if session_signals:
        contradictions = [s for s in session_signals if s["type"] == "GATE_CONTRADICTION"]
        bypasses = [s for s in session_signals if s["type"] == "FLAG_BYPASS"]
        blocks = [s for s in session_signals if s["type"] == "HOOK_BLOCK"]

        lines.append("## 세션 로그 모순 (메인 Claude)")
        lines.append(f"플래그 수동 우회: {len(bypasses)}건 | 훅 차단: {len(blocks)}건 | 게이트 모순: {len(contradictions)}건")
        lines.append("")

        if contradictions:
            lines.append("### 게이트 모순 (HOOK_BLOCK → FLAG_BYPASS)")
            for c in contradictions:
                lines.append(f"- {c['detail']}")
            lines.append("")

        if bypasses:
            lines.append("### 플래그 수동 우회")
            for b in bypasses:
                flags = ", ".join(b.get("flags", []))
                lines.append(f"- `{flags}` — {b['detail'][:100]}")
            lines.append("")
    else:
        lines.append("## 세션 로그 모순 없음")
        lines.append("")

    return "\n".join(lines)


# ── 메인 ─────────────────────────────────────────────────────────────

def analyze_file(filepath, session_jsonl=None):
    events = parse_jsonl(filepath)
    if not events:
        return f"[ERROR] 빈 로그: {filepath}"

    run_info = extract_run_info(events)
    config = extract_config(events)
    timeline = extract_timeline(events)
    agent_stats_data = extract_agent_stats(events)
    decisions = extract_decisions(events)
    phases_data = extract_phases(events)
    contexts = extract_contexts(events)

    # old format 호환: agent_stats가 없으면 stream에서 추출
    if not agent_stats_data:
        stream_tools, stream_files = extract_tool_usage_from_stream(events)
    else:
        stream_tools, stream_files = {}, []

    waste = detect_waste(timeline, agent_stats_data, stream_tools, stream_files, decisions, events)
    waste = detect_waste_with_context(waste, run_info, config, events)
    flow_issues = detect_flow_issues(run_info, timeline, events)

    # 세션 로그 모순 스캔
    session_signals = []
    if session_jsonl:
        run_start_ts = run_info.get("start_ts", 0)
        run_end_ts = run_info.get("end_ts", 0)
        session_signals = scan_session_log(session_jsonl, run_start_ts, run_end_ts)

    return generate_report(
        filepath, run_info, config, timeline, agent_stats_data,
        stream_tools, stream_files, waste, decisions, phases_data, contexts,
        flow_issues=flow_issues, events=events, session_signals=session_signals,
    )


def _build_menu_items(candidates):
    """candidates 파일 목록 → (label, filepath) 튜플 리스트."""
    items = []
    for fp in candidates:
        info = _quick_run_info(fp)
        ts     = datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%m-%d %H:%M")
        result = info.get("result", "?")
        mode   = info.get("mode", "?")
        pname  = info.get("prefix", os.path.basename(os.path.dirname(fp)))
        label  = f"[{ts}] {pname}  mode={mode}  result={result}"
        items.append((label, fp))
    return items


def _select_with_curses(items):
    """curses 화살표 선택 UI. 선택한 filepath 반환, 취소 시 None."""
    import curses

    def _menu(stdscr, items):
        curses.curs_set(0)
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)
        selected = 0
        while True:
            stdscr.clear()
            stdscr.addstr(0, 0, "최근 하네스 실행  (↑↓ 이동 / Enter 분석 / q 취소)\n", curses.A_BOLD)
            for i, (label, _) in enumerate(items):
                if i == selected:
                    stdscr.addstr(i + 2, 0, f"  ▶ {label}", curses.color_pair(1))
                else:
                    stdscr.addstr(i + 2, 0, f"    {label}")
            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP and selected > 0:
                selected -= 1
            elif key == curses.KEY_DOWN and selected < len(items) - 1:
                selected += 1
            elif key in (curses.KEY_ENTER, 10, 13):
                return items[selected][1]
            elif key in (ord('q'), ord('Q'), 27):  # q / Q / ESC
                return None

    return curses.wrapper(_menu, items)


def _select_interactive(candidates):
    """TTY면 curses, 아니면 번호 입력 폴백. 선택한 filepath 반환."""
    items = _build_menu_items(candidates)

    if sys.stdin.isatty() and sys.stdout.isatty():
        try:
            return _select_with_curses(items)
        except Exception:
            pass  # curses 실패 → 폴백

    # 폴백: 번호 입력
    print("최근 하네스 실행:\n")
    for i, (label, fp) in enumerate(items, 1):
        print(f"  {i}. {label}")
        print(f"     {fp}")
    print()
    try:
        val = input("번호 선택 (1-5, Enter=취소): ").strip()
        if not val:
            return None
        idx = int(val) - 1
        return items[idx][1] if 0 <= idx < len(items) else None
    except (ValueError, EOFError):
        return None


def _quick_run_info(filepath):
    """run_start / run_end 이벤트만 읽어 요약 dict 반환 (풀 분석 없음)."""
    info = {}
    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                ev = e.get("event", "")
                if ev == "run_start":
                    info["prefix"] = e.get("prefix", "?")
                    info["mode"]   = e.get("mode", "?")
                elif ev == "run_end":
                    info["result"] = e.get("result", "?")
                    break  # run_end 찾으면 충분
    except Exception:
        pass
    return info


def main():
    parser = argparse.ArgumentParser(description="하네스 JSONL 로그 리뷰")
    parser.add_argument("file", nargs="?", help="JSONL 파일 경로")
    parser.add_argument("--prefix", "-p", help="프로젝트 prefix (최신 로그 자동 탐색)")
    parser.add_argument("--last", "-n", type=int, default=1, help="최근 N개 로그 분석")
    parser.add_argument("--list", action="store_true", help="최신 5개 목록만 출력하고 종료")
    parser.add_argument("--session-jsonl", help="메인 Claude 세션 JSONL (게이트 모순 감지)")
    args = parser.parse_args()

    # 트리거 파일에서 session_jsonl 자동 읽기
    session_jsonl = args.session_jsonl
    if not session_jsonl and os.path.exists("/tmp/harness_review_trigger.json"):
        try:
            trigger = json.load(open("/tmp/harness_review_trigger.json"))
            session_jsonl = trigger.get("session_jsonl")
        except Exception:
            pass

    all_recent = sorted(
        glob.glob(os.path.join(LOG_DIR, "*", "run_*.jsonl")),
        key=os.path.getmtime,
        reverse=True,
    )

    # --list 또는 인자 없음 → 목록 출력 후 종료 (Claude가 번호 받아서 재호출)
    if args.list or (not args.file and not args.prefix):
        if not all_recent:
            print(f"[ERROR] 로그 없음: {LOG_DIR}/")
            sys.exit(1)
        items = _build_menu_items(all_recent[:5])
        print("최근 하네스 실행:\n")
        for i, (label, fp) in enumerate(items, 1):
            print(f"  {i}. {label}")
            print(f"     {fp}")
        return

    if args.file:
        files = [args.file]
    elif args.prefix:
        if args.last > 1:
            # --last N 명시: 최근 N개 분석 (리뷰 여부 무관)
            files = find_latest_logs(args.prefix, args.last)
        else:
            # --prefix만: 미리뷰 로그 전부 → 없으면 최신 1개
            files = find_unreviewed_logs(args.prefix)
            if not files:
                files = find_latest_logs(args.prefix, 1)
        if not files:
            print(f"[ERROR] {args.prefix} prefix 로그 없음: {LOG_DIR}/{args.prefix}/")
            sys.exit(1)

    for filepath in files:
        report = analyze_file(filepath, session_jsonl=session_jsonl)
        print(report)
        _mark_reviewed(filepath)
        if len(files) > 1:
            print("\n" + "=" * 60 + "\n")

    # classify-miss 요약 (라우터 로그가 있을 때만)
    print(_classify_miss_summary())


def _classify_miss_summary():
    """fast_classify 커버리지 1줄 요약. 라우터 로그 없으면 빈 문자열."""
    import re as _re
    log_path = "/tmp/harness-router.log"
    if not os.path.exists(log_path):
        return ""
    try:
        lines = open(log_path).readlines()
    except Exception:
        return ""

    fast = sum(1 for l in lines if "FAST_CLASSIFY result=" in l)
    haiku = sum(1 for l in lines if "INTENT result=" in l)
    fail = sum(1 for l in lines if "classify_fail" in l)
    total = fast + haiku + fail
    if total == 0:
        return ""

    pct = fast * 100 // total
    # Haiku 폴백된 짧은 프롬프트 수 (승격 후보)
    candidates = []
    for l in lines:
        if "INTENT result=" in l:
            m = _re.search(r"prompt='([^']{1,30})'", l)
            if m:
                candidates.append(m.group(1))

    out = f"\n--- fast_classify 커버리지: {pct}% ({fast}/{total})"
    if haiku > 0:
        out += f" | Haiku 폴백 {haiku}건"
    if fail > 0:
        out += f" | 분류실패 {fail}건"
    if candidates:
        out += f" | 승격 후보 {len(candidates)}건"
    if pct < 70:
        out += " ⚠️ 커버리지 낮음 — python3 ~/.claude/scripts/classify-miss-report.py 실행 권장"
    return out


if __name__ == "__main__":
    main()
