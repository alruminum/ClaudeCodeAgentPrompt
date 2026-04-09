# ClaudeCodeAgentPrompt 개선 구현 플랜

작성일: 2026-04-09  
대상: 1인 개발자 / $200 Max 플랜 / 중소형 프로젝트  
실행 순서: Phase A → Phase B → Phase C(선택) → Phase D

---

## 변경 사항 요약 (기존 플랜 대비)

| 기존 Phase | 변경 | 사유 |
|------------|------|------|
| Phase 1 디자인 v2 | **삭제** | 레포에 이미 Pencil MCP v2 적용 완료 |
| Phase 2 Feedback Compression | → **Phase A** (최우선) | Meta-Harness 핵심. 에이전트 자율 탐색 개념 추가 |
| Phase 3 Environment Bootstrap | → **Phase C** (선택) | 기존 `build_smart_context()` 충분. 필요 시 보강 |
| Phase 4 히스토리 보존 | → **Phase B** (2순위) | Meta-Harness 본질. pruning 정책 추가 |
| Phase 5 라우팅 세분화 | **Phase B에 흡수** | 독립 Phase 불필요. 히스토리 기반 에이전트 자율 판단 |
| Phase 6 자동 개선 | → **Phase D** (Step B 제거, 분석 전략 구체화) | 1인 개발 안전성 우선 |

---

## Phase A — Feedback Compression 제거 + 에이전트 자율 탐색

에이전트 간 요약 전달을 원본 파일 직접 참조로 변경하되, 하네스가 "이 파일을 읽어라"고 지정하지 않고 에이전트가 스스로 필요한 정보를 탐색하게 한다.

Meta-Harness 핵심 원칙: proposer가 중앙값 82개 파일을 자율 탐색하여 성과를 냈다. 사전 정의된 검색 휴리스틱 없이 에이전트가 무엇을 읽을지 스스로 결정하게 하는 것이 핵심이다.

### A-1. `utils.sh` `_agent_call()` 수정

현재 상태: 에이전트 출력을 `$out_file`에 저장하지만, 다음 에이전트에 `fail_context` 등으로 요약/발췌 전달.

변경:

```bash
# 출력 파일 경로 표준화
out_file="$OUT_DIR/${loop}_${agent}_attempt${attempt}.log"

# 다음 에이전트 프롬프트에 주입할 탐색 지시 템플릿
EXPLORE_INSTRUCTION="
이전 시도의 전체 기록이 아래 디렉토리에 있다:
  ${OUT_DIR}/
이 디렉토리를 ls로 확인하고, 필요한 파일을 직접 골라 읽어라.
특히 이전 에이전트의 출력, 에러 로그, diff를 확인하라.
어떤 파일을 읽을지는 네가 판단하라."
```

핵심: `fail_context` 변수로 요약을 넘기는 코드를 모두 제거하고, 위 탐색 지시로 대체.

### A-2. `impl-process.sh` 적용

| 기존 (요약 전달) | 변경 (파일 참조 + 자율 탐색) |
|---|---|
| engineer → test-engineer: `fail_context`에 에러 발췌 | test-engineer에게 `$OUT_DIR/` 탐색 지시만 전달 |
| validator FAIL → engineer: `fail_context`에 피드백 요약 | engineer에게 `$OUT_DIR/` 탐색 지시 + validator 출력 파일명 힌트 |
| pr-reviewer → engineer: 코멘트 요약 | 동일하게 파일 참조 |

validator 출력 파일명 같은 "힌트"는 주되, 읽을지 말지는 에이전트가 결정.

### A-3. `design.sh` 적용

ITERATE 시 크리틱 출력 전체를 디자이너에게 요약하지 않고, `$OUT_DIR/design/` 디렉토리 경로만 전달. 디자이너가 이전 라운드의 크리틱 점수표, 스크린샷, 피드백을 직접 탐색.

### A-4. `bugfix.sh`, `plan.sh` 적용

동일 패턴. QA 분류 결과, validator 피드백 등 모두 파일 참조로 전환.

### A-5. 검증

- impl 루프에서 test_fail 재시도 시나리오 실행
- 에이전트가 실제로 `ls` + `cat`으로 파일을 읽는지 JSONL 로그에서 확인
- 요약 전달 대비 1회 성공률 수동 비교 (3회 이상 실행)

---

## Phase B — 히스토리 보존 구조화 + Pruning 정책

시도별 디렉토리 구조로 원본을 보존하고, 에이전트가 자율 탐색할 수 있게 한다. 동시에 토큰 비용 폭주를 막는 pruning 정책을 설정한다.

### B-1. 히스토리 디렉토리 구조

```
$OUT_DIR/history/
├── impl/
│   ├── attempt-1/
│   │   ├── engineer.log          # 에이전트 전체 출력
│   │   ├── code.diff             # git diff 스냅샷
│   │   ├── test-results.log      # vitest 출력
│   │   ├── validator.log         # validator 피드백
│   │   └── meta.json             # ↓ 아래 참조
│   ├── attempt-2/
│   └── ...
├── design/
│   ├── round-1/
│   │   ├── designer.log
│   │   ├── screenshots/          # variant-A.png, B.png, C.png
│   │   ├── critic.log
│   │   └── meta.json
│   └── ...
└── bugfix/
    └── ...
```

### B-2. `meta.json` 스키마 (핵심)

Meta-Harness에서 scores가 핵심 탐색 신호이므로 반드시 포함:

```json
{
  "attempt": 1,
  "timestamp": "2026-04-09T14:30:00",
  "loop": "impl",
  "depth": "std",
  "result": "FAIL",
  "fail_type": "test_fail",
  "scores": {
    "validator_score": null,
    "test_pass_rate": "3/7",
    "critic_score": null
  },
  "failed_tests": ["auth.test.ts:login", "auth.test.ts:logout"],
  "changed_files": ["src/auth/login.ts", "src/auth/types.ts"],
  "agent_sequence": ["engineer", "test-engineer"],
  "token_cost": 0.45,
  "error_summary_oneline": "TypeError: Cannot read property 'token' of undefined"
}
```

`error_summary_oneline`은 에이전트가 히스토리를 빠르게 스캔할 때 사용. 전체 에러는 `test-results.log`에 있다.

### B-3. `impl-process.sh` 히스토리 기록 로직

각 시도 완료 후(성공/실패 무관):

```bash
attempt_dir="$OUT_DIR/history/impl/attempt-${attempt}"
mkdir -p "$attempt_dir"
cp "$out_file" "$attempt_dir/engineer.log"
git diff HEAD > "$attempt_dir/code.diff"
cp "$test_output" "$attempt_dir/test-results.log" 2>/dev/null
cp "$validator_output" "$attempt_dir/validator.log" 2>/dev/null
# meta.json 생성 (jq로 조립)
```

다음 시도 에이전트 프롬프트:

```
이전 시도들의 히스토리가 아래에 있다:
  $OUT_DIR/history/impl/
각 attempt-N/ 디렉토리에 meta.json이 있으니 먼저 확인하고,
필요한 로그를 직접 골라 읽어라.
```

### B-4. Pruning 정책 ($200 플랜 토큰 관리)

히스토리가 무한히 쌓이면 에이전트가 읽는 토큰이 폭주한다. 규칙:

| 조건 | 정책 |
|------|------|
| attempt 5개 초과 | 가장 오래된 attempt의 로그 파일 삭제, `meta.json`만 유지 |
| 단일 로그 파일 > 50KB | 마지막 500줄만 유지 (tail -500) |
| design round 3개 초과 | 가장 오래된 round의 screenshots/ 삭제, critic.log + meta.json만 유지 |
| 전체 history/ > 5MB | 가장 오래된 시도부터 순차 정리 |

이 pruning은 `_agent_call()` 시작 시 또는 attempt 디렉토리 생성 시 자동 실행:

```bash
prune_history() {
  local loop_dir="$1"  # e.g., $OUT_DIR/history/impl
  local max_full=5     # 전체 보존할 최근 시도 수

  attempts=($(ls -d "$loop_dir"/attempt-* 2>/dev/null | sort -V))
  if [ ${#attempts[@]} -gt $max_full ]; then
    for old in "${attempts[@]:0:$((${#attempts[@]}-max_full))}"; do
      # meta.json만 남기고 나머지 삭제
      find "$old" -type f ! -name "meta.json" -delete
    done
  fi
}
```

### B-5. harness-memory.md 통합 관리

기존 플랜의 `design-memory.md`, `bugfix-memory.md` 분리 → 하나로 통합 유지.

```markdown
# harness-memory.md

## impl 패턴
- [FAIL] vitest.config.ts 수정 시 100% 실패 → 수정 금지
- [SUCCESS] 파일 2개 이하 변경 시 1회 성공률 높음

## design 패턴
- [FAIL] 모바일 뷰포트 미고려 시 critic ITERATE 확률 높음

## bugfix 패턴
- [FAIL] 타입 에러 수정 시 관련 테스트 동시 수정 누락 빈번
```

### B-6. 기존 Phase 5 라우팅 흡수

하드코딩 분기 대신 에이전트 프롬프트에 판단 기준만 추가:

```
# engineer.md에 추가
히스토리를 확인했을 때:
- 같은 파일에서 2회 이상 실패했으면 해당 모듈의 의존성까지 넓게 확인하라
- 같은 테스트가 반복 실패하면 테스트 자체의 문제인지 먼저 의심하라
- validator가 연속 FAIL이면 스펙 자체에 빈 곳이 있는지 확인하라
```

하네스가 분기하는 게 아니라, 에이전트가 히스토리를 보고 스스로 전략을 바꾸게 한다.

### B-7. 검증

- 3회 반복 impl 루프에서 3번째 에이전트가 attempt-1, 2의 meta.json을 실제로 읽는지 확인
- pruning 후에도 에이전트가 충분한 정보를 얻는지 확인
- history/ 디렉토리 크기 모니터링 (5MB 이하 유지되는지)

---

## Phase C — Environment Bootstrap 보강 (선택)

기존 `build_smart_context()`가 이미 잘 되어 있으므로 (3KB/파일 캡, 30KB 총량, hot-file 우선), 별도 함수 4개를 만들지 않고 기존 함수를 확장한다.

### C-1. `build_smart_context()` 루프 타입 파라미터 추가

```bash
build_smart_context() {
  local loop_type="$1"  # impl | design | bugfix | plan

  # 공통: 프로젝트 루트 상태, 기술 스택, .env 존재 여부
  common_context

  case "$loop_type" in
    impl)
      # 기존 로직 유지 (src 파일 스캔, hot-file 우선)
      ;;
    design)
      # 추가: CSS 변수 목록, src/components/ 트리
      # Pencil get_editor_state는 designer.md 내에서 에이전트가 직접 호출
      ls_components
      extract_css_tokens
      ;;
    bugfix)
      # 추가: git diff, 최근 커밋 5개, 관련 테스트 파일
      git_recent_context
      ;;
    plan)
      # 추가: 아키텍처 문서 목록, 모듈 의존성
      ls_docs
      ;;
  esac
}
```

### C-2. 각 루프 진입점에서 호출

```bash
# impl.sh
context=$(build_smart_context "impl")

# design.sh
context=$(build_smart_context "design")
```

### C-3. 검증

- 각 루프에서 에이전트 첫 턴의 `Read`/`Bash` 호출 횟수 비교 (적용 전/후)
- 불필요한 컨텍스트가 주입되어 토큰을 낭비하는 케이스가 없는지 확인

---

## Phase D — 로그 기반 지속적 자동 개선 (Step A만)

하네스 실행 로그를 Haiku가 분석하여 개선점을 찾고, 사용자 승인 후 수정한다. Step B(완전 자동)는 1인 개발 환경에서 하네스 자체가 깨질 위험이 크므로 도입하지 않는다.

### D-1. 전체 플로우

```
하네스 실행 완료 (write_run_end)
  ↓
review-agent.sh 실행 (Haiku, ~$0.02~0.05)
  ↓ 입력: $OUT_DIR/history/ 전체 + 현재 run JSONL
  ↓
review-result.json 생성
  ↓
다음 사용자 메시지 시 harness-review-inject.py (PreToolUse 훅)
  ↓ review-result.json 감지 → 프롬프트에 주입
  ↓
"이 리뷰 결과를 확인하고 수정하시겠습니까?"
  ↓ 사용자 승인
  ↓
Claude가 해당 파일 수정 → git commit
```

### D-2. 리뷰 에이전트 분석 전략

리뷰 에이전트가 로그에서 찾아야 할 것과 그에 대한 구체적 개선 액션:

#### 카테고리 1: 즉시 수정 가능 (HIGH 신뢰도)

| 감지 패턴 | 로그에서 찾는 방법 | 개선 액션 | 수정 대상 |
|---|---|---|---|
| 에이전트 크래시/타임아웃 | `_agent_call` 종료코드 != 0 또는 timeout 이벤트 | 타임아웃 값 조정, 프롬프트 길이 축소 | `harness/utils.sh` |
| 마커 파싱 실패 | `parse_marker()` 반환값 empty, 기대 마커가 출력에 없음 | 마커 정규식 완화 또는 에이전트 프롬프트에 마커 출력 강조 | `harness/utils.sh` 또는 `agents/*.md` |
| 동일 실패 3회 반복 | `history/impl/attempt-*/meta.json`에서 같은 `fail_type` + 같은 `failed_tests` 3연속 | `harness-memory.md`에 제약조건 추가 | `harness-memory.md` |
| 경로 위반 시도 | `agent-boundary.py` 블록 로그가 같은 에이전트에서 반복 | 해당 에이전트 프롬프트에 금지 경로 명시 | `agents/*.md` |

#### 카테고리 2: 제안만 (MEDIUM 신뢰도)

| 감지 패턴 | 로그에서 찾는 방법 | 제안 내용 |
|---|---|---|
| 불필요한 반복 | attempt-1에서 성공할 수 있었는데 validator가 과도하게 FAIL 판정 | validator.md 기준 완화 제안 |
| 비용 초과 에이전트 | JSONL의 `token_cost` > $1.5 (단일 호출) | 해당 에이전트의 컨텍스트 크기 제한 제안 |
| 미사용 컨텍스트 | `build_smart_context()`가 주입한 파일을 에이전트가 한 번도 Read하지 않음 | 해당 파일을 컨텍스트에서 제외 제안 |
| SPEC_GAP 빈발 | `spec_gap_count` 가 자주 1 이상 | architect 프롬프트의 스펙 완성도 기준 강화 제안 |

#### 카테고리 3: 기록만 (LOW 신뢰도)

| 감지 패턴 | 로그에서 찾는 방법 | 기록 내용 |
|---|---|---|
| 평균 시도 횟수 추세 | 최근 10회 실행의 attempt 수 평균 | 추세 리포트 |
| 루프별 평균 비용 | JSONL의 run_end 이벤트에서 total_cost | 비용 추세 리포트 |
| 에이전트별 성공률 | meta.json의 result 필드 집계 | 성공률 대시보드 |

### D-3. `review-agent.sh` 구현

```bash
#!/bin/bash
# 입력: $OUT_DIR, $JSONL_LOG
# 출력: $OUT_DIR/review-result.json

REVIEW_PROMPT="
당신은 하네스 로그 리뷰어다.

## 분석할 데이터
1. 현재 실행 로그: $JSONL_LOG
2. 히스토리: $OUT_DIR/history/
3. 현재 메모리: harness-memory.md

## 분석 항목 (우선순위순)

### HIGH (즉시 수정 가능)
- 에이전트 크래시/타임아웃이 있는가?
- 마커 파싱 실패가 있는가?
- 같은 실패가 3회 이상 반복되는가?
- agent-boundary 블록이 반복되는가?

### MEDIUM (제안)
- 1회 만에 성공할 수 있었는데 불필요한 반복이 있었는가?
- 단일 에이전트 호출 비용이 \$1.5를 초과하는가?
- 주입된 컨텍스트 중 에이전트가 읽지 않은 파일이 있는가?
- SPEC_GAP가 빈번하게 발생하는가?

### LOW (기록)
- 평균 시도 횟수 추세는?
- 루프별 평균 비용 추세는?

## 출력 형식
JSON으로 출력하라:
{
  \"issues\": [
    {
      \"type\": \"repeated_failure\",
      \"confidence\": \"HIGH\",
      \"evidence\": \"attempt-1,2,3 모두 auth.test.ts:login에서 TypeError\",
      \"target_file\": \"harness-memory.md\",
      \"suggested_change\": \"## impl 패턴에 추가: auth 모듈 수정 시 token 초기화 로직 필수 확인\",
      \"risk\": \"LOW\"
    }
  ],
  \"stats\": {
    \"total_attempts\": 3,
    \"success\": false,
    \"total_cost\": 1.35,
    \"duration_minutes\": 12
  },
  \"summary\": \"1 HIGH, 1 MEDIUM issues found\"
}
"

# Haiku 호출 (저비용)
claude --model haiku --print "$REVIEW_PROMPT" > "$OUT_DIR/review-result.json"
```

### D-4. `harness-review-inject.py` 훅 구현

```python
# hooks/harness-review-inject.py
# 트리거: UserPromptSubmit (사용자가 다음 메시지를 보낼 때)

import json, os, glob

def hook(event):
    # 미처리 리뷰 파일 검색
    review_files = glob.glob("/tmp/*_review-result.json")
    if not review_files:
        return {"continue": True}

    review = json.loads(open(review_files[0]).read())
    high_issues = [i for i in review["issues"] if i["confidence"] == "HIGH"]
    medium_issues = [i for i in review["issues"] if i["confidence"] == "MEDIUM"]

    if not high_issues and not medium_issues:
        os.remove(review_files[0])
        return {"continue": True}

    # 프롬프트에 주입
    inject_text = "## 하네스 리뷰 결과 (이전 실행)\n\n"
    inject_text += f"통계: {review['stats']}\n\n"

    if high_issues:
        inject_text += "### 즉시 수정 권장 (HIGH)\n"
        for issue in high_issues:
            inject_text += f"- [{issue['type']}] {issue['evidence']}\n"
            inject_text += f"  수정 대상: {issue['target_file']}\n"
            inject_text += f"  제안: {issue['suggested_change']}\n\n"

    if medium_issues:
        inject_text += "### 검토 제안 (MEDIUM)\n"
        for issue in medium_issues:
            inject_text += f"- [{issue['type']}] {issue['evidence']}\n"
            inject_text += f"  제안: {issue['suggested_change']}\n\n"

    inject_text += "위 항목을 검토하시겠습니까? 승인하시면 수정합니다.\n"

    return {
        "continue": True,
        "additionalContext": inject_text
    }
```

### D-5. 수정 범위 제한 (안전장치)

절대 규칙: `src/` 코드는 건드리지 않는다.

| 허용 | 금지 |
|------|------|
| `agents/*.md` (에이전트 프롬프트) | `src/` (앱 코드) |
| `harness/*.sh` (오케스트레이션 로직) | `hooks/` (훅 자체) |
| `orchestration/*.md` (플로우 문서) | `.env`, 설정 파일 |
| `harness-memory.md` (메모리 파일) | `orchestration-rules.md` (마스터 규칙) |

`orchestration-rules.md`를 금지 목록에 추가하는 이유: 이 파일은 전체 시스템의 single source of truth이므로 자동 수정 대상에서 제외해야 안전하다.

### D-6. 학습 누적 + 자동 승격

```
$OUT_DIR/review-history/
├── 2026-04-09_impl_run1.json
├── 2026-04-09_design_run1.json
├── 2026-04-10_impl_run2.json
└── ...

승격 규칙:
- 같은 issue.type + 같은 target_file이 3회 이상 → harness-memory.md에 영구 제약조건 추가
- 이미 승격된 패턴이 이후 5회 연속 미발생 → "해결됨" 태그 추가 (삭제는 수동)
```

review-history pruning: 최근 30개만 유지 (약 1개월분).

### D-7. 비용 분석

| 항목 | 비용 |
|------|------|
| Haiku 리뷰 1회 | ~$0.02~0.05 |
| 사용자 승인 후 Sonnet 수정 1회 | ~$0.10~0.30 |
| 하네스 실행당 추가 비용 | ~$0.05~0.35 |
| 월 30회 실행 기준 | ~$1.5~10.5 |

### D-8. 검증

- 도입 후 2주간 HIGH 이슈의 정탐률 수동 확인 (목표: 80% 이상)
- 리뷰 결과에서 제안한 수정이 실제로 다음 실행에서 해당 실패를 방지하는지 추적
- review-history에서 승격된 패턴이 유효한지 월 1회 수동 검토

---

## 실행 순서 및 의존성

```
Phase A (Feedback Compression 제거)
  ↓ 에이전트가 원본 파일을 직접 읽는 구조 확립
Phase B (히스토리 보존 + Pruning)
  ↓ Phase A의 파일 참조 구조 위에 시도별 디렉토리 추가
Phase C (Environment Bootstrap 보강) — 선택
  ↓ A, B와 독립적이나 B 이후 검증 시 필요성 판단
Phase D (로그 기반 자동 개선)
  ↓ A+B가 만든 히스토리와 로그를 분석 재료로 사용
```

Phase A와 B는 순차 필수. Phase C는 B 검증 후 에이전트 첫 턴 탐색이 여전히 비효율적일 때만 진행. Phase D는 A+B 안정화 후 도입.

## 빠트린 항목 체크리스트

| 항목 | 포함 여부 | 비고 |
|------|-----------|------|
| Tech Epic 루프(Loop E) | Phase A, B 적용 대상에 포함 필요 | 현재 플랜에서 누락, 실제 적용 시 tech-epic.sh도 동일 패턴 적용 |
| 예산 캡 재조정 | Phase B pruning에서 간접 해결 | 히스토리 크기 제한으로 토큰 소비 관리 |
| orchestration-rules.md 동기화 | Phase A~B 완료 후 반영 필요 | 변경된 에이전트 간 통신 방식을 마스터 문서에 업데이트 |
