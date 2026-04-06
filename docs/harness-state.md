# 하네스 엔지니어링 현행 상태

> 최종 업데이트: 2026-04-06
> 하네스 수정 후 마지막 단계로 갱신한다 (백로그 → 수정 → **이 파일**).

---

## 1. 시스템 개요

AI 에이전트가 실수할 수 없는 환경을 코드가 아닌 구조로 강제하는 시스템.
Claude Code 위에서 bash 스크립트 + Python 훅만으로 동작 (외부 인프라 의존 없음).

**4기둥 구현 현황**

| 기둥 | 구현체 | 상태 |
|---|---|---|
| 컨텍스트 파일 | `orchestration-rules.md` (단일 소스) + 2-섹션 에이전트 파일 | ✅ |
| CI/CD 게이트 | `agent-boundary.py` + `orch-rules-first.py` + validator/test-engineer/security-reviewer 순차 게이트 | ✅ |
| 도구 경계 | 에이전트별 Write/Edit 허용 경로 매트릭스 (물리적 차단) | ✅ |
| 피드백 루프 | `harness-memory.md` (반자동 지원: S5) + Auto-Promoted Rules (3회 누적 자동 프로모션) | ✅ |

---

## 2. 핵심 파일 인벤토리

### 글로벌 (`~/.claude/`)

| 파일 | 역할 | 의존 |
|---|---|---|
| `harness-executor.sh` | 5가지 모드(impl/impl2/design/bugfix/plan) 라우터 + depth 자동 감지 (`detect_depth()`) | harness-loop.sh, 에이전트들 |
| `harness-loop.sh` | 구현 루프 엔진 (fast/std/deep depth 분기, engineer→test-engineer→validator→pr-reviewer→security-reviewer, 3회 재시도) + memory candidate 작성 | /tmp/{p}_* 플래그들 |
| `setup-harness.sh` | 프로젝트별 훅 설치 → `.claude/settings.json` + `harness.config.json` | - |
| `setup-agents.sh` | 프로젝트별 에이전트 파일 초기화 (9개) + GitHub milestone/label 생성 | - |
| `harness-memory.md` | 크로스 프로젝트 실패/성공 패턴 저장 (S5 반자동: FAIL 시 초안 생성 → 유저 승인) | harness-loop.sh (CONSTRAINTS 로드) |
| `orchestration-rules.md` | **마스터 규칙 단일 소스** — 루프 A~E, 마커, 정책 | 모든 스크립트/에이전트 |

### 글로벌 훅 (`~/.claude/hooks/`)

| 파일 | 트리거 | 역할 |
|---|---|---|
| `harness-router.py` | UserPromptSubmit (global) | 프롬프트 의도 분류 (regex+LLM 하이브리드) → 워크플로우 상태 주입 |
| `harness-session-start.py` | SessionStart (global) | `/tmp/{prefix}_*` 플래그 전체 초기화 |
| `orch-rules-first.py` | PreToolUse(Edit/Write) (global) | `orchestration-rules.md` 선행 수정 물리적 강제 |
| `agent-boundary.py` | PreToolUse(Edit/Write) (global) | 에이전트별 파일 수정 경로 물리적 제한 |
| `harness-settings-watcher.py` | PostToolUse(Edit) (global) | `settings.json` hooks 변경 감지 → 동기화 리마인드 |

### 프로젝트별 (`.claude/`, `setup-harness.sh`가 생성)

| 파일 | 역할 |
|---|---|
| `settings.json` | PreToolUse(docs/src 보호) + PreToolUse(Bash:git commit 게이트) + PreToolUse(Agent:6단계 게이트) + PostToolUse(Agent:플래그 관리) |
| `harness.config.json` | `{"prefix": "xx"}` — 프로젝트별 플래그 prefix (최대 6자) |
| `harness-executor.sh` | setup-agents.sh가 글로벌에서 복사 |
| `harness-loop.sh` | setup-agents.sh가 글로벌에서 복사 |
| `agents/*.md` | setup-agents.sh가 초기화한 9개 에이전트 파일 |

---

## 3. 플래그 체계 (`/tmp/{prefix}_*`)

| 플래그 | 생성 주체 | 소비 주체 | 의미 |
|---|---|---|---|
| `{p}_harness_active` | harness-executor.sh | harness-loop.sh | 하네스 실행 중 |
| `{p}_plan_validation_passed` | validator (Plan Validation PASS) | harness-loop.sh (impl2 진입 체크) | impl 파일 검증 완료 |
| `{p}_impl_path` | harness-executor.sh | harness-loop.sh | 현재 impl 파일 경로 |
| `{p}_current_issue` | harness-executor.sh | harness-loop.sh, PostToolUse 훅 | 현재 처리 중 이슈 번호 |
| `{p}_test_engineer_passed` | test-engineer (TESTS_PASS) | harness-loop.sh | 테스트 통과 |
| `{p}_validator_b_passed` | validator Mode B (PASS) | harness-loop.sh | 코드 검증 통과 |
| `{p}_pr_reviewer_lgtm` | pr-reviewer (LGTM) | harness-loop.sh | PR 리뷰 승인 |
| `{p}_security_review_passed` | security-reviewer (SECURE) | harness-loop.sh | 보안 감사 통과 |
| `{p}_designer_ran` | harness-executor.sh (design mode) | harness-executor.sh | designer 실행 완료 |
| `{p}_design_critic_passed` | design-critic (PICK) | harness-executor.sh | 디자인 승인 |
| `{p}_{agent}_active` | harness-loop.sh (에이전트 호출 전) | agent-boundary.py | 에이전트 경계 검사용 |
| `{p}_pr_body.txt` | harness-loop.sh (HARNESS_DONE) | 메인 Claude (PR 생성 시 활용) | PR 본문 자동 생성 |
| `{p}_memory_candidate.md` | harness-loop.sh (FAIL 시) | 메인 Claude (유저 승인 후 harness-memory.md에 기록) | 실패 패턴 초안 (S5) |
| `{p}-agent-calls.log` | harness-loop.sh | - | 에이전트 호출 로그 |

**생명주기**: SessionStart → `harness-session-start.py`가 `/tmp/{p}_*` 전체 삭제 → 루프 진행 중 생성 → HARNESS_DONE 후 정리

---

## 4. 완료된 기능 ✅

### 베이스라인

| 기능 | 구현체 | 완료일 |
|---|---|---|
| 결정론적 게이트 (5모드 라우팅) | `harness-executor.sh` | 초기 |
| 플래그 기반 상태머신 | `/tmp/{p}_*` 14개 | 초기 |
| Ground truth 테스트 (LLM 독립) | `npx vitest run` in `harness-loop.sh` | 초기 |
| 에이전트 도구 경계 물리적 차단 | `agent-boundary.py` | 초기 |
| 보안 감사 게이트 | `security-reviewer` (OWASP+WebView) | 초기 |
| Smart Context (50KB 캡) | `build_smart_context()` in `harness-loop.sh` | 초기 |
| 실패 유형별 수정 전략 | `fail_type` 4종 분기 (test/validator/pr/security) | 초기 |
| 실패 패턴 자동 프로모션 | 3회 누적 → Auto-Promoted Rules | 초기 |
| 단일 소스 원칙 물리적 강제 | `orch-rules-first.py` | 초기 |
| 의도 분류 라우터 | regex + LLM 하이브리드 in `harness-router.py` | 초기 |
| 루프 A~E 5종 | `orchestration-rules.md` + `harness-executor.sh` | 초기 |

### 고도화 항목 (S코드)

| 코드 | 항목 | 구현체 | 완료일 |
|---|---|---|---|
| S1 | 수용 기준 메타데이터 | `(TEST)/(BROWSER:DOM)/(MANUAL)` 태그 + validator Plan Validation 게이트 | 2026-04-05 |
| S2 | PR body 자동 생성 | `harness-loop.sh` HARNESS_DONE 후 `/tmp/{p}_pr_body.txt` | 2026-04-05 |
| S3 | doc-garden 스킬 | `/doc-garden` 커맨드 — 문서-코드 불일치 리포트 (수동 트리거, 자동 수정 없음) | 2026-04-05 |
| S4 | Depth Selector | `--depth=fast/std/deep` — fast: engineer→commit만 / std: 전체 루프 / deep: std+S15 stub + 자동 감지 | 2026-04-05 |
| S5 | Memory 반자동 기록 | FAIL 시 `/tmp/{p}_memory_candidate.md` 초안 작성, HARNESS_DONE 후 유저에게 기록 여부 제안 | 2026-04-05 |
| S6 | AMBIGUOUS 자동 트리거 | `harness-router.py` AMBIGUOUS + no_active → product-planner 힌트 주입 (루프 진입 금지) | 2026-04-05 |
| S7 | 세션 컨텍스트 브리지 | `harness-session-start.py` — 프로젝트명·최근커밋·진행중 항목 자동 주입. HARNESS_DONE 시 `last_issue` 저장 | 2026-04-05 |
| S8 | 하네스 smoke test | `commands/harness-test.md` — 파일존재·문법·플래그 dry-run, SMOKE_PASS/FAIL 판정 | 2026-04-05 |
| S10 | 납품 게이트 | `commands/deliver.md` — .env노출·console.log·하드코딩URL·빌드 스캔, DELIVERY_READY/BLOCKED/WARN | 2026-04-05 |
| S16 | Router spawn 안전화 | `harness-router.py` try_spawn_harness() O_EXCL lock + TTL 120s + heartbeat / `harness-executor.sh` EXIT trap + timeout 300 / `harness-loop.sh` timeout 300 | 2026-04-06 |
| S17 | pre-evaluator + JSON Lease | `harness-loop.sh` run_automated_checks() (has_changes/no_new_deps/file_unchanged) / `harness-executor.sh` _write_lease() JSON heartbeat / `harness-router.py` _lease_age() | 2026-04-06 |
| S18 | Adaptive Interview Harness | `harness-router.py` run_interview_turn() + AMBIGUOUS 분기 교체 — AMBIGUOUS 감지 → Haiku Q&A (max_turn=4) → plan 자동 spawn / interview_state.json 상태 관리 / LLM override 차단 (0-A) / double Haiku 방지 (0-B) | 2026-04-06 |

---

## 5. 에이전트 역할 경계 매트릭스

`agent-boundary.py`가 `{p}_{agent}_active` 플래그 활성 상태에서 허용 경로 외 Write/Edit를 물리적으로 차단.

| 에이전트 | 허용 경로 | 절대 금지 |
|---|---|---|
| engineer | `src/**` (테스트 포함) | 설계 문서 수정 |
| architect | `docs/**`, `backlog.md` | `src/**` 수정 |
| designer | `design-preview-*.html`, `docs/ui-spec*` | architecture 계열, src |
| test-engineer | `src/__tests__/**` | src 본체 수정 |
| product-planner | `prd.md`, `trd.md` | 코드·설계 문서 |
| validator, design-critic, pr-reviewer, qa, security-reviewer | *(없음 — ReadOnly)* | 모든 Write/Edit |

## 6. 의존성 맵

```mermaid
graph TD
  User[사용자 프롬프트] --> Router[harness-router.py\nUserPromptSubmit]
  Router -->|AMBIGUOUS| Hint[product-planner 힌트 주입\n루프 진입 차단]
  Router -->|분류 완료| Executor[harness-executor.sh\n5모드 라우터]
  Executor -->|impl2 + depth 감지| Loop[harness-loop.sh\n구현 루프]
  Executor -->|impl| Architect[architect\nModule Plan]
  Architect --> Validator_C[validator\nPlan Validation]
  Validator_C -->|PASS| Loop
  Loop -->|fast| Engineer[engineer\nsrc/** 구현]
  Loop -->|std/deep| Engineer
  Engineer --> Commit_fast[git commit\nfast mode]
  Loop -->|std/deep| TestEngineer[test-engineer\n테스트 작성]
  TestEngineer --> Vitest[npx vitest run\nground truth]
  Vitest --> Validator_B[validator Mode B\n스펙 검증]
  Validator_B --> PRReviewer[pr-reviewer\n코드 품질]
  PRReviewer --> Security[security-reviewer\nOWASP 감사]
  Security --> Commit[git commit\n+ pr_body.txt + memory_candidate]

  OrcRules[orchestration-rules.md] -.->|단일 소스| Executor
  OrcRules -.->|단일 소스| Loop
  Memory[harness-memory.md] -.->|CONSTRAINTS| Loop
  Flags[/tmp/prefix_*\n플래그들] -.->|상태| Loop

  OrcFirst[orch-rules-first.py\nPreToolUse] -.->|차단| OrcRules
  AgentBoundary[agent-boundary.py\nPreToolUse] -.->|경로 제한| Engineer
  AgentBoundary -.->|경로 제한| TestEngineer
```

**글로벌 훅 실행 순서 (모든 파일 편집 시)**:
```
Edit/Write 시도
  → orch-rules-first.py (orchestration-rules.md 선행 수정 체크)
  → agent-boundary.py ({agent}_active 플래그 + 허용 경로 체크)
  → 허용 시 실제 편집 실행
  → harness-settings-watcher.py (settings.json 변경 감지)
```
