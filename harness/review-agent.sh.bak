#!/bin/bash
# ~/.claude/harness/review-agent.sh
# 하네스 실행 완료 후 Haiku가 로그를 분석해 개선점을 찾는다 (Phase D Step A).
#
# 호출: bash ~/.claude/harness/review-agent.sh <jsonl_log> [prefix]
# 출력: ${STATE_DIR}/${PREFIX}_review-result.json
#
# 완료 기준:
# - 실행 시 ${STATE_DIR}/${PREFIX}_review-result.json 생성
# - review-result.json이 항상 유효한 JSON (parse_error 케이스 포함)
# - promote_suggestions 필드로만 제안 (자동 수정 금지)

set -euo pipefail

JSONL_LOG="${1:-}"
PREFIX="${2:-}"

if [[ -z "$JSONL_LOG" || ! -f "$JSONL_LOG" ]]; then
  echo "[review-agent] JSONL 로그 없음 — 스킵" >&2
  exit 0
fi

# PREFIX 추론 (지정 안 됐을 때: JSONL 경로의 디렉토리명에서 추출)
if [[ -z "$PREFIX" ]]; then
  local_dir=$(dirname "$JSONL_LOG")
  PREFIX=$(basename "$local_dir" 2>/dev/null | sed 's/[^a-z0-9]//g' | cut -c1-8 || echo "proj")
  [[ -z "$PREFIX" ]] && PREFIX="proj"
fi

RESULT_FILE="${STATE_DIR}/${PREFIX}_review-result.json"
HIST_DIR="${STATE_DIR}/${PREFIX}_history"

# ── harness-review.py 실행: WASTE 패턴 + 타임라인 구조화 분석 ──────────
WASTE_ANALYSIS=""
REVIEW_SCRIPT="${HOME}/.claude/scripts/harness-review.py"
REVIEW_TXT="${JSONL_LOG%.jsonl}_review.txt"
if [[ -f "$REVIEW_SCRIPT" ]]; then
  python3 "$REVIEW_SCRIPT" "$JSONL_LOG" > "$REVIEW_TXT" 2>/dev/null || true
  WASTE_ANALYSIS=$(head -c 8000 "$REVIEW_TXT" 2>/dev/null || true)
fi

# 로그 내용을 직접 포함 (--print 모드는 tool 없음 — 경로만 넘기면 읽지 못함)
LOG_CONTENT=$(tail -c 6000 "$JSONL_LOG" 2>/dev/null || true)

# meta.json 요약 (히스토리 있을 때)
META_SUMMARY=""
if [[ -d "$HIST_DIR" ]]; then
  while IFS= read -r mf; do
    [[ -z "$mf" ]] && continue
    META_SUMMARY="${META_SUMMARY}
=== $(dirname "$mf" | xargs basename) ===
$(head -c 500 "$mf" 2>/dev/null || true)"
  done < <(find "$HIST_DIR" -name "meta.json" 2>/dev/null | sort | tail -10)
fi

# harness-memory.md 요약
MEMORY_CONTENT=""
for mem_f in "${HOME}/.claude/harness-memory.md" ".claude/harness-memory.md"; do
  if [[ -f "$mem_f" ]]; then
    MEMORY_CONTENT=$(tail -30 "$mem_f" 2>/dev/null || true)
    break
  fi
done

REVIEW_PROMPT="당신은 하네스 로그 리뷰어다.

## 분석할 데이터 (아래에 직접 포함됨)

### [1] harness-review.py 구조화 분석 (WASTE 패턴 + 타임라인) — 최우선 참고
${WASTE_ANALYSIS:-harness-review.py 미실행 또는 출력 없음}

### [2] 현재 실행 JSONL 로그 (마지막 6KB)
${LOG_CONTENT}

### [3] attempt meta.json 요약 (최근 10개)
${META_SUMMARY:-없음}

### [4] harness-memory.md (마지막 30줄)
${MEMORY_CONTENT:-없음}

## 분석 항목 (우선순위순)

### HIGH (즉시 수정 가능)
- 에이전트 크래시/타임아웃이 있는가? (exit code != 0 또는 timeout 이벤트)
- 마커 파싱 실패가 있는가? (UNKNOWN이 기대 마커 위치에 반환됨)
- 같은 실패가 3회 이상 반복되는가? (history/*/attempt-*/meta.json 확인)
- agent-boundary 블록이 반복되는가?

### MEDIUM (제안)
- 1회 만에 성공할 수 있었는데 불필요한 반복이 있었는가?
- 단일 에이전트 호출 비용이 \$1.5를 초과하는가?
- 주입된 컨텍스트 중 에이전트가 읽지 않은 파일이 있는가?
- SPEC_GAP가 빈번하게 발생하는가?

### LOW (기록)
- 평균 시도 횟수 추세는?
- 루프별 평균 비용 추세는?

## 출력 형식 (중요)
반드시 유효한 JSON만 출력하라. 마크다운 코드블록(\`\`\`json) 금지. JSON 외 텍스트 금지.

{
  \"issues\": [
    {
      \"type\": \"<이슈 유형: repeated_failure|agent_crash|marker_parse_fail|boundary_block|other>\",
      \"confidence\": \"HIGH|MEDIUM|LOW\",
      \"evidence\": \"<구체적 근거>\",
      \"target_file\": \"<수정 대상 파일 경로>\",
      \"suggested_change\": \"<구체적 수정 제안>\",
      \"risk\": \"LOW|MEDIUM|HIGH\"
    }
  ],
  \"stats\": {
    \"total_attempts\": 0,
    \"success\": false,
    \"total_cost\": 0.0,
    \"duration_minutes\": 0
  },
  \"promote_suggestions\": [],
  \"summary\": \"<한 줄 요약>\"
}"

# Haiku 호출 — 임시 파일에 저장 후 JSON 검증
TMP_OUT=$(mktemp /tmp/review_agent_XXXXXX.txt)
trap 'rm -f "$TMP_OUT"' EXIT

claude --model haiku --print "$REVIEW_PROMPT" > "$TMP_OUT" 2>/dev/null || true

# JSON 검증 — 유효하지 않으면 parse_error 저장
python3 - "$TMP_OUT" "$RESULT_FILE" << 'PYEOF'
import json, sys, os

tmp_file = sys.argv[1]
result_file = sys.argv[2]

try:
    raw = open(tmp_file).read().strip()
    # 마크다운 코드블록 제거 시도
    if raw.startswith("```"):
        lines = raw.split("\n")
        end_idx = len(lines)
        for i, l in enumerate(lines):
            if i > 0 and l.strip() == "```":
                end_idx = i
                break
        raw = "\n".join(lines[1:end_idx])
    parsed = json.loads(raw)
    # 필수 키 보장
    if "issues" not in parsed:
        parsed["issues"] = []
    if "stats" not in parsed:
        parsed["stats"] = {}
    if "promote_suggestions" not in parsed:
        parsed["promote_suggestions"] = []
    if "summary" not in parsed:
        parsed["summary"] = ""
    with open(result_file, "w") as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)
except Exception as e:
    try:
        raw_preview = open(tmp_file).read()[:500]
    except Exception:
        raw_preview = ""
    error_result = {
        "parse_error": str(e),
        "raw_output_preview": raw_preview,
        "issues": [],
        "stats": {},
        "promote_suggestions": [],
        "summary": "parse_error — Haiku JSON 파싱 실패"
    }
    with open(result_file, "w") as f:
        json.dump(error_result, f, ensure_ascii=False, indent=2)
PYEOF

echo "[review-agent] 완료: $RESULT_FILE" >&2
