# 하네스 엔지니어링 현행 상태

> 최종 업데이트: 2026-04-05
> 이 파일은 하네스 파일 변경 시 즉시 갱신한다 (orchestration-rules.md 정책 9).

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
| 피드백 루프 | `harness-memory.md` (수동 관리) + Auto-Promoted Rules (3회 누적 자동 프로모션) | ✅ (반자동화 대기 중 → P1) |

---

## 2. 핵심 파일 인벤토리

### 글로벌 (`~/.claude/`)

| 파일 | 역할 | 의존 |
|---|---|---|
| `harness-executor.sh` | 5가지 모드(impl/impl2/design/bugfix/plan) 라우터 | harness-loop.sh, 에이전트들 |
| `harness-loop.sh` | 구현 루프 엔진 (engineer→test-engineer→validator→pr-reviewer→security-reviewer, 3회 재시도) | /tmp/{p}_* 플래그들 |
| `setup-harness.sh` | 프로젝트별 훅 설치 → `.claude/settings.json` + `harness.config.json` | - |
| `setup-agents.sh` | 프로젝트별 에이전트 파일 초기화 (9개) + GitHub milestone/label 생성 | - |
| `harness-memory.md` | 크로스 프로젝트 실패/성공 패턴 저장 (수동 관리) | harness-loop.sh (CONSTRAINTS 로드) |
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
| `{p}-agent-calls.log` | harness-loop.sh | - | 에이전트 호출 로그 |

**생명주기**: SessionStart → `harness-session-start.py`가 `/tmp/{p}_*` 전체 삭제 → 루프 진행 중 생성 → HARNESS_DONE 후 정리

---

## 4. 완료된 기능 ✅

### 베이스라인

| 기능 | 구현체 | 완료일 |
|---|---|---|
| 결정론적 게이트 (5모드 라우팅) | `harness-executor.sh` | 초기 |
| 플래그 기반 상태머신 | `/tmp/{p}_*` 13개 | 초기 |
| Ground truth 테스트 (LLM 독립) | `npx vitest run` in `harness-loop.sh` | 초기 |
| 에이전트 도구 경계 물리적 차단 | `agent-boundary.py` | 초기 |
| 보안 감사 게이트 | `security-reviewer` (OWASP+WebView) | 초기 |
| Smart Context (50KB 캡) | `build_smart_context()` in `harness-loop.sh` | 초기 |
| 실패 유형별 수정 전략 | `fail_type` 4종 분기 (test/validator/pr/security) | 초기 |
| 실패 패턴 자동 프로모션 | 3회 누적 → Auto-Promoted Rules | 초기 |
| 단일 소스 원칙 물리적 강제 | `orch-rules-first.py` | 초기 |
| 의도 분류 라우터 | regex + LLM 하이브리드 in `harness-router.py` | 초기 |
| 루프 A~E 5종 | `orchestration-rules.md` + `harness-executor.sh` | 초기 |

### 고도화 항목

| ID | 기능 | 구현체 | 완료일 |
|---|---|---|---|
| G3 | 수용 기준 메타데이터 | `(TEST)/(BROWSER:DOM)/(MANUAL)` 태그 + validator Plan Validation 게이트 | 2026-04-05 |
| G6 | PR body 자동 생성 | `harness-loop.sh` HARNESS_DONE 후 `/tmp/{p}_pr_body.txt` | 2026-04-05 |
| G10 | doc-garden 스킬 | `/doc-garden` 커맨드 — 문서-코드 불일치 리포트 (수동 트리거, 자동 수정 없음) | 2026-04-05 |
| P5 | AMBIGUOUS → product-planner 자동 힌트 | `harness-router.py` AMBIGUOUS + no_active → product-planner 힌트 주입 (루프 진입 금지) | 2026-04-05 |

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

---

## 6. 현재 알려진 한계

| 항목 | 상세 | 대응 계획 |
|---|---|---|
| **harness-memory 수동 전용** | 에이전트 자동 기록 금지 → 사람이 직접 복사해야 프로모션됨 | P1 (Memory 반자동) |
| **Smart Context 로직 미명세** | `build_smart_context()` 50KB 캡은 구현. hot-file 선택 기준은 정의 안 됨 | P2 (Smart Context 명세) |
| **루프 재개 불가** | 세션 중단 시 처음부터 재시작 (체크포인트 없음) | P3 (루프 체크포인트) |
| **Depth 선택 없음** | 변수 rename부터 핵심 모듈까지 동일 루프 깊이 (5 에이전트 풀 실행) | P0 (Depth Selector) |
| **[REQ-NNN] ID 추적 미구현** | G3 계획에 있었지만 orchestration-rules.md에 미반영. prd→impl→테스트 추적 안 됨 | 별도 검토 필요 |
| **정책 9 물리적 강제 없음** | harness-state.md/backlog.md 선행 업데이트 강제가 written policy만 (훅 없음) | P0 이후 백로그 등록 |

---

## 7. 의존성 맵

```mermaid
graph TD
  User[사용자 프롬프트] --> Router[harness-router.py\nUserPromptSubmit]
  Router --> Executor[harness-executor.sh\n5모드 라우터]
  Executor -->|impl2| Loop[harness-loop.sh\n구현 루프]
  Executor -->|impl| Architect[architect\nModule Plan]
  Architect --> Validator_C[validator\nPlan Validation]
  Validator_C -->|PASS| Loop
  Loop --> Engineer[engineer\nsrc/** 구현]
  Loop --> TestEngineer[test-engineer\n테스트 작성]
  Loop --> Vitest[npx vitest run\nground truth]
  Loop --> Validator_B[validator Mode B\n스펙 검증]
  Loop --> PRReviewer[pr-reviewer\n코드 품질]
  Loop --> Security[security-reviewer\nOWASP 감사]
  Loop --> Commit[git commit\n+ pr_body.txt]

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
