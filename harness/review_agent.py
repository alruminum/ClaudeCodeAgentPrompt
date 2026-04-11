"""
review_agent.py — review-agent.sh 대체.
하네스 실행 완료 후 Haiku가 로그를 분석해 개선점을 찾는다.
Python 3.9+ stdlib only.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def run_review(run_log_path: str, prefix: str = "") -> None:
    """review-agent.sh의 전체 흐름 대체."""
    log_path = Path(run_log_path)
    if not log_path.exists():
        print("[review-agent] JSONL 로그 없음 — 스킵", file=sys.stderr)
        return

    # PREFIX 추론
    if not prefix:
        local_dir = log_path.parent.name
        prefix = re.sub(r"[^a-z0-9]", "", local_dir.lower())[:8] or "proj"

    # state_dir 탐색
    cwd = Path.cwd().resolve()
    state_dir = cwd / ".claude" / "harness-state"
    if not state_dir.is_dir():
        state_dir = Path("/tmp")

    result_file = state_dir / f"{prefix}_review-result.json"
    hist_dir = state_dir / f"{prefix}_history"

    # ── harness-review.py 실행 ──
    waste_analysis = ""
    review_script = Path.home() / ".claude" / "scripts" / "harness-review.py"
    review_txt = log_path.with_suffix(".txt").parent / (log_path.stem + "_review.txt")
    if review_script.exists():
        try:
            r = subprocess.run(
                ["python3", str(review_script), str(log_path)],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0:
                review_txt.write_text(r.stdout, encoding="utf-8")
                waste_analysis = r.stdout[:8000]
        except Exception:
            pass

    # 로그 내용 (마지막 6KB)
    try:
        raw = log_path.read_bytes()
        log_content = raw[-6000:].decode("utf-8", errors="replace")
    except OSError:
        log_content = ""

    # meta.json 요약
    meta_summary = ""
    if hist_dir.is_dir():
        meta_files = sorted(hist_dir.rglob("meta.json"))[-10:]
        for mf in meta_files:
            try:
                parent_name = mf.parent.name
                content = mf.read_bytes()[:500].decode("utf-8", errors="replace")
                meta_summary += f"\n=== {parent_name} ===\n{content}"
            except OSError:
                pass

    # harness-memory.md 요약
    memory_content = ""
    for mem_f in (Path.home() / ".claude" / "harness-memory.md", Path(".claude/harness-memory.md")):
        if mem_f.exists():
            try:
                lines = mem_f.read_text(encoding="utf-8").splitlines()
                memory_content = "\n".join(lines[-30:])
            except OSError:
                pass
            break

    review_prompt = f"""당신은 하네스 로그 리뷰어다.

## 분석할 데이터 (아래에 직접 포함됨)

### [1] harness-review.py 구조화 분석 (WASTE 패턴 + 타임라인) — 최우선 참고
{waste_analysis or 'harness-review.py 미실행 또는 출력 없음'}

### [2] 현재 실행 JSONL 로그 (마지막 6KB)
{log_content}

### [3] attempt meta.json 요약 (최근 10개)
{meta_summary or '없음'}

### [4] harness-memory.md (마지막 30줄)
{memory_content or '없음'}

## 출력 형식 (중요)
반드시 유효한 JSON만 출력하라. 마크다운 코드블록 금지. JSON 외 텍스트 금지.

{{"issues": [], "stats": {{}}, "promote_suggestions": [], "summary": ""}}"""

    # Haiku 호출
    try:
        r = subprocess.run(
            ["claude", "--model", "haiku", "--print", review_prompt],
            capture_output=True, text=True, timeout=120,
        )
        raw_output = r.stdout.strip()
    except Exception:
        raw_output = ""

    # JSON 검증
    try:
        # 마크다운 코드블록 제거
        if raw_output.startswith("```"):
            lines = raw_output.split("\n")
            end_idx = len(lines)
            for i, l in enumerate(lines):
                if i > 0 and l.strip() == "```":
                    end_idx = i
                    break
            raw_output = "\n".join(lines[1:end_idx])
        parsed = json.loads(raw_output)
        for key in ("issues", "stats", "promote_suggestions", "summary"):
            if key not in parsed:
                parsed[key] = [] if key in ("issues", "promote_suggestions") else ("" if key == "summary" else {})
    except Exception as e:
        parsed = {
            "parse_error": str(e),
            "raw_output_preview": raw_output[:500],
            "issues": [],
            "stats": {},
            "promote_suggestions": [],
            "summary": "parse_error — Haiku JSON 파싱 실패",
        }

    result_file.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[review-agent] 완료: {result_file}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        run_review(sys.argv[1], sys.argv[2] if len(sys.argv) >= 3 else "")
