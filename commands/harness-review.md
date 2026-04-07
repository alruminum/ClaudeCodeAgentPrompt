---
description: 하네스 JSONL 로그를 파싱해 에이전트 타임라인·도구 사용·낭비 패턴을 진단한다. HARNESS_DONE/ESCALATE 후 자동 실행 또는 수동 호출.
argument-hint: "[prefix] [--last N]"
---

# /harness-review

하네스 루프 실행 로그를 분석해 낭비 패턴을 진단하고 수정 제안을 출력한다.

## 인자

- `$ARGUMENTS`가 비어있으면: 모든 prefix에서 최신 1개 로그 자동 탐색
- `$ARGUMENTS`가 prefix만: 해당 prefix 최신 로그 분석 (예: `mb`)
- `$ARGUMENTS`에 `--last N`: 최근 N개 로그 분석 (예: `mb --last 3`)

## 실행

```bash
# 인자 파싱
ARGS="$ARGUMENTS"
if [ -z "$ARGS" ]; then
  python3 ~/.claude/scripts/harness-review.py
elif echo "$ARGS" | grep -q "\-\-last"; then
  python3 ~/.claude/scripts/harness-review.py --prefix $ARGS
else
  python3 ~/.claude/scripts/harness-review.py --prefix $ARGS
fi
```

## 출력 해석

리포트가 출력되면 유저에게 아래 형태로 전달한다:

1. **요약** — 모드, 소요시간, 비용, 에이전트 수
2. **타임라인** — 에이전트별 소요시간/비용/도구 사용 테이블
3. **WASTE 패턴** — 발견된 낭비 패턴과 수정 제안
4. **수정 제안** — 우선순위별 수정 파일과 변경 내용

WASTE 패턴이 없으면 "정상 실행"으로 보고한다.

## WASTE 패턴 유형

| 패턴 | 설명 | 심각도 |
|------|------|--------|
| `WASTE_INFRA_READ` | 에이전트가 하네스 인프라 파일 탐색 | HIGH |
| `WASTE_SUB_AGENT` | 에이전트가 서브에이전트 과다 스폰 | HIGH |
| `WASTE_HARNESS_EXEC` | ReadOnly 에이전트가 Bash 호출 | HIGH |
| `WASTE_TIMEOUT` | 타임아웃 직전 + 결과 없음 | MEDIUM |
| `WASTE_NO_OUTPUT` | 정상 종료인데 출력 비어있음 | MEDIUM |
| `RETRY_SAME_FAIL` | 연속 동일 실패 반복 | MEDIUM |
| `CONTEXT_BLOAT` | 프롬프트 40KB 초과 | MEDIUM |
| `SLOW_PHASE` | 기대 소요시간 2배 초과 | LOW |

## 자동 실행 조건

orchestration-rules.md 정책 10에 따라, 아래 마커 수신 후 메인 Claude가 자동 실행:
- `HARNESS_DONE`
- `IMPLEMENTATION_ESCALATE`
- `KNOWN_ISSUE`
