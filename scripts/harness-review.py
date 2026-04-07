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
    "hooks/", "settings.json", "harness-utils", "harness-loop",
    "harness-executor",
]

EXPECTED_ELAPSED = {
    "engineer": 900,
    "test-engineer": 300,
    "validator": 300,
    "pr-reviewer": 180,
    "security-reviewer": 180,
    "qa": 300,
    "architect": 300,
    "designer": 300,
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


def find_latest_logs(prefix, count=1):
    d = os.path.join(LOG_DIR, prefix)
    if not os.path.isdir(d):
        return []
    files = sorted(glob.glob(os.path.join(d, "run_*.jsonl")), reverse=True)
    return files[:count]


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

def detect_waste(timeline, agent_stats, stream_tools, stream_files, decisions):
    patterns = []

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
        infra_hits = [f for f in files if any(p in f for p in INFRA_PATTERNS)]
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

    return patterns


# ── 리포트 생성 ──────────────────────────────────────────────────────

def fmt_time(ts):
    if ts <= 0:
        return "?"
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def generate_report(filepath, run_info, config, timeline, agent_stats,
                    stream_tools, stream_files, waste, decisions, phases, contexts):
    lines = []
    basename = os.path.basename(filepath)

    # 요약
    total_cost = sum(e.get("cost_usd", 0) for e in timeline)
    lines.append(f"# Harness Review: {run_info['prefix']}/{basename}")
    lines.append("")
    lines.append("## 요약")
    lines.append(f"- 모드: {run_info['mode']}")
    lines.append(f"- 전체 소요: {run_info['elapsed']}s")
    lines.append(f"- 에이전트 호출: {len(timeline)}개")
    lines.append(f"- 총 비용: ${total_cost:.2f}")
    if config:
        lines.append(f"- impl: {config.get('impl_file', '?')}")
        lines.append(f"- depth: {config.get('depth', '?')}")
        lines.append(f"- constraints: {config.get('constraints_chars', '?')} chars")
    lines.append("")

    # 타임라인
    lines.append("## 타임라인")
    lines.append("| 시간 | 에이전트 | 소요(s) | 비용($) | exit | prompt(KB) | 도구 |")
    lines.append("|------|---------|---------|---------|------|------------|------|")
    for entry in timeline:
        agent = entry["agent"]
        tools_str = ""
        if agent in agent_stats and agent_stats[agent]["tools"]:
            tools_str = " ".join(f"{k}:{v}" for k, v in agent_stats[agent]["tools"].items())
        elif stream_tools:
            tools_str = " ".join(f"{k}:{v}" for k, v in stream_tools.items())
        pc_kb = f"{entry.get('prompt_chars', 0) / 1024:.1f}"
        exit_str = "KILLED" if entry.get("status") == "incomplete" else str(entry["exit"])
        elapsed_str = f"~{entry['elapsed']}" if entry.get("status") == "incomplete" else str(entry["elapsed"])
        lines.append(
            f"| {fmt_time(entry.get('t_start', 0))} | {agent} "
            f"| {elapsed_str} | {entry.get('cost_usd', 0):.2f} "
            f"| {exit_str} | {pc_kb} | {tools_str} |"
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
                if any(p in f for p in INFRA_PATTERNS):
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
        for i, w in enumerate(waste, 1):
            sev = w["severity"]
            lines.append(f"{i}. **{w['type']}** [{sev}] — {w['detail']}")
            lines.append(f"   fix: {w['fix']}")
            if "files" in w:
                for f in w["files"]:
                    lines.append(f"   - `{f}`")
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

    return "\n".join(lines)


# ── 메인 ─────────────────────────────────────────────────────────────

def analyze_file(filepath):
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

    waste = detect_waste(timeline, agent_stats_data, stream_tools, stream_files, decisions)

    return generate_report(
        filepath, run_info, config, timeline, agent_stats_data,
        stream_tools, stream_files, waste, decisions, phases_data, contexts,
    )


def main():
    parser = argparse.ArgumentParser(description="하네스 JSONL 로그 리뷰")
    parser.add_argument("file", nargs="?", help="JSONL 파일 경로")
    parser.add_argument("--prefix", "-p", help="프로젝트 prefix (최신 로그 자동 탐색)")
    parser.add_argument("--last", "-n", type=int, default=1, help="최근 N개 로그 분석")
    args = parser.parse_args()

    if args.file:
        files = [args.file]
    elif args.prefix:
        files = find_latest_logs(args.prefix, args.last)
        if not files:
            print(f"[ERROR] {args.prefix} prefix 로그 없음: {LOG_DIR}/{args.prefix}/")
            sys.exit(1)
    else:
        # 모든 prefix에서 최신 1개
        all_files = sorted(glob.glob(os.path.join(LOG_DIR, "*", "run_*.jsonl")), reverse=True)
        if not all_files:
            print(f"[ERROR] 로그 없음: {LOG_DIR}/")
            sys.exit(1)
        files = all_files[:args.last]

    for filepath in files:
        report = analyze_file(filepath)
        print(report)
        if len(files) > 1:
            print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    main()
