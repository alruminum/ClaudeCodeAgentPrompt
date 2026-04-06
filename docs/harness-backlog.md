# 하네스 엔지니어링 백로그

> 최종 업데이트: 2026-04-06
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
| **S16** | **Router spawn 안전화 — Atomic Lock + TTL (좀비 방지)** | S | ✅ 완료 |
| **S17** | **Gorchera 패턴 — Lease Heartbeat + automated_checks** | S | ✅ 완료 |
| **S18** | **Temperature=0 결정론적 실행 (CLI 지원 여부 선행 확인)** | S | ⬜ 대기 |
| S10 | 납품 게이트 (/deliver, B2B 납품 전 체크) | S | ✅ 완료 |
| S11 | Smart Context 명세화 (hot-file 선택 로직) | S | ⬜ 보류 |
| S12 | 루프 체크포인트 재개 (세션 중단 후 이어받기) | S | ⬜ 보류 |
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
| 결정론적 게이트 5모드 (impl/impl2/design/bugfix/plan) | `harness-executor.sh` |
| 플래그 기반 상태머신 | `/tmp/{prefix}_*` 13개 |
| Ground truth 테스트 (LLM 독립) | `npx vitest run` in `harness-loop.sh` |
| 에이전트 도구 경계 물리적 차단 | `agent-boundary.py` |
| 보안 감사 게이트 | `security-reviewer` OWASP+WebView |
| Smart Context 50KB 캡 | `build_smart_context()` |
| 실패 유형별 수정 전략 | `fail_type` 4종 분기 (test/validator/pr/security) |
| 실패 패턴 자동 프로모션 | 3회 누적 → Auto-Promoted Rules |
| 단일 소스 원칙 물리적 강제 | `orch-rules-first.py` |
| 의도 분류 라우터 | regex + LLM 하이브리드 (`harness-router.py`) |
| 루프 A~E 5종 | `orchestration-rules.md` + `harness-executor.sh` |

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

**변경**: `harness-loop.sh` (`generate_pr_body()`)

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

**변경**: `harness-executor.sh` (`detect_depth()`), `harness-loop.sh` (fast 분기)

---

### ✅ S5 — Memory 반자동 기록

루프 FAIL 시 `/tmp/{p}_memory_candidate.md`에 실패 패턴 초안 자동 작성.
HARNESS_DONE 후 메인 Claude가 "기록할까요?" 제안 → 유저 Y/N.

**변경**: `harness-loop.sh` (`append_failure()` + HARNESS_DONE 출력)

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

### 🔥 S16 — Router spawn 안전화 (Atomic Lock + TTL)

**배경**: S16 구현(980ca48)이 Popen 백그라운드 spawn + lock 없음으로 무한 좀비 루프 → 1분 만에 $100 소진.  
**방향**: 직접 spawn 방식 유지 (LLM 우회 목적 정당), 구현만 안전하게 교체.

**Phase 1 변경 내용:**

```
harness-router.py
  - try_spawn_harness() 추가
    - TTL 체크: lock 파일 mtime 기준 120초 초과 → stale → 삭제
    - Atomic create: os.O_CREAT | os.O_EXCL (race condition 방지)
    - FileExistsError → spawn 금지 (중복 차단)
    - BUG/PLANNING 분기에도 active 체크 추가 (S16 버그 수정)

harness-executor.sh
  - 모든 mode 진입 시 즉시 lock 갱신
  - heartbeat 백그라운드 (15초마다 touch → mtime 갱신)
  - EXIT trap: heartbeat kill + lock 삭제 (성공/실패/크래시 모두)
```

**수용 기준**: 동시 2개 UserPromptSubmit 발생 시 1개만 spawn. 크래시 후 2분 내 재spawn 불가, 2분 후 가능.

**변경 파일**: `hooks/harness-router.py`, `harness-executor.sh`

---

### ⬜ S17 — Gorchera 패턴 적용 (Lease Heartbeat + automated_checks)

**배경**: Gorchera(knewstimek/gorchera) 분석에서 발견한 운영 안정성 패턴 3개.  
**선행**: S16 완료 후 진행.

**Phase 2 변경 내용:**

```
1. Lease 파일 고도화 (S16 단순 touch → JSON lease)
   /tmp/{prefix}_harness_active.json
   { "pid": 1234, "mode": "bugfix", "started": 1712345678, "heartbeat": 1712345693 }
   → router가 heartbeat 필드로 stale 판단 (touch mtime보다 명시적)

2. pre-evaluator automated_checks (LLM 호출 전 sh 사전 검사)
   harness-executor.sh impl 모드에 추가:
   - file_exists: 생성 예정 파일 실제 존재 확인
   - no_new_deps: package.json 의존성 추가 여부 감지
   - file_unchanged: 변경 금지 파일 수정 여부 확인
   → 실패 시 validator 호출 없이 즉시 FAIL (토큰 절약)

3. estimateTokenCount 한국어 보정 (선택)
   Gorchera의 char/4 추정이 CJK에서 4배 낮게 나오는 문제
   → 우리 시스템에선 직접적 영향 없지만, 비용 추정 기능 추가 시 참고
```

**수용 기준**: pre-evaluator 체크에서 잡힌 오류가 validator 에이전트 호출 없이 FAIL 처리됨.

**변경 파일**: `hooks/harness-router.py`, `harness-executor.sh`

---

### ⬜ S18 — Temperature=0 결정론적 실행

**배경**: 수도코드 분석에서 발견. `callIsolatedLLMWorker`에서 `temperature: 0.0` 명시.
validator/security-reviewer처럼 PASS/FAIL 판정이 중요한 역할은 온도 0이 일관된 결과를 보장.

**선행 확인 필요**: `claude --agent --print` CLI가 temperature 파라미터를 지원하는지 확인.
```bash
# 확인 방법
claude --help | grep -i temp
claude --agent validator --print --temperature 0 -p "test" 2>&1 | head -5
```

**지원 시 적용 대상**:
| 에이전트 | 이유 |
|---|---|
| validator | PASS/FAIL 판정 — 동일 input에 동일 output 필수 |
| security-reviewer | VULNERABILITIES_FOUND/SECURE — 판정 일관성 필수 |
| design-critic | PICK/ITERATE/ESCALATE — 판정 일관성 권장 |
| pr-reviewer | LGTM/CHANGES_REQUESTED — 판정 일관성 권장 |

engineer/designer는 창의성 필요 → temperature 유지.

**미지원 시**: 항목 WONTFIX 처리.

**변경**: `harness-executor.sh`, `harness-loop.sh` (claude --agent 호출에 `--temperature 0` 추가)

---

### ⬜ S9 — impl 충돌 감지

동일 파일을 수정하는 impl이 여러 개 동시에 존재할 때 사전 경고.
"이거 하나 고치면 기존게 안되고" 문제 예방.

```
impl 진입 시 → 변경 대상 파일 목록 파싱
→ 미완료 impl들과 교집합 → IMPL_CONFLICT 경고
→ 유저 결정: 무시 / 순서 조정
```

**변경**: `harness-executor.sh` + `architect.md` (변경 파일 목록 섹션 필수화)

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
**변경**: `harness-loop.sh` (`build_smart_context()`)

---

### ⬜ S12 — 루프 체크포인트 재개

세션 만료로 루프 중단 시 처음부터 재시작하는 비용 제거.

```json
/tmp/{p}_loop_state.json
{ "attempt": 2, "last_stage": "test-engineer", "fail_type": "validator_fail" }
→ 세션 재시작 시 해당 stage부터 재개
```

**재검토 트리거**: 세션 중단으로 실제 손해 경험 시
**변경**: `harness-executor.sh`, `harness-loop.sh`

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
**변경**: `harness-loop.sh`

---

### ⬜ S15 — BROWSER:DOM 자동 검증

`(BROWSER:DOM)` 태그 있을 때만 opt-in으로 Playwright 실행.
루프마다 dev server + Playwright = 30~60초 추가이므로 기본 비활성.

**재검토 트리거**: UI 버그가 vitest 통과 후 반복 발견 시
**선행 작업**: S14 완료
**변경**: `harness-loop.sh`

---

### ⬜ M1 — 크로스모델 리뷰 (보안 파일 한정)

auth/api/db 파일 변경 시 Haiku로 세컨드 오피니언.
전체 PR 적용은 토큰 과다 → 보안 파일만.

**재검토 트리거**: 팀 합류 또는 보안 사고
**변경**: `harness-loop.sh`

---

### ⬜ M2 — 커스텀 린트

코드베이스 10파일+ 이상에서 중복 로직 반복 시 pr-reviewer 부담 감소.
eslint-plugin-sonarjs + import 정렬 규칙.

**재검토 트리거**: 코드베이스 10파일+ + 중복 로직 반복
**변경**: `.eslintrc`, `harness-loop.sh`

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
**변경**: `harness-loop.sh`

---

### ⬜ L1 — 커버리지 게이트 전체 70%

S14(신규 파일 60%) → 전체 파일 70%로 기준 상향.

**전제**: S14 완료
**변경**: `harness-loop.sh`

---

### ⬜ L2 — Git Worktree 격리

팀 병렬 개발 시 브랜치 충돌 방지.
각 루프를 별도 worktree에서 실행, 성공 시만 메인 병합.

**전제**: feature branch 전략 확립
**변경**: `harness-executor.sh`, `harness-loop.sh`

---

### ⬜ L3 — 뮤테이션 테스트

테스트가 통과해도 실제로 버그를 잡는지 검증 (stryker-js).

**재검토 트리거**: 테스트 신뢰도 문제 반복 + 토큰 예산 여유
**변경**: `harness-loop.sh`

---

### ⬜ L4 — 크로스모델 리뷰 전체 PR

M1(보안 파일 한정) → 전체 PR로 확장.

**전제**: M1 완료 + 토큰 예산 충분
**변경**: `harness-loop.sh`
