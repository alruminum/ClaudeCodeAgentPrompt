# 하네스 엔지니어링 백로그

> 최종 업데이트: 2026-04-05
> 이 파일은 하네스 기능 추가/변경 시 즉시 갱신한다 (orchestration-rules.md 정책 9).
> 항목 상태: 보류 / 진행중 / 완료

---

## 완료 항목 ✅

### 베이스라인 (초기 구축)

| 항목 | 구현체 |
|---|---|
| 결정론적 게이트 5모드 | `harness-executor.sh` |
| 플래그 기반 상태머신 | `/tmp/{prefix}_*` |
| Ground truth 테스트 | `npx vitest run` (LLM 독립) |
| 에이전트 도구 경계 물리적 차단 | `agent-boundary.py` |
| 보안 감사 게이트 | `security-reviewer` OWASP+WebView |
| Smart Context 50KB 캡 | `build_smart_context()` in `harness-loop.sh` |
| 실패 유형별 수정 전략 | `fail_type` 4종 분기 |
| 실패 패턴 자동 프로모션 | 3회 누적 → Auto-Promoted Rules |
| 단일 소스 원칙 물리적 강제 | `orch-rules-first.py` |
| 의도 분류 라우터 | regex + LLM 하이브리드 |
| 루프 A~E 5종 | orchestration-rules.md + harness-executor.sh |

### 고도화 항목

| ID | 항목 | 완료일 |
|---|---|---|
| **G3** | 수용 기준 메타데이터 — `(TEST)/(BROWSER:DOM)/(MANUAL)` 태그 + validator Plan Validation 게이트 | 2026-04-05 |
| **G6** | PR body 자동 생성 — HARNESS_DONE 후 `/tmp/{p}_pr_body.txt` | 2026-04-05 |
| **G10** | doc-garden 스킬 — 문서-코드 불일치 리포트 (수동 트리거, 자동 수정 없음) | 2026-04-05 |

---

## SOLO — 1인 개발자 (현재)

즉시 적용 가능한 항목부터 우선 진행. 재검토 조건이 있는 항목은 조건 발생 시 진행.

### ~~P0. Depth Selector — `--depth=fast/std/deep`~~ ✅ 완료 (2026-04-05)

**왜**: 변수 rename과 핵심 모듈 재작성이 동일 루프(5 에이전트 풀)를 탐. 1인 개발자에게 속도·토큰 낭비.

**동작**:
```
fast  → engineer only (test-engineer·validator·pr-reviewer·security 스킵)
std   → 현재 루프 C 전체 (기본값)
deep  → std + coverage gate + BROWSER:DOM
```

**자동 선택 규칙 (orchestration-rules에 추가 예정)**:
- impl 파일에 `(MANUAL)` 태그만 있으면 `--depth=fast` 자동 선택
- impl 파일에 `(BROWSER:DOM)` 태그 있으면 `--depth=deep` 권장

**변경 대상**: `harness-executor.sh`, `harness-loop.sh`, `orchestration-rules.md`

**선행 작업**: 없음

---

### ~~P1. Memory 반자동 기록 (초안 제안 → 유저 승인)~~ ✅ 완료 (2026-04-05)

**왜**: 현재 `harness-memory.md`는 수동 전용. 에이전트가 실패 패턴 초안을 제안하면 기록 비용이 줄어 cross-project 학습이 실제로 작동함.

**동작**:
```
루프 C FAIL 시
  → engineer가 /tmp/{p}_memory_candidate.md에 초안 작성
  (형식: "YYYY-MM-DD | fail_type | 파일패턴\n→ 수정 전략: ...")

HARNESS_DONE 후
  → 메인 Claude: "이 패턴 harness-memory.md에 기록할까요?" 제안
  → 유저 Y → 자동 추가 / N → 폐기
```

**기록 예시**:
```markdown
2026-04-06 | validator_fail | src/hooks/use*.ts
훅 반환 타입 명시 누락 — validator 반복 반려.
→ 수정 전략: impl 파일에 "커스텀 훅 반환 타입 명시 필수" 추가
```

**변경 대상**: `harness-loop.sh`

**선행 작업**: 없음

**향후**: 잘 되면 유저 승인 없이 자동 기록으로 전환 검토

---

### P2. Smart Context 명세화

**상태**: 보류 (장기 프로젝트 시작 시)

**왜**: `build_smart_context()`가 50KB 캡만 구현. hot-file 선택 기준이 없으면 장기 프로젝트에서 관련 없는 파일이 컨텍스트를 채움.

**동작**:
```
Hot files 선택 기준:
  1. impl 파일에 명시된 경로 (최우선)
  2. git diff --name-only HEAD~3 HEAD (최근 변경 파일)
  3. 나머지는 50KB 한도 내에서 추가

GC 경계:
  루프 C 3회 초과 시 이전 attempt 에러 트레이스만 압축해서 carry-forward
  (이전 attempt의 전체 컨텍스트는 버림)
```

**변경 대상**: `harness-loop.sh` (`build_smart_context()` 함수)

**재검토 트리거**: 장기 프로젝트(에픽 3개+) 시작 시 또는 컨텍스트 관련 실패 반복 시

---

### P3. 루프 체크포인트 재개

**상태**: 보류 (세션 중단 손해 경험 시)

**왜**: 루프 C 3회차 도중 세션 만료되면 처음부터 재시작. 이미 통과한 단계를 다시 도는 비용.

**동작**:
```json
// /tmp/{p}_loop_state.json (루프 진행 중 유지)
{
  "attempt": 2,
  "last_completed_stage": "test-engineer",
  "impl_file": "docs/.../impl/01-auth.md",
  "fail_type": "validator_fail",
  "fail_detail": "..."
}
```
세션 재시작 시 `harness-executor.sh`가 파일 감지 → 해당 stage부터 재개.

**변경 대상**: `harness-executor.sh`, `harness-loop.sh`

**재검토 트리거**: 세션 중단으로 루프 재시작 손해를 실제로 경험했을 때

---

### P4. 비용 게이트 (선택적)

**상태**: 보류 (선택적)

**왜**: 루프 시작 전 예상 호출 수를 알면 간단한 수정에 풀 루프 도는 것을 방지.

**동작**:
```
[HARNESS] 예상: engineer(1) + test-engineer(1) + validator(1) + pr-reviewer(1) + security(1) = 최소 5회
진행하시겠습니까? (Y/n/--depth=fast)
```
`--yes` 플래그로 스킵 가능. `--depth=fast` 입력 시 즉시 변경.

**변경 대상**: `harness-executor.sh`

**재검토 트리거**: 선택적 — 토큰 비용이 체감될 때

---

### ~~P5. AMBIGUOUS → product-planner 자동 트리거~~ ✅ 완료 (2026-04-05)

**왜**: 현재 harness-router.py가 프롬프트를 AMBIGUOUS로 분류하면 그냥 PASS (일반 채팅 폴백). pseudo-code의 `triggerDeepInterview()` 의도가 구현 안 됨. 모호한 요청이 루프로 진입하면 잘못된 방향으로 전체 루프를 소모할 수 있음.

**동작**:
```
harness-router.py가 AMBIGUOUS 판정
  → hookSpecificOutput에 product-planner 자동 호출 지시 주입
  → 메인 Claude: product-planner 에이전트 호출 (역질문 모드)
  → PRD/TRD 윤곽 잡힌 후 → 루프 A or C 진입
```

**AMBIGUOUS 기준 명확화 필요**:
- 구현 요청인지 질문인지 불분명한 경우
- 요청은 명확한데 scope가 불분명한 경우 (전자만 AMBIGUOUS, 후자는 ACTIONABLE로 처리)

**변경 대상**: `hooks/harness-router.py` (AMBIGUOUS 처리 분기)

**선행 작업**: 없음

---

### P6. 세션 컨텍스트 브리지

**상태**: 보류 (즉시 적용 가능)

**왜**: 새 세션마다 "기존꺼 파악하라"는 지시에 토큰 낭비. `SessionStart` 훅에서 현재 프로젝트 상태를 자동 압축해서 주입하면 파악 비용 0.

**동작**:
```
SessionStart 훅 실행
  → 현재 프로젝트 harness.config.json 존재 확인
  → /tmp/{p}_current_issue 읽기 (진행 중 이슈)
  → backlog.md에서 진행중 항목 추출
  → hookSpecificOutput에 압축 요약 주입:
     "프로젝트: {name} | 진행 중: {issue} | 마지막 완료: {last_done}"
```

**변경 대상**: `hooks/harness-session-start.py`

**선행 작업**: 없음

---

### P7. impl 파일 간 충돌 감지

**상태**: 보류 (즉시 적용 가능)

**왜**: "이거 하나 고치면 기존게 안되고" — impl A가 수정하는 파일을 미완료 impl B도 수정하면 루프 완료 후 충돌. 사전 경고 없음.

**동작**:
```
harness-executor.sh impl 진입 시
  → 현재 impl 파일의 변경 대상 파일 목록 파싱
  → 미완료 다른 impl 파일들과 교집합 체크
  → 겹치는 파일 발견 → IMPL_CONFLICT 경고 출력
  → 유저 결정: 무시하고 진행 / 순서 조정
```

**변경 대상**: `harness-executor.sh`

**선행 작업**: impl 파일 포맷에 "변경 대상 파일 목록" 섹션 명시 필요 (architect.md 규칙 추가)

---

### P8. 납품 게이트

**상태**: 보류 (B2B 납품 프로젝트 시작 전)

**왜**: B2B 납품 시 "클라이언트에게 넘겨도 되는가" 기준이 security-reviewer와 다름. 환경변수 노출, console.log 잔존, 하드코딩 상수, 빌드 성공 여부를 HARNESS_DONE 직후 또는 git push 전에 자동 확인.

**동작**:
```
/deliver 커맨드 or git push 전 훅
  → 환경변수 노출 스캔 (.env 패턴이 src/** 에 있는지)
  → console.log / debugger 잔존 스캔
  → 하드코딩 URL/키 스캔
  → npm run build 성공 여부
  → DELIVERY_READY / DELIVERY_BLOCKED 판정
```

**변경 대상**: `commands/deliver.md` (신규) + `setup-harness.sh` (git push 훅 옵션)

**선행 작업**: 없음

---

### P9. 하네스 smoke test

**상태**: 보류 (P0~P5 구현 후)

**왜**: 하네스 자체를 고치고 나서 잘 동작하는지 확인 방법이 없음. 새 게이트 추가 후 기존 루프가 깨졌는지 알 수가 없음.

**동작**:
```
/harness-test 커맨드
  → fixture impl 파일 (테스트용 더미) 로드
  → harness-loop.sh 드라이런 (실제 에이전트 호출 없이 플래그 흐름만 체크)
  → 각 게이트(test_pass → validator_pass → pr_lgtm → security_pass) 순서 검증
  → SMOKE_PASS / SMOKE_FAIL 출력
```

**변경 대상**: `commands/harness-test.md` (신규)

**선행 작업**: P0 완료 후 적용 권장 (depth 분기가 생기면 각 depth별 smoke test 필요)

---

### P10. 에이전트 병목 리포트

**상태**: 보류 (선택적)

**왜**: `-agent-calls.log`가 쌓이지만 분석 없음. 어떤 에이전트가 가장 많이 실패하는지, 어떤 파일 패턴이 3회 초과를 유발하는지 알면 개선 방향이 명확해짐.

**동작**:
```
/harness-stats 커맨드
  → {prefix}-agent-calls.log 파싱
  → 에이전트별 실패율
  → 평균 attempt 수
  → IMPLEMENTATION_ESCALATE 유발한 impl 파일 패턴
  → 리포트 출력 (수정 없음)
```

**변경 대상**: `commands/harness-stats.md` (신규)

**재검토 트리거**: 에픽 3개 이상 완료 후 패턴 파악하고 싶을 때

---

### G2. 커버리지 게이트 (신규 파일 60%)

**상태**: 보류

**왜 보류**: P0 Depth Selector 완료 후 test-engineer 품질이 어떻게 변하는지 확인 먼저. 신규 파일 필터링 로직(git diff JSON 파싱)이 fragile할 수 있음.

**구현 위치**: `harness-loop.sh`
```bash
npx vitest run --coverage
# git diff HEAD~1 --name-only --diff-filter=A 로 신규 파일 목록 추출
# 신규 파일 coverage < 60% → coverage_fail
```

**선행 작업**: `npm install -D @vitest/coverage-v8` + `vite.config.ts` coverage 섹션

**재검토 트리거**: test-engineer가 너무 얕은 테스트만 반복 작성할 때

---

### G7. BROWSER:DOM 자동 검증 (opt-in)

**상태**: 보류

**왜 보류**: 루프마다 dev server + Playwright = 30~60초 추가. G2 이후에 함께 검토.

**구현 위치**: `harness-loop.sh` (test-engineer 완료 후, validator 호출 전)
```bash
if grep -qc "(BROWSER:DOM)" "$IMPL_FILE"; then
  npm run dev &
  DEV_PID=$!
  # design-critic 에이전트 호출 (DOM 검증 모드)
  kill $DEV_PID
fi
```

**선행 작업**: G2 완료 + architect.md에 UI 태스크 = `(BROWSER:DOM)` 필수 규칙 추가

**재검토 트리거**: UI 버그가 vitest 통과 후 반복 발견될 때

---

## MEDIUM — 팀 3~10인

SOLO 항목(P0~P4) 완료 후 적용. 팀 합류 시 재검토.

### G1. 크로스모델 리뷰 (보안 파일 한정)

**왜**: auth/api/db 파일에서 단일 모델 blind spot 보완. 전체 PR 적용은 토큰 과다.

**구현**:
```bash
security_files=$(git diff --name-only HEAD | grep -E 'auth|api|token|password|secret|db' || echo "")
if [[ -n "$security_files" ]]; then
  claude --model haiku --print "이 diff에서 버그/취약점 찾아라: ..."
fi
```

**변경 대상**: `harness-loop.sh`

**재검토 트리거**: 보안 사고 발생 또는 팀 2인+ 합류

---

### G4. 커스텀 린트 (sonarjs + import 정렬)

**왜**: 코드베이스 10파일+ 이상에서 중복 로직이 자주 등장할 때 pr-reviewer 부담 감소.

**구현**: `.eslintrc`에 `eslint-plugin-sonarjs` + import 정렬 규칙 추가. `harness-loop.sh` lint 단계 삽입.

**재검토 트리거**: 코드베이스 10파일+ + 중복 로직 반복 발생

---

### G5. GC 에이전트 (/scan 커맨드)

**왜**: 에픽 5개 이상 완료 후 dead code 누적 시 jscpd·knip으로 자동 감지. 리포트만, 자동 PR 없음.

**구현**: `skills/scan.md` (신규 커맨드)

**재검토 트리거**: 에픽 5개 완료 후 dead code 체감

---

### G9. 관측성 로그 (/tmp 파일 기반)

**왜**: 프로덕션 트래픽 발생 후 버그 재현이 어려워질 때.

**구현**: `/tmp/{p}_observability/` 파일 로그. Web UI 없음. Grafana 연동 확장 가능 구조.

**재검토 트리거**: 프로덕션 트래픽 발생 + 버그 재현 어려움

---

## LARGE — 팀 10인+

MEDIUM 항목 완료 후 적용. 브랜치 전략·CI 인프라 확립이 전제.

### G2 (확장). 커버리지 게이트 전체 70%

SOLO G2(신규 파일 60%) → 전체 파일 70%로 기준 상향.

**변경 대상**: `harness-loop.sh` (SOLO G2 구현 위에 기준값만 변경)

---

### G8. Git Worktree 격리 실행

**왜**: 팀 병렬 개발 시 브랜치 충돌 방지. 각 루프를 별도 worktree에서 실행.

**구현**: `isolation: "worktree"` Claude Code 기능 활용. 성공 시만 메인 병합.

**변경 대상**: `harness-executor.sh`, `harness-loop.sh`

**전제**: feature branch 전략 확립

---

### G11. 뮤테이션 테스트 (stryker-js)

**왜**: 테스트가 통과해도 실제로 버그를 잡는지 검증. 테스트 신뢰도 문제가 반복될 때.

**구현**: `harness-loop.sh` 선택적 단계로 stryker-js 실행.

**재검토 트리거**: 테스트 신뢰도 문제 반복 + 토큰 예산 여유

---

### G1+. 크로스모델 리뷰 (전체 PR)

MEDIUM G1(보안 파일 한정) → 전체 PR로 확장.

**전제**: G1 MEDIUM 완료 + 토큰 예산 충분

---

## 재검토 트리거 요약

| 상황 | 재검토 항목 |
|---|---|
| 즉시 | P6, P7 |
| 장기 프로젝트 시작 | P2 |
| 세션 중단 손해 경험 | P3 |
| 토큰 비용 체감 | P4 |
| test-engineer 품질 반복 하락 | G2 |
| UI 버그가 vitest 통과 후 반복 발견 | G7 |
| 팀 2인+ 합류 또는 보안 사고 | G1 (MEDIUM) |
| 코드베이스 10파일+ + 중복 로직 반복 | G4 |
| 에픽 5개 완료 후 dead code 체감 | G5 |
| 프로덕션 트래픽 발생 | G9 |
| 브랜치 전략 + 팀 10인+ | G8 |
| 테스트 신뢰도 반복 문제 + 예산 여유 | G11 |
