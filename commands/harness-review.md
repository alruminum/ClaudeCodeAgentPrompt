---
description: 하네스 JSONL 로그를 파싱해 에이전트 타임라인·도구 사용·낭비 패턴을 진단한다. HARNESS_DONE/ESCALATE 후 자동 실행 또는 수동 호출.
argument-hint: "[prefix] [--last N]"
---

# /harness-review

하네스 루프 실행 로그를 분석해 낭비 패턴을 진단하고 수정 제안을 출력한다.

## 인자

- `$ARGUMENTS`가 비어있으면: 최신 5개 목록 출력 → Claude가 유저에게 번호 선택 요청 → 선택된 항목 분석
- `$ARGUMENTS`가 prefix만: 미리뷰 로그 전부 분석 → 없으면 최신 1개 (예: `mb`)
- `$ARGUMENTS`에 `--last N`: 최근 N개 로그 분석 (예: `mb --last 3`)

## 실행

```bash
ARGS="$ARGUMENTS"
if [ -z "$ARGS" ]; then
  python3 ~/.claude/scripts/harness-review.py --list
elif echo "$ARGS" | grep -q "\-\-last"; then
  python3 ~/.claude/scripts/harness-review.py --prefix $ARGS
else
  python3 ~/.claude/scripts/harness-review.py --prefix $ARGS
fi
```

## 인자 없을 때 흐름 (Claude 행동 규칙)

1. 위 bash 블록을 실행해 목록을 출력한다.
2. 출력된 목록을 유저에게 보여주고 **"몇 번을 분석할까요?"** 라고 묻는다.
3. 유저가 번호로 응답하면 해당 줄의 파일 경로를 추출해 아래 명령을 실행한다:
   ```bash
   python3 ~/.claude/scripts/harness-review.py <파일경로>
   ```
4. 분석 리포트를 출력 규칙에 따라 그대로 출력한다.

## 출력 규칙 (절대 준수 — 위반 시 유저 컴플레인 발생)

**Bash 출력은 Claude Code UI에서 자동 접힘(collapsed) 처리되어 유저에게 안 보일 수 있다.**
따라서 Bash stdout 내용을 Claude 텍스트 응답으로 **한 글자도 바꾸지 않고 그대로 복사**해서 출력한다.

### Claude의 응답 규칙

1. Bash로 스크립트를 실행한다
2. Bash stdout 전체를 Claude 텍스트 응답에 **character-for-character 복사**한다
3. 리포트 뒤에 추가 코멘트는 허용 (별도 줄에서)

### 절대 금지 (반복 위반 — 6회 컴플레인)

- ❌ 마크다운 테이블(`| 항목 | 값 |`)을 ASCII 박스(`┌──┬──┐`)로 변환
- ❌ 섹션 생략, 축약, 요약, 재배치
- ❌ "핵심은~", "정리하면~" 같은 자체 해석을 리포트 사이에 삽입
- ❌ 테이블 컬럼 순서나 헤더 변경
- ❌ 줄바꿈 추가/제거로 레이아웃 변경

### 핵심 원칙

**스크립트가 `print()`한 텍스트 = Claude가 출력할 텍스트. 1:1 동일해야 한다.**
마크다운 렌더링은 Claude Code UI가 알아서 한다. Claude는 원문만 전달하면 된다.

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

orchestration/policies.md 정책 17에 따라, 아래 마커 수신 후 메인 Claude가 자동 실행:
- `HARNESS_DONE`
- `IMPLEMENTATION_ESCALATE`
- `HARNESS_CRASH`
- `KNOWN_ISSUE`
- `PLAN_VALIDATION_PASS`
- `PLAN_VALIDATION_ESCALATE`
