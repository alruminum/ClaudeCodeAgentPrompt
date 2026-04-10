# 하네스 엔지니어링 백로그

> 최종 업데이트: 2026-04-09 (S73/S74 — Phase C build_loop_context + Phase D review-agent)
> 하네스 수정 시 **첫 번째 단계**로 갱신한다 (백로그 → 수정 → state).

---

## 코드 범례

| 코드 | 의미 | 적용 시점 |
|---|---|---|
| **S** (Solo) | 1인 개발자 기준 | 지금 바로 |
| **M** (Medium) | 팀 3~10인 | 팀 합류 시 |
| **L** (Large) | 팀 10인+ | 규모 확장 시 |
| **BASE** | 전 규모 공통 베이스라인 | 초기 구축 완료 |

---

## 전체 현황

| 코드 | 항목 | 규모 | 상태 |
|---|---|---|---|
| BASE | 결정론적 게이트, 루프 A~E, 플래그 상태머신, 에이전트 경계, 보안 감사, 실패 전략 등 | ALL | ✅ 완료 |
| S1 | 수용 기준 메타데이터 (TEST/BROWSER:DOM/MANUAL 태그) | S | ✅ 완료 |
| S2 | PR body 자동 생성 | S | ✅ 완료 |
| S3 | doc-garden (문서-코드 불일치 리포트) | S | ✅ 완료 |
| S4 | Depth Selector (fast/std/deep) | S | ✅ 완료 |
| S5 | Memory 반자동 기록 (실패 패턴 초안 → 유저 승인) | S | ✅ 완료 |
| S6 | AMBIGUOUS 자동 트리거 (product-planner 힌트 주입) | S | ✅ 완료 |
| S7 | 세션 컨텍스트 브리지 (새 세션 상태 자동 주입) | S | ✅ 완료 |
| S8 | 하네스 smoke test (/harness-test) | S | ✅ 완료 |
| S9 | impl 충돌 감지 (파일 겹침 사전 경고) | S | ⬜ 대기 |
| **S45** | **JSONL 로그 보강 — agent_stats/decision/phase/context/config/rollback/commit 이벤트** | S | ✅ 완료 |
| **S46** | **/harness-review 스킬 — JSONL 파서 + 8개 WASTE 패턴 진단** | S | ✅ 완료 |
| **S47** | **HARNESS_DONE 후 자동 /harness-review 트리거 (정책 10)** | S | ✅ 완료 |
| **S48** | **QA 에이전트 스코프 강화 — 인프라 탐색·Agent·Bash 금지 + agent_active 플래그 세팅** | S | ✅ 완료 |
| **S16** | **~~Router spawn 안전화~~** → Popen 제거, Rate Limiter(5/60s) 유지 | S | ✅ 리팩 |
| **S17** | **~~Gorchera 패턴~~** → JSON Lease 제거, pre-evaluator 유지 | S | ✅ 리팩 |
| **S18** | **Adaptive Interview — AMBIGUOUS → Haiku Q&A → additionalContext 힌트** | S | ✅ 리팩 |
| **S19** | **macOS timeout 호환 (shim) + impl_path 누락 가드** | S | ✅ 완료 |
| **S20** | **Agent Observability: 전 에이전트 실행 로그 + FIFO 10-run 보존** | S | ✅ 완료 |
| **S21** | **하네스 루프 타임스탬프 로깅 (hlog 함수)** | S | ✅ 완료 |
| **S22** | **에이전트 호출별 timeout 강제 + exit 124 감지** | S | ✅ 완료 |
| **S23** | **std 모드 게이트 축소 (5→3단계, deep 분리)** | S | ✅ 완료 |
| **S24** | **grep 파싱 → 라인 전체 매칭 강화** | S | ✅ 완료 |
| **S25** | **BATS 테스트 (하네스 스크립트 자체 테스트) — 69건: utils 23 + flow 22 + impl 14 + executor 10** | S | ✅ 완료 |
| **S26** | **git diff 타이밍 픽스 (pr-reviewer 빈 diff 방지)** | S | ✅ 완료 |
| **S30** | **에이전트별 --max-budget-usd 2.00** | S | ✅ 완료 |
| **S31** | **킬 스위치 (/harness-kill)** | S | ✅ 완료 |
| **S32** | **전체 루프 비용 상한 $10** | S | ✅ 완료 |
| **S27** | **fast_classify() — regex 2단계 즉시 분류** | S | ✅ 완료 |
| **S28** | **_call_haiku() — urllib API 직접 + CLI(socrates) 폴백** | S | ✅ 완료 |
| **S33** | **Stop hook — harness_active 물리적 종료 차단** | S | ✅ 완료 |
| **S34** | **Bash timeout 환경변수 (10분 기본 / 30분 상한)** | S | ✅ 완료 |
| **S35** | **executor 경로 폴백 (프로젝트 → 글로벌)** | S | ✅ 완료 |
| **S39** | **agent out_file 가드 — check_agent_output() 5곳 전수 적용** | S | ✅ 완료 |
| **S40** | **rollback_attempt — 실패 시 git stash로 오염 코드 격리** | S | ✅ 완료 |
| **RF1** | **5f19c2a 복원 리팩토링 — Popen 전면 제거, 라우터=분류+힌트** | S | ✅ 완료 |
| **S49** | **루프 D 라우팅 단순화 — 3타입(FUNCTIONAL_BUG/SPEC_ISSUE/DESIGN_ISSUE), 심각도 제거, QA 이슈 등록 전 경로 의무화** | S | ✅ 완료 |
| **S50** | **harness-review 비정상 종료 진단 — ABNORMAL_END/ROUTING_MISMATCH/MISSING_PHASE/EARLY_EXIT 4개 패턴** | S | ✅ 완료 |
| **S51** | **harness-review 토큰 낭비 진단 — CONTEXT_EXCESS/SPARSE_PROMPT/DUPLICATE_READ 3개 패턴** | S | ✅ 완료 |
| **S52** | **run_end에 result 마커 기록 — EARLY_EXIT 오탐 수정** | S | ✅ 완료 |
| **S53** | **로그 #8/#10 분석 기반 5건 수정 — validator 파싱/test-engineer timeout/engineer Agent 금지/prompt 축소** | S | ✅ 완료 |
| **S54** | **PREFIX 전략 통일 — harness_common.py 공유 모듈 + 4개 훅 HARNESS_PREFIX 하드코딩 제거** | S | ✅ 완료 |
| **S55** | **settings.json 5개 훅 등록 + file-ownership-gate를 agent-boundary에 통합** | S | ✅ 완료 |
| **S56** | **하드코딩 경로 제거 + session-start timeout + HARNESS_RESULT 초기화** | S | ✅ 완료 |
| **S57** | **훅 간섭 테스트 (dry-run + 실제 시나리오)** | S | ✅ 완료 |
| **S58** | **append_failure race condition + grep -F + 변수 인용 + 정책 13 추가** | S | ✅ 완료 |
| **S59** | **_agent_call stdin pipe 전환 (MEDIUM)** | S | ⬜ 보류 |
| **S60** | **에이전트 명세 정교화 4건 — test-engineer/qa/engineer/security-reviewer** | S | ✅ 완료 |
| **S61** | **문서 보완 — README/post-commit-scan 문서화/harness-memory 시드/CLAUDE-base 예시** | S | ✅ 완료 |
| S10 | 납품 게이트 (/deliver, B2B 납품 전 체크) | S | ✅ 완료 |
| S11 | Smart Context 명세화 (hot-file 선택 로직) | S | ⬜ 보류 |
| S12 | 루프 체크포인트 재개 (루프 C/D 상태 감지 + 재진입 스킵) | S | 🔧 진행 |
| **S62** | **스크립트↔룰 동기화 — e32ce43 이후 스크립트 미반영 일괄 수정** | S | 🔧 진행 |
| **S63** | **utils.sh 공용 함수 추출 — parse_marker()/run_plan_validation() + 코드 품질 정비** | S | 🔧 진행 |
| **S64** | **impl-process.sh fast 모드 정정 — validator_b_passed 조건부 설정** (S72로 대체됨) | S | ✅ 완료 |
| **S72** | **커밋 전략 개편 — engineer 즉시 커밋 + pr-reviewer 전 depth 적용 + 머지 조건 통일** | S | ✅ 완료 |
| **S65** | **impl-process.sh SPEC_GAP 핸들링 — spec_gap_count 동결/에스컬레이션 (정책 15)** | S | 🔧 진행 |
| **S66** | **bugfix.sh 라우팅 정비 — backlog/KNOWN_ISSUE 경로 + qa 마일스톤 규칙 정정** | S | 🔧 진행 |
| **S67** | **plan.sh 흐름 완성 — validator DV + Task Decompose/Module Plan + Plan Validation** | S | 🔧 진행 |
| **S68** | **design.sh 흐름 완성 — post-PICK DESIGN_HANDOFF + IMPL_CHK + FLAG 생성** | S | 🔧 진행 |
| **S69** | **스마트 컨텍스트 공용화 + validator diff 패싱** | S | ✅ 완료 |
| **S70** | **훅 전수 감사 — orch-rules-first 패턴 오류, drift-check 매핑 불완전, file-ownership-gate 데드코드 삭제, 테스트 추가** | S | 🔧 진행 |
| **S71** | **디자인 워크플로우 v2 — Pencil MCP 기반 재설계 (designer/design-critic/design.sh/orchestration/design.md 일괄 업데이트, HTML 프리뷰 제거, Figma 모드 제거)** | S | ✅ 완료 |
| **S73** | **Phase C — build_loop_context(loop_type) + design/plan/bugfix 루프 진입 컨텍스트 prepend (8KB 캡)** | S | ✅ 완료 |
| **S74** | **Phase D Step A — review-agent.sh (Haiku 로그 분석) + harness-review-inject.py 훅 + setup-harness.sh 글로벌 훅 등록 로직** | S | ✅ 완료 |
| **S75** | **하네스 출력 현행화 — Phase A/B/C·Mode A/B/C/D/F 레이블 제거, _agent_call 입력 미리보기·토큰·비용 출력, 에이전트 프롬프트 @MODE: 형식 통일** | S | ✅ 완료 |
| **S76** | **에이전트 인프라 탐색 금지 강화 — architect/engineer/validator Universal Preamble에 orchestration-rules.md 등 인프라 파일 Read 금지 명시** | S | ✅ 완료 |
| **S77** | **harness-review INFRA 분류 오탐 수정 — agent-config/ 경로를 INFRA_EXCLUSIONS로 제외 (의도된 프로젝트 컨텍스트 읽기)** | S | ✅ 완료 |
| **S78** | **디자인 루프 2모드 분리 — DEFAULT(1variant, 크리틱 없음, 유저 직접 확인) / CHOICE(3variant, 크리틱 PASS/REJECT, 유저 PICK). designer/design-critic/design.sh/executor.sh/orchestration/design.md/commands/design.md 일괄 업데이트** | S | 🔧 진행 |
| S13 | 에이전트 병목 리포트 (/harness-stats) | S | ⬜ 보류 |
| S14 | 커버리지 게이트 신규파일 60% | S | ⬜ 보류 |
| S15 | BROWSER:DOM 자동 검증 (opt-in Playwright) | S | ⬜ 보류 |
| M1 | 크로스모델 리뷰 (보안 파일 한정, Haiku 2nd opinion) | M | ⬜ 보류 |
| M2 | 커스텀 린트 (sonarjs + import 정렬) | M | ⬜ 보류 |
| M3 | GC 에이전트 (/scan, dead code 리포트) | M | ⬜ 보류 |
| M4 | 관측성 로그 (/tmp 파일 기반) | M | ⬜ 보류 |
| L1 | 커버리지 게이트 전체 파일 70% | L | ⬜ 보류 |
| L2 | Git Worktree 격리 실행 | L | ⬜ 보류 |
| L3 | 뮤테이션 테스트 (stryker-js) | L | ⬜ 보류 |
| L4 | 크로스모델 리뷰 전체 PR | L | ⬜ 보류 |

> **대기**: 즉시 진행 가능 / **보류**: 아래 재검토 트리거 발생 시 진행

---

## 재검토 트리거

| 트리거 | 항목 |
|---|---|
| 즉시 | S7, S8, S9, S10 |
| 장기 프로젝트 (에픽 3개+) 시작 | S11 |
| 세션 중단 손해 경험 | S12 |
| 에픽 3개+ 완료 후 패턴 파악 | S13 |
| test-engineer 품질 반복 하락 | S14 |
| UI 버그 vitest 통과 후 반복 발견 | S15 |
| 팀 합류 또는 보안 사고 | M1 |
| 코드베이스 10파일+ + 중복 반복 | M2 |
| 에픽 5개+ 완료 후 dead code 체감 | M3 |
| 프로덕션 트래픽 발생 | M4 |
| 팀 10인+ + 브랜치 전략 확립 | L1~L4 |

---

## 항목별 상세

### ✅ BASE — 베이스라인

초기 구축 시 완료. 전 규모 공통 적용.

| 기능 | 구현체 |
|---|---|
| 결정론적 게이트 4모드 (impl/design/bugfix/plan) | `harness/executor.sh` |
| 플래그 기반 상태머신 | `/tmp/{prefix}_*` 13개 |
| Ground truth 테스트 (LLM 독립) | `npx vitest run` in `harness/impl-process.sh` |
| 에이전트 도구 경계 물리적 차단 | `agent-boundary.py` |
| 보안 감사 게이트 | `security-reviewer` OWASP+WebView |
| Smart Context 50KB 캡 | `build_smart_context()` |
| 실패 유형별 수정 전략 | `fail_type` 4종 분기 (test/validator/pr/security) |
| 실패 패턴 자동 프로모션 | 3회 누적 → Auto-Promoted Rules |
| 단일 소스 원칙 물리적 강제 | `orch-rules-first.py` |
| 의도 분류 라우터 | regex + LLM 하이브리드 (`harness-router.py`) |
| 루프 A~E 5종 | `orchestration-rules.md` + `harness/executor.sh` |

---

### ✅ S1 — 수용 기준 메타데이터

impl 파일에 검증 방법 태그 필수화. "무엇을 어떻게 검증할지" 명확화.

- `(TEST)` — vitest 자동 테스트
- `(BROWSER:DOM)` — Playwright DOM 쿼리
- `(MANUAL)` — curl/bash 수동 (자동화 불가 시만)

validator Plan Validation에서 태그 없는 항목 → `PLAN_VALIDATION_FAIL`.

**변경**: `architect.md`, `validator.md`, `orchestration-rules.md`

---

### ✅ S2 — PR body 자동 생성

HARNESS_DONE 후 `/tmp/{p}_pr_body.txt` 자동 생성.
What/Why + 테스트 결과 + 위험도 + 리뷰 포커스 포함.

**변경**: `harness/impl-process.sh` (`generate_pr_body()`)

---

### ✅ S3 — doc-garden

`/doc-garden` 커맨드. docs/**와 src/**를 비교해 불일치 리포트 출력.
자동 수정 없음 — 리포트만.

**변경**: `commands/doc-garden.md`

---

### ✅ S4 — Depth Selector

모든 작업이 동일 루프 깊이를 타던 것을 3단계로 분리.

| depth | 실행 단계 | 자동 선택 조건 |
|---|---|---|
| `fast` | engineer → commit | impl에 `(MANUAL)` 태그만 있을 때 |
| `std` | 전체 루프 (기본값) | 일반 구현 |
| `deep` | std + S14·S15 (미구현 stub) | impl에 `(BROWSER:DOM)` 있을 때 |

**변경**: `harness/executor.sh` (`detect_depth()`), `harness/impl-process.sh` (fast 분기)

---

### ✅ S5 — Memory 반자동 기록

루프 FAIL 시 `/tmp/{p}_memory_candidate.md`에 실패 패턴 초안 자동 작성.
HARNESS_DONE 후 메인 Claude가 "기록할까요?" 제안 → 유저 Y/N.

**변경**: `harness/impl-process.sh` (`append_failure()` + HARNESS_DONE 출력)

---

### ✅ S6 — AMBIGUOUS 자동 트리거

모호한 요청이 루프로 진입하는 것을 차단.
AMBIGUOUS + 진행 중 워크플로우 없음 → product-planner 힌트 주입.

- 구현 수준 모호 → 파일/동작 명확화 요청
- PRD 수준 모호 → product-planner 호출 안내

**변경**: `hooks/harness-router.py`

---

### ✅ S7 — 세션 컨텍스트 브리지

새 세션마다 "기존꺼 파악하라"는 지시에 드는 토큰 비용 제거.
SessionStart 훅에서 현재 상태를 자동 압축해 주입.

```
SessionStart → harness.config.json 확인
→ /tmp/{p}_current_issue + backlog 진행중 항목 읽기
→ "프로젝트: {name} | 진행 중: #{issue}" hookSpecificOutput 주입
```

**변경**: `hooks/harness-session-start.py`

---

### ✅ S8 — 하네스 smoke test

하네스 수정 후 루프가 깨졌는지 확인하는 방법이 없음.
fixture impl로 플래그 흐름만 dry-run.

```
/harness-test → fixture impl 로드
→ 각 게이트 플래그 순서 검증 (실제 에이전트 호출 없음)
→ SMOKE_PASS / SMOKE_FAIL
```

**변경**: `commands/harness-test.md` (신규)

---

### ✅ S16 — ~~Router spawn 안전화~~ → Popen 제거, Rate Limiter 유지

**배경**: S16 구현(980ca48)이 Popen 백그라운드 spawn + lock 없음으로 무한 좀비 루프 → 1분 만에 $100 소진.
**결과**: RF1 리팩토링에서 Popen/Atomic Lock/TTL/heartbeat 전면 제거. 라우터=분류+힌트 원칙으로 복원.

**잔존 기능**: Rate Limiter(5회/60초) — 훅 자체의 중복 실행 방어용으로 유지.

**변경 파일**: `hooks/harness-router.py`

---

### ✅ S17 — ~~Gorchera 패턴~~ → JSON Lease 제거, pre-evaluator 유지

**배경**: Gorchera 분석에서 발견한 패턴 중 JSON Lease는 Popen 전제 → RF1에서 제거.

**잔존 기능**: pre-evaluator automated_checks (has_changes/no_new_deps/file_unchanged) — `harness/impl-process.sh`에서 유지.

**변경 파일**: `harness/impl-process.sh`

---

### ✅ S18 — Adaptive Interview (additionalContext 방식)

**배경**: AMBIGUOUS 요청이 루프로 직행하던 것을 Haiku Q&A로 명확화 후 진입.
**RF1 변경**: Popen spawn 제거 → additionalContext로 질문/힌트 주입. 메인 Claude가 질문 전달.

**구현 내용**:
- `_run_interview_turn()` — Haiku로 다음 질문 생성, DONE이면 None 반환
- `/tmp/{p}_interview_state.json` — 인터뷰 상태 관리 (history, current_q, original, turn)
- max_turn=4 하드캡 — 4턴 초과 시 자동 완료
- 완료 시 product-planner 호출 힌트 주입

**변경 파일**: `hooks/harness-router.py`

---

### ✅ S20 — Agent Observability: 전 에이전트 실행 로그 + FIFO 10-run 보존

**배경**: 하네스 루프 안에서 에이전트가 무엇을 하는지 실행 중에 볼 방법이 없었다.
`tail -f`로 실시간 확인 + 실행 후 분석용 JSONL 아카이브 필요.

**구현 내용**:
- `harness/utils.sh` 신규 — `rotate_harness_logs()` + `write_run_end()` + `_agent_call()` 공용 유틸
- `_agent_call()`: `--output-format stream-json --include-partial-messages` → `tee`로 JSONL 실시간 기록 + `python3`으로 result 텍스트 추출
- FIFO 로테이션: prefix별 최신 10개 유지 (`ls -t | tail -n +10 | xargs rm`)
- 모든 에이전트(architect/engineer/validator/test-engineer/pr-reviewer/security-reviewer/designer/design-critic/qa/product-planner) 대상

**로그 위치**: `~/.claude/harness-logs/{prefix}/run_YYYYMMDD_HHmmss.jsonl`

**실시간 확인**:
```bash
tail -f ~/.claude/harness-logs/mb/$(ls -t ~/.claude/harness-logs/mb/ | head -1)
```

**per-agent timeout**: architect/engineer=900s, validator/test-engineer/designer/design-critic/qa/product-planner=300s, pr-reviewer/security-reviewer=180s

**변경 파일**: `harness/utils.sh` (신규), `harness/executor.sh`, `harness/impl-process.sh`

---

### ⬜ S9 — impl 충돌 감지

동일 파일을 수정하는 impl이 여러 개 동시에 존재할 때 사전 경고.
"이거 하나 고치면 기존게 안되고" 문제 예방.

```
impl 진입 시 → 변경 대상 파일 목록 파싱
→ 미완료 impl들과 교집합 → IMPL_CONFLICT 경고
→ 유저 결정: 무시 / 순서 조정
```

**변경**: `harness/executor.sh` + `architect.md` (변경 파일 목록 섹션 필수화)

---

### ✅ S10 — 납품 게이트

B2B 납품 전 "클라이언트에게 줘도 되는가" 자동 체크.
security-reviewer와 다른 기준 — 실수 방지용.

```
/deliver
→ .env 패턴 src/** 노출 스캔
→ console.log / debugger 잔존 스캔
→ 하드코딩 URL·키 스캔
→ npm run build 성공 여부
→ DELIVERY_READY / DELIVERY_BLOCKED
```

**변경**: `commands/deliver.md` (신규)

---

### ⬜ S11 — Smart Context 명세화

`build_smart_context()` hot-file 선택 기준 미정의.
장기 프로젝트에서 관련 없는 파일이 50KB를 채우는 문제 예방.

```
우선순위: impl 명시 경로 > git diff HEAD~3 최근 변경 > 나머지
GC: 3회 초과 시 이전 attempt 에러 트레이스만 carry-forward
```

**S11 확장 — attempt 간 Context GC** (GAP-1):
현재 attempt 0: impl 전체, attempt 1+: error 관련 파일 로드.
3회 재시도 시 attempt 1→2→3 사이에 공통 컨텍스트 중복 낭비 발생.
목표: 이전 attempt들의 공통 컨텍스트를 요약하고, 에러 트레이스 + 변경된 파일만 carry-forward.

```
attempt 0 → context = impl + 관련 파일 전체 (기존 로직)
attempt 1 → context = error_trace + 실패 파일 (기존 로직)
attempt 2 → context = prev_attempt_summary + new_error_trace  ← 신규
             (prev 컨텍스트를 1줄 요약으로 압축)
```

**재검토 트리거**: 에픽 3개+ 프로젝트 시작 시
**변경**: `harness/impl-process.sh` (`build_smart_context()`)

---

### ✅ S12 — 루프 C/D 상태 감지 + 재진입

**배경**: 루프 중단 후 재진입 시 처음부터 재시작하는 비용 제거. JSON 체크포인트 대신 기존 시그널(impl 파일, GitHub issue, 플래그)을 활용한 경량 감지.

**루프 D (bugfix) 재진입**:
1. impl 파일 존재 → QA + architect 스킵 → engineer 직접
2. GitHub issue에 QA 리포트 → QA 스킵 → architect부터
3. 둘 다 없음 → QA부터 (기본)

**루프 C (impl) 재진입**:
1. `plan_validation_passed` 플래그 + impl 존재 → engineer 루프로 직접 진입
2. impl 존재 → architect 스킵 → validator Plan Validation
3. 둘 다 없음 → architect부터 (기본 — Phase 0.7이 이미 처리)

**`_run_bugfix_direct()` 개선**:
- impl 파일이 이미 있으면 architect Mode F 스킵

**변경 파일**: `orchestration-rules.md`, `harness/executor.sh`

---

### ⬜ S13 — 에이전트 병목 리포트

`{prefix}-agent-calls.log` 분석. 어느 에이전트가 병목인지 파악.

```
/harness-stats → 에이전트별 실패율 + 평균 attempt
→ ESCALATE 유발 impl 패턴 → 리포트 출력 (수정 없음)
```

**재검토 트리거**: 에픽 3개+ 완료 후
**변경**: `commands/harness-stats.md` (신규)

---

### ⬜ S14 — 커버리지 게이트 60%

신규 추가 파일 기준 60% 미만 시 `coverage_fail`.
기존 파일은 게이트 제외 (레거시 분리).

**재검토 트리거**: test-engineer 품질 반복 하락 시
**선행 작업**: `npm install -D @vitest/coverage-v8`
**변경**: `harness/impl-process.sh`

---

### ⬜ S15 — BROWSER:DOM 자동 검증

`(BROWSER:DOM)` 태그 있을 때만 opt-in으로 Playwright 실행.
루프마다 dev server + Playwright = 30~60초 추가이므로 기본 비활성.

**재검토 트리거**: UI 버그가 vitest 통과 후 반복 발견 시
**선행 작업**: S14 완료
**변경**: `harness/impl-process.sh`

---

### ⬜ M1 — 크로스모델 리뷰 (보안 파일 한정)

auth/api/db 파일 변경 시 Haiku로 세컨드 오피니언.
전체 PR 적용은 토큰 과다 → 보안 파일만.

**재검토 트리거**: 팀 합류 또는 보안 사고
**변경**: `harness/impl-process.sh`

---

### ⬜ M2 — 커스텀 린트

코드베이스 10파일+ 이상에서 중복 로직 반복 시 pr-reviewer 부담 감소.
eslint-plugin-sonarjs + import 정렬 규칙.

**재검토 트리거**: 코드베이스 10파일+ + 중복 로직 반복
**변경**: `.eslintrc`, `harness/impl-process.sh`

---

### ⬜ M3 — GC 에이전트

에픽 5개+ 후 dead code 누적 시 jscpd·knip으로 자동 감지.
리포트만, 자동 PR 없음.

**재검토 트리거**: 에픽 5개+ 완료 후 dead code 체감
**변경**: `commands/scan.md` (신규)

---

### ⬜ M4 — 관측성 로그

프로덕션 트래픽 발생 후 버그 재현이 어려워질 때.
`/tmp/{p}_observability/` 파일 로그. Web UI 없음.

**재검토 트리거**: 프로덕션 트래픽 발생
**변경**: `harness/impl-process.sh`

---

### ⬜ L1 — 커버리지 게이트 전체 70%

S14(신규 파일 60%) → 전체 파일 70%로 기준 상향.

**전제**: S14 완료
**변경**: `harness/impl-process.sh`

---

### ⬜ L2 — Git Worktree 격리

팀 병렬 개발 시 브랜치 충돌 방지.
각 루프를 별도 worktree에서 실행, 성공 시만 메인 병합.

**전제**: feature branch 전략 확립
**변경**: `harness/executor.sh`, `harness/impl-process.sh`

---

### ⬜ L3 — 뮤테이션 테스트

테스트가 통과해도 실제로 버그를 잡는지 검증 (stryker-js).

**재검토 트리거**: 테스트 신뢰도 문제 반복 + 토큰 예산 여유
**변경**: `harness/impl-process.sh`

---

### ⬜ L4 — 크로스모델 리뷰 전체 PR

M1(보안 파일 한정) → 전체 PR로 확장.

**전제**: M1 완료 + 토큰 예산 충분
**변경**: `harness/impl-process.sh`

---

### ✅ S21 — 하네스 루프 타임스탬프 로깅 (hlog 함수)

**배경**: 하네스 루프 진입 후 어디서 멈추는지 알 수 없었다. `agent-calls.log`만으로는 부족.

**구현 내용**:
- `harness/impl-process.sh` 상단에 `HLOG`/`hlog()` 함수 정의
- `HLOG="/tmp/${PREFIX}-harness-debug.log"`, `hlog()` = `[HH:MM:SS] [attempt=N] 메시지`
- 루프 시작/종료, 에이전트 전후, vitest 전후에 hlog 추가
- `ATTEMPT` 전역 변수 루프 반복마다 갱신

**실시간 모니터링**: `tail -f /tmp/${PREFIX}-harness-debug.log`

**변경**: `harness/impl-process.sh`

---

### ✅ S22 — 에이전트 호출별 timeout 강제 + exit 124 감지

**배경**: `_agent_call`이 `|| true`로 exit code를 먹어버려 hang 발생 시 어디서 멈추는지 알 수 없었다.

**구현 내용**:
- `harness/utils.sh`: `|| true` → `|| _call_exit=$?` 교체, `return $_call_exit` 추가
- `agent_end` JSONL 이벤트에 `exit` 필드 추가
- `harness/impl-process.sh`: 모든 `_agent_call` 호출에 `|| AGENT_EXIT=$?` 추가
- exit 124(timeout) 감지 시 `hlog "⏰ ${AGENT} timeout — skip"` 기록

**변경**: `harness/utils.sh`, `harness/impl-process.sh`

---

### ✅ S23 — std 모드 게이트 축소 (5→3단계, deep 분리)

**배경**: std에서 LLM 에이전트를 5회 호출해 이슈당 10~20분 소요. pr-reviewer·security-reviewer는 일상 작업에서 과도함.

**구현 내용**:
- `fast`: engineer → commit (LLM 1회)
- `std`: engineer → test-engineer → vitest → validator → commit (LLM 3회)
- `deep`: engineer → test-engineer → vitest → validator → pr-reviewer → security-reviewer → commit (LLM 5회)
- std/fast에서 `pr_reviewer_lgtm`, `security_review_passed` 플래그 자동 touch
- `orchestration-rules.md` depth 테이블 + 루프 C 다이어그램 동기화
- "deep = std 미구현" 라인 제거

**변경**: `harness/impl-process.sh`, `orchestration-rules.md`

---

### ✅ S24 — grep 파싱 → 라인 전체 매칭 강화

**배경**: `grep -oE "PASS|FAIL"` 패턴이 설명 텍스트에 포함된 키워드도 매칭해 오탐 가능.

**구현 내용**:
- validator: `grep -oE '\bPASS\b|\bFAIL\b'` → `grep -qE "^PASS$"` / `^FAIL$`
- pr-reviewer: `grep -oE 'LGTM|CHANGES_REQUESTED'` → `^LGTM$` / `^CHANGES_REQUESTED$`
- security-reviewer: `grep -oE 'SECURE|VULNERABILITIES_FOUND'` → `^SECURE$` / `^VULNERABILITIES_FOUND$`
- UNKNOWN 케이스: `echo ⚠️` + FAIL 동일 처리 (`!= PASS` 조건으로 통일)
- UNKNOWN 시 error_trace fallback: `tail -6`

**변경**: `harness/impl-process.sh`

---

### ⬜ S25 — BATS 테스트 (하네스 스크립트 자체 테스트)

**배경**: `harness/impl-process.sh`·`harness/executor.sh` 핵심 함수를 수동으로만 검증 중. 회귀 방지 필요.

**구현 대상**:
- `detect_depth()` — impl 파일 태그별 fast/std/deep 자동 선택
- `build_smart_context()` — attempt 0 vs N 컨텍스트 분기
- grep 파싱 함수 — `^마커$` 패턴 PASS/FAIL/UNKNOWN 분기

**도구**: [BATS](https://github.com/bats-core/bats-core) (Bash Automated Testing System)
**변경**: `tests/harness.bats` (신규)

---

### ✅ S26 — git diff 타이밍 픽스 (pr-reviewer 빈 diff 방지)

**배경**: pr-reviewer에 diff를 전달하기 전 `git add`가 선행되지 않아 staged 변경이 diff에 포함되지 않는 경우 발생.

**구현 내용**:
- pr-reviewer 호출 직전 `git add -A` 실행 (또는 `git diff HEAD` 대신 `git diff --cached HEAD` 검토)
- deep 모드에서만 해당 (std에서는 pr-reviewer 스킵)

**변경**: `harness/impl-process.sh`

---

### ✅ S30 — 에이전트별 --max-budget-usd 2.00

**배경**: 개별 에이전트가 폭주해 비용이 무제한 증가하는 경우 방지.

**구현 내용**:
- `harness/utils.sh` `_agent_call()` claude 호출에 `--max-budget-usd 2.00` 추가
- 모든 에이전트(engineer/test-engineer/validator/pr-reviewer/security-reviewer 등) 일괄 적용

**변경**: `harness/utils.sh`

---

### ✅ S31 — 킬 스위치

**배경**: 루프가 폭주하거나 잘못된 방향으로 진행 시 즉시 중단할 방법이 없었다.

**구현 내용**:
- `harness/impl-process.sh` `kill_check()` 함수 — `/tmp/{PREFIX}_harness_kill` 파일 존재 시 즉시 `HARNESS_KILLED` 출력 후 exit 0
- 삽입 위치: while 루프 상단 + 각 에이전트 호출 직전(engineer×2, test-engineer, vitest, validator, pr-reviewer, security-reviewer)
- `harness/executor.sh` EXIT trap에 kill 파일 정리 추가
- `commands/harness-kill.md` 신규 — `/harness-kill` 커맨드

**사용법**: `touch /tmp/{PREFIX}_harness_kill`

**변경**: `harness/impl-process.sh`, `harness/executor.sh`, `commands/harness-kill.md` (신규)

---

### ✅ S32 — 전체 루프 비용 상한 $10

**배경**: 루프 전체 비용이 누적돼 예산을 초과하는 경우 방지.

**구현 내용**:
- `harness/utils.sh` Python parser에서 result 이벤트 `total_cost_usd` 추출 → `{out_file}_cost.txt` 기록
- `harness/impl-process.sh` `budget_check()` 함수 — 에이전트별 비용 누적 → $10 초과 시 `HARNESS_BUDGET_EXCEEDED` 출력 후 exit 1
- `hlog`에 에이전트별·누적 비용 기록 (`💰 ${agent} 비용: $X | 누적: $Y/10`)
- agent_end JSONL 이벤트에 `cost_usd` 필드 추가

**변경**: `harness/utils.sh`, `harness/impl-process.sh`

---

### ✅ S27 — fast_classify() regex 2단계 즉시 분류

**배경**: 모든 프롬프트가 Haiku LLM을 거쳐 분류 지연 발생.

**구현 내용**:
- GREETING: 짧은 반응어 완전 일치 (`ㅇㅇ`, `응`, `ok`, `ㅋ+` 등)
- QUESTION: `?`로 끝나면 무조건
- BUG: 버그 키워드 있되 구현 동사 없는 경우만
- IMPLEMENTATION: 이슈번호 + 명령형 동사 조합
- 미분류 → LLM 폴백 (extract_intent)

**변경 파일**: `hooks/harness-router.py`

---

### ✅ S28 — _call_haiku() urllib API 직접 + CLI 폴백

**배경**: CLI `claude -p` 호출이 느리고 타임아웃 발생 빈번.

**구현 내용**:
- urllib.request로 Anthropic API 직접 호출 (timeout=5s)
- API 키 없거나 실패 시 `claude --agent socrates` CLI 폴백 (timeout=10s)
- HARNESS_INTERNAL=1 env로 재귀 방지

**변경 파일**: `hooks/harness-router.py`, `agents/socrates.md`

---

### ✅ S33 — Stop hook (harness_active 물리적 종료 차단)

**배경**: 하네스 실행 중 Claude가 조기 종료 선언하면 루프가 중단됨.

**구현 내용**:
- `hooks/harness-stop-gate.sh` — Stop hook에서 `/tmp/{p}_harness_active` 체크
- 존재 시 exit 2 → 종료 차단, kill switch 활성 시 즉시 허용
- `settings.json` Stop hook: gate → afplay 순서 등록

**변경 파일**: `hooks/harness-stop-gate.sh` (신규), `settings.json`

---

### ✅ RF1 — 5f19c2a 복원 리팩토링

**배경**: 980ca48(S16 Popen 도입) 이후 구조가 복잡해져 유지보수 불가.

**핵심 원칙**: 라우터=분류+힌트 주입, Claude=판단+실행. Popen 전면 제거.

**변경 내용**:
- `hooks/harness-router.py` — 5f19c2a 베이스로 복원 + S27/S28/S18/S16(Rate Limiter)/S30(Kill Switch) 선별 병합
- `orchestration-rules.md` — 정책4 복원(Popen→포어그라운드), AMBIGUOUS→Adaptive Interview, 정책10 추가
- `hooks/harness-stop-gate.sh` + `settings.json` — Stop hook 신규

**제거된 것**: Popen spawn, Atomic Lock, JSON Lease, heartbeat, try_spawn_harness(), run_harness(), get_harness_sh()

**변경 파일**: `hooks/harness-router.py`, `orchestration-rules.md`, `hooks/harness-stop-gate.sh`, `settings.json`

---

### ✅ S34 — Bash timeout 환경변수

**배경**: Claude Code 내부 Bash 기본 timeout 2분. 하네스 루프에서 engineer가 2분 넘기면 강제 종료.

**구현 내용**:
- `~/.claude/settings.json` 최상위 `env` 키 추가
- `BASH_DEFAULT_TIMEOUT_MS=600000` (10분 기본)
- `BASH_MAX_TIMEOUT_MS=1800000` (30분 상한)

**변경 파일**: `settings.json`

---

### ✅ S35 — executor 경로 폴백

**배경**: 프로젝트 `.claude/harness/executor.sh`가 없으면 `bash: No such file or directory` 에러.

**구현 내용**:
- `harness-router.py`에서 executor 경로 자동 감지
- 프로젝트 `.claude/harness/executor.sh` 먼저, 없으면 `~/.claude/harness/executor.sh` 폴백
- 디렉티브 3곳 모두 동적 경로 사용

**변경 파일**: `hooks/harness-router.py`

---

### ✅ S39 — agent out_file 가드

**배경**: `_agent_call`이 출력 없이 실패하면 out_file 미생성 → `cat`에서 `set -e` 크래시.

**구현 내용**:
- `check_agent_output()` 헬퍼 — 파일 미존재 또는 비어있으면 return 1
- 5곳 전수 적용: engineer → test-engineer → validator → pr-reviewer → security-reviewer
- 실패 시 graceful retry (append_failure → rollback_attempt → continue)
- `harness/utils.sh` `_agent_call`에서 out_file 사전 touch (이중 보호)

**변경 파일**: `harness/impl-process.sh`, `harness/utils.sh`

---

### ✅ S50 — harness-review 비정상 종료 진단

**배경**: harness-review가 WASTE 패턴(낭비)만 보고, "왜 끊겼는지"는 진단하지 않았다. 비정상 종료나 조기 exit 시 원인 추적 불가.

**변경 내용**:
- 4개 흐름 진단 패턴 추가:
  - `ABNORMAL_END` — run_end 없거나 incomplete agent 존재
  - `EARLY_EXIT` — run_end 있지만 HARNESS_DONE/ESCALATE 마커 없음
  - `MISSING_PHASE` — orchestration-rules 예상 단계 대비 누락
  - `ROUTING_MISMATCH` — QA 출력 타입과 실제 다음 agent 불일치
- 모드별 예상 에이전트 순서(`EXPECTED_SEQUENCE`) 정의
- QA 출력에서 타입 분류 자동 추출(`_extract_qa_type`)
- 에이전트별 중단 원인 힌트(`_diagnose_abort`)

**변경 파일**: `scripts/harness-review.py`

---

### ✅ S49 — 루프 D 라우팅 단순화

**배경**: 루프 D의 qa 라우팅이 6타입×심각도 조합으로 복잡. FUNCTIONAL_BUG LOW가 backlog로 빠져 유저 의도 무시. QA가 이슈 등록 안 하는 책임 공백.

**변경 내용**:
- 6타입(FUNCTIONAL_BUG/SPEC_VIOLATION/REGRESSION/INTEGRATION_ISSUE/DESIGN_ISSUE/ARCH_ISSUE) → 3타입(FUNCTIONAL_BUG/SPEC_ISSUE/DESIGN_ISSUE) 통합
- 심각도(CRITICAL/HIGH/MEDIUM/LOW) 제거 — 경로 분기에 불필요
- QA가 **모든 경로에서** 이슈 등록 의무화:
  - FUNCTIONAL_BUG → Bugs 마일스톤
  - SPEC_ISSUE (PRD 명세 있음) → Feature 마일스톤 + epic 라벨
  - SPEC_ISSUE (PRD 명세 없음) → Feature 마일스톤
  - DESIGN_ISSUE → Feature 마일스톤
- executor backlog 분기 제거 → FUNCTIONAL_BUG도 engineer 직접 경로

**변경 파일**: `orchestration-rules.md`, `harness/executor.sh`, `agents/qa.md`

---

### ✅ S40 — rollback_attempt (실패 시 git stash 격리)

**배경**: 실패한 attempt의 변경사항이 다음 attempt에 오염.

**구현 내용**:
- `rollback_attempt()` 헬퍼 — `git stash push --include-untracked -m "harness-failed-attempt-N"`
- 5곳 실패 분기(autocheck/test/validator/pr/security) continue 직전에 호출
- 스태시는 `git stash list`로 확인/복구 가능

**변경 파일**: `harness/impl-process.sh`

---

### ✅ S72 — git checkout stdout 오염 + QA 타임아웃 수정

**배경**: run_20260409_163231에서 `MERGE_CONFLICT_ESCALATE` 발생. 브랜치명이 `MCLAUDE.mdfix/91-fix-freeze`로 오염.
분석 결과 두 가지 버그 발견:

**버그 1 — git checkout stdout 오염 (utils.sh)**
- `create_feature_branch`에서 브랜치가 이미 존재할 때 `git checkout "$branch_name"` 실행
- 수정된 추적 파일(CLAUDE.md, docs/test-plan.md)이 있으면 git이 수정 파일 목록을 stdout으로 출력
- `FEATURE_BRANCH=$(create_feature_branch ...)` 가 오염된 문자열 캡처 → 브랜치명 깨짐
- 수정: `git checkout` 명령에 `>/dev/null 2>&1` 추가

**버그 2 — QA 300s 타임아웃 (bugfix.sh)**
- QA 에이전트가 6개 파일 읽음 (Glob 1 + Read 6) → 토큰 처리+생성 시간 초과
- 300s 제한이 너무 빡빡함 (architect는 600s)
- 수정: QA timeout 300 → 600

**변경 파일**: `harness/utils.sh`, `harness/bugfix.sh`
