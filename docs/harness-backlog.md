# 하네스 엔지니어링 백로그

> 최종 업데이트: 2026-04-12
> 하네스 수정 시 **첫 번째 단계**로 갱신한다 (백로그 → 수정 → state).

---

## 코드 범례

| 코드 | 의미 | 적용 시점 |
|---|---|---|
| **S** (Solo) | 1인 개발자 기준 | 지금 바로 |
| **M** (Medium) | 팀 3~10인 | 팀 합류 시 |
| **L** (Large) | 팀 10인+ | 규모 확장 시 |

---

## 전체 현황

### 완료 (✅)

| 코드 | 항목 | 완료일 |
|---|---|---|
| BASE | 결정론적 게이트, 루프 A~E, 플래그 상태머신, 에이전트 경계, 보안 감사, 실패 전략 | 초기 |
| S1 | 수용 기준 메타데이터 (TEST/BROWSER:DOM/MANUAL 태그) | 04-05 |
| S2 | PR body 자동 생성 | 04-05 |
| S3 | doc-garden (문서-코드 불일치 리포트) | 04-05 |
| S4 | Depth Selector (fast/std/deep) | 04-05 |
| S5 | Memory 반자동 기록 (실패 패턴 초안 → 유저 승인) | 04-05 |
| S6 | AMBIGUOUS 자동 트리거 (product-planner 힌트 주입) | 04-05 |
| S7 | 세션 컨텍스트 브리지 (새 세션 상태 자동 주입) | 04-05 |
| S8 | 하네스 smoke test (/harness-test) | 04-05 |
| S10 | 납품 게이트 (/deliver, B2B 납품 전 체크) | 04-05 |
| S12 | 루프 체크포인트 재개 (루프 C/D 상태 감지 + 재진입 스킵) | 04-07 |
| S16 | Router spawn → Popen 제거, Rate Limiter 유지 | 04-07 |
| S17 | JSON Lease → 제거, pre-evaluator 유지 | 04-07 |
| S18 | Adaptive Interview (AMBIGUOUS → Haiku Q&A → additionalContext 힌트) | 04-07 |
| S19 | macOS timeout 호환 (shim) + impl_path 누락 가드 | 04-06 |
| S20 | Agent Observability (전 에이전트 실행 로그 + FIFO 10-run 보존) | 04-06 |
| S21 | 타임스탬프 로깅 (hlog 함수) | 04-06 |
| S22 | 에이전트 호출별 timeout 강제 + exit 124 감지 | 04-06 |
| S23 | std 모드 게이트 축소 (5→3단계, deep 분리) | 04-06 |
| S24 | grep 파싱 → 라인 전체 매칭 강화 | 04-06 |
| S25 | BATS 테스트 (하네스 스크립트 자체 테스트, 115건+) | 04-06 |
| S26 | git diff 타이밍 픽스 (pr-reviewer 빈 diff 방지) | 04-06 |
| S27 | fast_classify() — regex 2단계 즉시 분류 | 04-07 |
| S28 | _call_haiku() — urllib API 직접 + CLI 폴백 | 04-07 |
| S30 | 에이전트별 --max-budget-usd 2.00 | 04-06 |
| S31 | 킬 스위치 (/harness-kill) | 04-06 |
| S32 | 전체 루프 비용 상한 $10 | 04-06 |
| S33 | Stop hook — harness_active 물리적 종료 차단 (이후 폐기, 정책 7로 대체) | 04-07 |
| S34 | Bash timeout 환경변수 (10분 기본 / 30분 상한) | 04-07 |
| S35 | executor 경로 폴백 (프로젝트 → 글로벌) | 04-07 |
| S39 | agent out_file 가드 — check_agent_output() 5곳 전수 적용 | 04-07 |
| S40 | rollback_attempt — 실패 시 git stash로 오염 코드 격리 | 04-07 |
| S45 | JSONL 로그 보강 — agent_stats/decision/phase 이벤트 | 04-07 |
| S46 | /harness-review 스킬 — JSONL 파서 + WASTE 패턴 진단 | 04-07 |
| S47 | HARNESS_DONE 후 자동 /harness-review 트리거 (정책 17) | 04-07 |
| S48 | QA 에이전트 스코프 강화 — 인프라 탐색·Agent·Bash 금지 | 04-07 |
| S49 | 루프 D 라우팅 단순화 — 3타입, 심각도 제거, QA 이슈 등록 의무화 | 04-07 |
| S50 | harness-review 비정상 종료 진단 — 4패턴 | 04-07 |
| S51 | harness-review 토큰 낭비 진단 — 3패턴 | 04-07 |
| S52 | run_end result 마커 기록 — EARLY_EXIT 오탐 수정 | 04-07 |
| S53 | 로그 분석 기반 5건 수정 | 04-07 |
| S54 | PREFIX 전략 통일 — harness_common.py 공유 모듈 | 04-07 |
| S55 | settings.json 5개 훅 등록 + file-ownership-gate 통합 | 04-07 |
| S56 | 하드코딩 경로 제거 + session-start timeout | 04-07 |
| S57 | 훅 간섭 테스트 (dry-run + 실제 시나리오) | 04-07 |
| S58 | append_failure race condition + grep -F + 변수 인용 | 04-07 |
| S60 | 에이전트 명세 정교화 4건 | 04-07 |
| S61 | 문서 보완 — README/post-commit-scan/harness-memory 시드 | 04-07 |
| S62 | 스크립트↔룰 동기화 — 6개 스크립트 오케스트레이션 룰 반영 | 04-09 |
| S63 | utils.sh 공용 함수 추출 — parse_marker()/run_plan_validation() | 04-09 |
| S64 | impl-process.sh fast 모드 정정 → S72로 대체됨 | 04-09 |
| S65 | SPEC_GAP 핸들링 — spec_gap_count 동결/에스컬레이션 | 04-09 |
| S66 | bugfix.sh 라우팅 정비 — backlog/KNOWN_ISSUE/DESIGN_ISSUE 경로 | 04-09 |
| S67 | plan.sh 흐름 완성 — 6단계 완전 구현 | 04-09 |
| S68 | design.sh 흐름 완성 — ITERATE feedback + ESCALATE 분기 | 04-09 |
| S69 | 스마트 컨텍스트 공용화 + validator diff 패싱 | 04-09 |
| S70 | 훅 전수 감사 — orch-rules-first 패턴 수정, drift-check 매핑, 데드코드 삭제 | 04-09 |
| S71 | 디자인 워크플로우 v2 — Pencil MCP 기반 재설계 | 04-09 |
| S72 | 커밋 전략 개편 — engineer 즉시 커밋 + pr-reviewer 전 depth 통일 | 04-09 |
| S73 | Phase C — build_loop_context() + 루프별 진입 컨텍스트 prepend | 04-09 |
| S74 | Phase D — review-agent.sh + harness-review-inject.py 훅 | 04-09 |
| S75 | 하네스 출력 현행화 — 레이블 정리, @MODE: 형식 통일 | 04-09 |
| S76 | 에이전트 인프라 탐색 금지 강화 — Universal Preamble에 인프라 Read 금지 | 04-09 |
| S77 | harness-review INFRA 오탐 수정 — agent-config/ EXCLUSIONS | 04-09 |
| S78 | 디자인 루프 2모드 분리 — DEFAULT/CHOICE | 04-09 |
| S79 | bugfix SPEC_ISSUE 오염 수정 — MODULE_PLAN 프리픽스 제거 | 04-09 |
| S80 | MODULE_PLAN mode 파라미터 도입 | 04-09 |
| S81 | 디자인 아키텍처 v4 — 2×2 매트릭스, ux 스킬 직접 호출 | 04-10 |
| RF1 | 5f19c2a 복원 리팩토링 — Popen 전면 제거 | 04-07 |
| #A1 | 게이트 책임 분리 — 훅은 외부 방어만, 순서는 스크립트가 담당 | 04-11 |
| #A2 | 마커 파싱 강건화 | 04-11 |
| #A3 | 플래그 이름 상수화 (flags.sh) | 04-11 |
| #B1 | Universal Preamble 분리 — 공통 지침 동적 주입 (agents/preamble.md) | 04-11 |
| #C2 | 비용/시간 추적 — 타이밍 요약 + ISO 타임스탬프 강화 | 04-11 |
| #D8 | settings.json 훅 자동 구성 — _meta: harness 태그 | 04-11 |
| — | /tmp 상태 → 프로젝트별 `.claude/harness-state/` 영속 디렉토리 이전 | 04-11 |
| — | architect BUGFIX_PLAN → LIGHT_PLAN 일반화 | 04-11 |
| — | designer 이슈 생성 Phase 0-0 이전 + 프로젝트 하드코딩 제거 | 04-11 |
| — | depth frontmatter 누락 방어 — std 폴백 | 04-11 |
| — | DESIGN_ISSUE 이슈 중복 생성 제거 + HANDOFF 이슈번호 전달 | 04-11 |
| — | agent-gate qa HARNESS_ONLY 예외 | 04-11 |
| — | bugfix 경로 모순 5건 수정 + 낭비 자동 감지 보강 | 04-11 |
| — | harness-review: 세션 로그 모순 자동 감지 | 04-11 |
| — | harness-review: 리뷰 자동 실행 + 원문 출력 강제 | 04-11 |
| — | 에이전트 분류 상수 단일 소스 + issue-gate qa 예외 | 04-11 |
| — | depth 추천 기준 재설계 — architect 자율 판단 존중 | 04-11 |
| — | harness-review: .reviewed 마커 + 자동 리마인더 | 04-11 |
| — | 히스토리 루프별 격리 + 에이전트 I/O 원문 전량 보존 | 04-11 |
| PY1 | **Python 마이그레이션 — core 모듈 9개 신규 작성 + 래퍼 스왑** | 04-12 |
| PY2 | depth upshift Python 함수 직접 호출 전환 | 04-12 |
| PY3 | 타임아웃 watchdog + SIGTERM 핸들러 + 데드코드 제거 | 04-12 |

### 대기 / 보류

| 코드 | 항목 | 규모 | 상태 |
|---|---|---|---|
| S9 | impl 충돌 감지 (파일 겹침 사전 경고) | S | ⬜ 대기 |
| S11 | Smart Context 명세화 (hot-file 선택 + attempt 간 Context GC) | S | ⬜ 보류 |
| S13 | 에이전트 병목 리포트 (/harness-stats) | S | ⬜ 보류 |
| S14 | 커버리지 게이트 신규파일 60% | S | ⬜ 보류 |
| S15 | BROWSER:DOM 자동 검증 (opt-in Playwright) | S | ⬜ 보류 |
| S59 | _agent_call stdin pipe 전환 | S | ⬜ 보류 |
| M1 | 크로스모델 리뷰 (보안 파일 한정, Haiku 2nd opinion) | M | ⬜ 보류 |
| M2 | 커스텀 린트 (sonarjs + import 정렬) | M | ⬜ 보류 |
| M3 | GC 에이전트 (/scan, dead code 리포트) | M | ⬜ 보류 |
| M4 | 관측성 로그 (/tmp 파일 기반) | M | ⬜ 보류 |
| L1 | 커버리지 게이트 전체 파일 70% | L | ⬜ 보류 |
| L2 | Git Worktree 격리 실행 | L | ⬜ 보류 |
| L3 | 뮤테이션 테스트 (stryker-js) | L | ⬜ 보류 |
| L4 | 크로스모델 리뷰 전체 PR | L | ⬜ 보류 |

---

## 재검토 트리거

| 트리거 | 항목 |
|---|---|
| 즉시 | S9 |
| 장기 프로젝트 (에픽 3개+) 시작 | S11 |
| 에픽 3개+ 완료 후 패턴 파악 | S13 |
| test-engineer 품질 반복 하락 | S14 |
| UI 버그 vitest 통과 후 반복 발견 | S15 |
| 팀 합류 또는 보안 사고 | M1 |
| 코드베이스 10파일+ + 중복 반복 | M2 |
| 에픽 5개+ 완료 후 dead code 체감 | M3 |
| 프로덕션 트래픽 발생 | M4 |
| 팀 10인+ + 브랜치 전략 확립 | L1~L4 |

---

## 항목별 상세 (대기/보류만)

### ⬜ S9 — impl 충돌 감지

동일 파일을 수정하는 impl이 여러 개 동시에 존재할 때 사전 경고.

```
impl 진입 시 → 변경 대상 파일 목록 파싱
→ 미완료 impl들과 교집합 → IMPL_CONFLICT 경고
→ 유저 결정: 무시 / 순서 조정
```

---

### ⬜ S11 — Smart Context 명세화

`build_smart_context()` hot-file 선택 기준 미정의.
장기 프로젝트에서 관련 없는 파일이 50KB를 채우는 문제 예방.

```
우선순위: impl 명시 경로 > git diff HEAD~3 최근 변경 > 나머지
attempt 2+ → prev_attempt_summary + new_error_trace (Context GC)
```

**재검토 트리거**: 에픽 3개+ 프로젝트 시작 시

---

### ⬜ S13 — 에이전트 병목 리포트

`/harness-stats` — 에이전트별 실패율 + 평균 attempt + ESCALATE 유발 패턴.

**재검토 트리거**: 에픽 3개+ 완료 후

---

### ⬜ S14 — 커버리지 게이트 60%

신규 추가 파일 기준 60% 미만 시 `coverage_fail`.
**선행 작업**: `npm install -D @vitest/coverage-v8`

---

### ⬜ S15 — BROWSER:DOM 자동 검증

`(BROWSER:DOM)` 태그 있을 때만 opt-in Playwright 실행.
**선행 작업**: S14 완료

---

### ⬜ S59 — _agent_call stdin pipe 전환

에이전트 프롬프트를 파일 대신 stdin pipe로 전달. 보류 중.

---

### ⬜ M1~M4, L1~L4 — 팀 규모 확장 시 항목

| 항목 | 설명 |
|---|---|
| M1 | 크로스모델 리뷰 (보안 파일 한정, Haiku 2nd opinion) |
| M2 | 커스텀 린트 (sonarjs + import 정렬) |
| M3 | GC 에이전트 (/scan, dead code 리포트) |
| M4 | 관측성 로그 (/tmp 파일 기반) |
| L1 | 커버리지 게이트 전체 파일 70% (S14 전제) |
| L2 | Git Worktree 격리 실행 |
| L3 | 뮤테이션 테스트 (stryker-js) |
| L4 | 크로스모델 리뷰 전체 PR (M1 전제) |
