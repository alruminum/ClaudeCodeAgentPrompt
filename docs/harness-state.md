# 하네스 엔지니어링 현행 상태

> 최종 업데이트: 2026-04-17
> 하네스 수정 후 마지막 단계로 갱신한다 (백로그 → 수정 → **이 파일**).

---

## 시스템 개요

AI 에이전트가 실수할 수 없는 환경을 코드가 아닌 구조로 강제하는 시스템.
Claude Code 위에서 Python 코어 + Bash 래퍼 + Python 훅으로 동작 (외부 인프라 의존 없음).

**4기둥 구현 현황**

| 기둥 | 구현체 | 상태 |
|---|---|---|
| 컨텍스트 파일 | `orchestration-rules.md` (단일 소스) + Universal Preamble (`agents/preamble.md`) 동적 주입 | ✅ |
| CI/CD 게이트 | `agent-boundary.py` + `orch-rules-first.py` + validator/test-engineer/security-reviewer 순차 게이트 | ✅ |
| 도구 경계 | 에이전트별 Write/Edit 허용 경로 매트릭스 (물리적 차단) | ✅ |
| 피드백 루프 | `harness-memory.md` (반자동 지원: S5) + Auto-Promoted Rules (3회 누적 자동 프로모션) | ✅ |

---

## 핵심 파일 인벤토리

### Python 코어 (`~/.claude/harness/*.py`) — 마이그레이션 완료

| 파일 | 역할 |
|---|---|
| `executor.py` | 메인 엔트리포인트 — 모드 라우팅 (impl/plan), lock, heartbeat, depth 감지 |
| `core.py` | `_agent_call()`, `kill_check()`, `parse_marker()` 등 코어 유틸 |
| `config.py` | 프로젝트 설정 로드 (harness.config.json, prefix, 경로) |
| `helpers.py` | impl 루프 공유 헬퍼 (constraints, budget_check, hlog) |
| `impl_loop.py` | impl depth별 루프 엔진 (simple/std/deep). std/deep: TDD 순서 (test-engineer 선행 -> engineer) |
| `impl_router.py` | impl 모드 진입 — 재진입 감지, architect, plan validation |
| `plan_loop.py` | plan 모드 — 기획-UX 루프만 (product-planner → ux-architect → validator UX). 설계 루프(architect SD + designer)는 메인 Claude 오케스트레이션으로 분리됨 |
| `review_agent.py` | 하네스 완료 후 Haiku 로그 분석 → review-result.json 생성 |
| `__init__.py` | 패키지 초기화 |

### Bash 래퍼 (`~/.claude/harness/*.sh`) — Python 코어 호출

| 파일 | 역할 |
|---|---|
| `executor.sh` | Python `executor.py` 래퍼 (Bash 도구 호출 호환) |
| `impl.sh` | Python `impl_router.py` 래퍼 |
| `impl_simple.sh` | Python `impl_loop.py --depth simple` 래퍼 |
| `impl_std.sh` | Python `impl_loop.py --depth std` 래퍼 |
| `impl_deep.sh` | Python `impl_loop.py --depth deep` 래퍼 |
| `impl_helpers.sh` | Python `helpers.py` 래퍼 |
| `plan.sh` | Python `plan_loop.py` 래퍼 |
| `review-agent.sh` | Python `review_agent.py` 래퍼 |
| `utils.sh` | Python `core.py` 래퍼 — `_agent_call()` 등 공용 함수 |
| `flags.sh` | 플래그 이름 상수 정의 (상수화: #A3) |
| `markers.sh` | 마커 파싱 유틸 (강건화: #A2) |
| `rollback.sh` | 실패 시 git stash 격리 |
| `design.sh` | ⚠️ DEPRECATED — ux 스킬이 designer 직접 호출 |

### 기타 글로벌 파일

| 파일 | 역할 |
|---|---|
| `setup-harness.sh` | 프로젝트별 훅 설치 → `.claude/settings.json` + `harness.config.json` |
| `setup-agents.sh` | 프로젝트별 에이전트 파일 초기화 + GitHub milestone/label 생성 |
| `harness-memory.md` | 크로스 프로젝트 실패/성공 패턴 저장 (반자동: FAIL 시 초안 → 유저 승인) |
| `orchestration-rules.md` | **마스터 규칙 단일 소스** — 루프 A~E, 마커, 정책 |
| `agents/preamble.md` | Universal Preamble — 전 에이전트 공통 지침 (동적 주입) |
| `scripts/harness-review.py` | JSONL 로그 파서 — 타임라인·도구사용·WASTE 패턴 진단 + 세션 로그 모순 감지 |

### 글로벌 훅 (`~/.claude/hooks/`)

| 파일 | 트리거 | 역할 |
|---|---|---|
| `harness_common.py` | (모듈) | `get_prefix()`, `deny()`, `flag_path()` 공유 유틸 |
| `harness-router.py` | UserPromptSubmit | fast_classify(regex) → extract_intent(Haiku LLM) → 워크플로우 상태/Adaptive Interview 주입 |
| `harness-session-start.py` | SessionStart | 플래그 전체 초기화 + 프로젝트 컨텍스트 자동 주입 |
| `orch-rules-first.py` | PreToolUse(Edit/Write) | `orchestration-rules.md` 선행 수정 물리적 강제 |
| `agent-boundary.py` | PreToolUse(Edit/Write/Read) | 에이전트별 경로 제한 + 메인 Claude file-ownership 차단 통합 |
| `agent-gate.py` | PreToolUse(Agent) | 에이전트 실행 순서·조건 검증 (qa는 하네스 외에서도 허용) |
| `commit-gate.py` | PreToolUse(Bash) | git commit 전 pr-reviewer LGTM 확인 |
| `issue-gate.py` | PreToolUse | 이슈 관련 게이트 (qa 예외 포함) |
| `post-agent-flags.py` | PostToolUse(Agent) | 에이전트 완료 후 플래그 생성/삭제 + 문서 신선도 경고 |
| `post-commit-cleanup.py` | PostToolUse(Bash) | git commit 성공 후 1회성 플래그 삭제 |
| `post-commit-scan.sh` | PostToolUse(Bash) | 커밋 후 스캔 |
| `harness-settings-watcher.py` | PostToolUse(Edit) | `settings.json` hooks 변경 감지 → 동기화 리마인드 |
| `harness-review-inject.py` | UserPromptSubmit | review-result.json 감지 → 리뷰 결과 프롬프트 주입 |
| `harness-review-trigger.py` | (트리거) | 하네스 완료 후 자동 /harness-review 실행 |
| `harness-review-stop.py` | (트리거) | 리뷰 누락 방지 — .reviewed 마커 + 자동 리마인더 |
| `harness-drift-check.py` | (감지) | 에이전트 파일 drift 감지 |

### 프로젝트별 (`.claude/`, `setup-harness.sh`가 생성)

| 파일 | 역할 |
|---|---|
| `settings.json` | `env` + `allowedTools`만 — 훅 없음 (전역 전용). `_meta: harness` 태그로 프레임워크/사용자 분리 |
| `harness.config.json` | `{"prefix": "xx"}` — 프로젝트별 플래그 prefix (최대 6자) |
| `agents/*.md` | setup-agents.sh가 초기화한 에이전트 파일 |

---

## 플래그 체계 (`/tmp/{prefix}_*`)

| 플래그 | 생성 주체 | 소비 주체 | 의미 |
|---|---|---|---|
| `{p}_harness_active` | executor | impl 루프 | 하네스 실행 중 |
| `{p}_plan_validation_passed` | validator (Plan Validation PASS) | impl 루프 (engineer 진입 체크) | impl 파일 검증 완료 |
| `{p}_impl_path` | executor | impl 루프 | 현재 impl 파일 경로 |
| `{p}_current_issue` | executor | impl 루프, PostToolUse 훅 | 현재 처리 중 이슈 번호 |
| `{p}_test_engineer_passed` | test-engineer (TESTS_PASS) | impl 루프 | 테스트 통과 |
| `{p}_validator_b_passed` | validator Mode B (PASS) | impl 루프 | 코드 검증 통과 |
| `{p}_pr_reviewer_lgtm` | pr-reviewer (LGTM) | impl 루프 | PR 리뷰 승인 |
| `{p}_security_review_passed` | security-reviewer (SECURE) | impl 루프 | 보안 감사 통과 |
| `{p}_designer_ran` | ux 스킬 | ux 스킬 | designer 실행 완료 |
| `{p}_design_critic_passed` | ux 스킬 / design-critic | ux 스킬 | 디자인 승인 |
| `{p}_{agent}_active` | `_agent_call()` | agent-boundary.py | 에이전트 경계 검사용 |
| `{p}_pr_body.txt` | impl 루프 (HARNESS_DONE) | 메인 Claude (PR 생성) | PR 본문 자동 생성 |
| `{p}_memory_candidate.md` | impl 루프 (FAIL 시) | 메인 Claude (유저 승인) | 실패 패턴 초안 |
| `{p}_harness_kill` | 사용자 (`/harness-kill`) | `kill_check()` | 킬 스위치 |
| `{p}_{agent}_cost.txt` | `_agent_call()` | `budget_check()` | 에이전트별 비용 (USD) |
| `{p}_hud.json` | HUD 클래스 | `/harness-monitor`, 외부 watch | 실시간 진행 상태 (depth, attempt, agents) |
| `{p}_handoffs/attempt-N/` | `write_handoff()` | 다음 에이전트 (explore_instruction) | 구조화된 인수인계 문서 |
| `{p}_polish_out.txt` | engineer POLISH | impl 루프 | POLISH 모드 출력 |

**생명주기**: SessionStart → `harness-session-start.py`가 플래그 전체 삭제 → 루프 진행 중 생성 → HARNESS_DONE 후 정리

---

## 현재 기능

### 게이트 / 안전장치

- **Depth 자동 선택**: impl 파일의 `(TEST)/(BROWSER:DOM)/(MANUAL)` 태그 + 컨텍스트 기반으로 simple/std/deep 자동 감지. architect가 판단 질문으로 depth 추천하며, 수동 `--depth` 오버라이드 가능. frontmatter 누락 시 std 폴백.
- **비용 제어**: 에이전트별 `--max-budget-usd 2.00` 상한 + 전체 루프 `$10` 상한 (`budget_check()`). 도메인별 토큰 예산 (`config.token_budget` dict, 85% 경고). ISO 타임스탬프 + 타이밍 요약.
- **Circuit Breaker**: 동일 fail_type 120초 내 2회 반복 → attempt 소진 없이 즉시 IMPLEMENTATION_ESCALATE. JSONL `circuit_breaker` 이벤트 기록.
- **킬 스위치**: `/harness-kill` 커맨드로 다음 에이전트 호출 전 즉시 루프 중단.
- **에이전트 timeout**: 역할별 차등 timeout (architect/engineer=900s, validator 등=300~600s). exit 124 감지 시 자동 스킵. 타임아웃 watchdog + SIGTERM 핸들러로 좀비 프로세스 방지.
- **모호한 요청 차단**: AMBIGUOUS 감지 시 루프 진입 금지. Adaptive Interview로 Haiku Q&A(max 4턴) 후 명확화. 완료 시 product-planner 호출 힌트 주입.
- **게이트 책임 분리**: 훅은 외부 방어(경로 제한, 순서 위반 차단)만 담당. 에이전트 실행 순서는 스크립트가 결정. QA는 하네스 외에서도 분류 역할로 허용.
- **settings.json 훅 자동 구성**: `_meta: harness` 태그로 프레임워크 관리 훅과 사용자 설정을 분리. `setup-harness.sh`가 자동 생성.

### 관측성 / 로깅

- **JSONL 아카이브**: 전 에이전트 stream-json 실시간 기록 → `~/.claude/harness-logs/{prefix}/run_*.jsonl`. FIFO 10-run 보존. 에이전트 I/O 원문 전량 보존 + 히스토리 루프별 격리.
- **디버그 로그**: `hlog()` 함수 — `[HH:MM:SS] [attempt=N]` 형식. 루프 시작/종료, 에이전트 전후, 테스트 전후 기록.
- **HUD Statusline**: depth별 에이전트 체인 진행 상태를 stdout 진행 바로 표시. `.claude/harness-state/{prefix}_hud.json`에 실시간 상태 저장. `/harness-monitor` 스킬로 별도 세션 실시간 모니터링 (전용 세션, 무한 대기, 루프 자동 감지).
- **Handoff 문서**: 에이전트 전환 시 하네스가 구조화된 인수인계 문서 자동 생성 (변경요약/결정사항/주의사항/확인항목). `explore_instruction(handoff_path=)` 우선 전달. `.claude/harness-state/{prefix}_handoffs/attempt-N/`.
- **REFLECTION (성공 학습)**: HARNESS_DONE 시 engineer 출력에서 성공 패턴 자동 추출 → `harness-memory.md` Success Patterns 섹션. 실패 auto-promotion과 대칭.
- **harness-review**: JSONL 파서 기반 자동 진단 시스템.
  - **WASTE 패턴 8종**: 낭비 감지 (CONTEXT_EXCESS, SPARSE_PROMPT, DUPLICATE_READ, INFRA_READ 등)
  - **흐름 진단 4패턴**: ABNORMAL_END, EARLY_EXIT, MISSING_PHASE, ROUTING_MISMATCH
  - **자동 실행**: HARNESS_DONE/ESCALATE 후 자동 트리거. `.reviewed` 마커로 누락 방지 + 자동 리마인더.
  - **세션 로그 모순 감지**: 메인 Claude 세션에서 에이전트 출력과 모순되는 행동 자동 탐지.
  - **원문 출력 강제**: 리뷰 결과 재가공/요약/생략 없이 원문 그대로 출력.

### 라우팅 / 분류

- **의도 분류**: 2단계 하이브리드. `fast_classify()` regex(GREETING/QUESTION/BUG/IMPLEMENTATION) → 미분류 시 Haiku LLM 폴백 (`_call_haiku()` urllib 5s + CLI socrates 10s).
- **에이전트 분류 상수**: 단일 소스에서 관리. issue-gate에서 QA 예외 포함.
- **루프 D (버그픽스) 라우팅**: 3타입(FUNCTIONAL_BUG/SPEC_ISSUE/DESIGN_ISSUE). 심각도 없음. QA가 모든 경로에서 이슈 등록 의무. BUGFIX_PLAN → LIGHT_PLAN으로 일반화 (버그+디자인 국소 변경 통합).
- **루프 C/D 재진입**: impl 파일/GitHub issue/플래그 기반 경량 감지. 중단 후 처음부터 재시작하지 않고 가능한 지점부터 이어감.
- **세션 컨텍스트 브리지**: SessionStart 시 프로젝트명·최근커밋·진행중 항목 자동 주입. 새 세션 시작 비용 절감.
- **executor 경로 폴백**: 프로젝트 `.claude/harness/` → 없으면 글로벌 `~/.claude/harness/` 자동 전환.

### 구현 루프 (impl)

- **3단계 depth**: simple (engineer → pr-reviewer → POLISH → merge), std (+ test-engineer → validator → POLISH), deep (+ security-reviewer). engineer 직후 feature branch 즉시 커밋.
- **POLISH 모드**: pr-reviewer LGTM 후 NICE TO HAVE 항목을 engineer `@MODE:ENGINEER:POLISH` (180초)로 경량 정리. regression 실패 시 `git reset --hard` revert → 원본으로 merge.
- **test/lint command 설정화**: `config.test_command` / `config.lint_command`로 프레임워크 비종속 (vitest 하드코딩 제거).
- **Second Reviewer v3**: `harness/providers.py`의 어댑터 패턴으로 외부 AI 파일별 리뷰. 지원 프로바이더: Gemini (`gemini` CLI, stdin pipe), Codex (`codex exec`, OMC 참고). pr-reviewer와 threading 병렬. `git diff HEAD~1 -- {file}`로 파일별 patch 추출 (파일당 60초). 2단계 프롬프트(1차 diff만, NEED_FULL_FILE 시 2차 전체 파일). LGTM 시 findings → POLISH 합산. CLI 미설치/에러 → 자동 스킵. 새 프로바이더 추가: providers.py에 클래스 + PROVIDERS dict 등록만.
- **SPEC_GAP 핸들링**: SPEC_GAP_FOUND → architect SPEC_GAP → 3-way 분기 (RESOLVED/PP_ESCALATION/TECH_CONSTRAINT). `spec_gap_count` 동결 카운터 (max 2).
- **plan.sh**: 6단계 흐름 (product-planner → architect SD → validator DV → architect MP → validator PV → PLAN_VALIDATION_PASS). product-planner가 CLARITY_INSUFFICIENT 에스컬레이션 시 메인 Claude가 유저에게 추가 질문 후 재실행 (max 2회).
- **모호성 정량화**: product-plan 스킬이 5차원 모호성 점수(Goal/User/Scope/Constraints/Success)로 인터뷰. 20% 미만 도달 시 plan 루프 진입.
- **Smart Context**: impl 명시 경로 우선, attempt별 에러 트레이스 carry-forward. 소스파일 3KB캡, 전체 30KB캡.
- **실패 복구**: `rollback_attempt()` — 실패 시 `git stash push --include-untracked`로 오염 코드 격리. `check_agent_output()` — 빈 출력 graceful retry.
- **Phase C/D**: `build_loop_context()`로 루프별 진입 컨텍스트 prepend (8KB 캡). review-agent가 완료 후 Haiku 로그 분석.

### 디자인 워크플로우

- **2×2 포맷 매트릭스**: SCREEN/COMPONENT × ONE_WAY/THREE_WAY. 하네스 루프 밖에서 ux 스킬이 designer Agent를 직접 호출.
- **Pencil MCP 기반**: HTML 프리뷰/Figma 모드 제거. `.pen` 파일로 디자인 생성/검증.
- **THREE_WAY 모드**: design-critic이 3개 variant를 PASS/REJECT 판정 → 유저 PICK.
- **DESIGN_ISSUE 흐름**: 이슈 중복 생성 방지. designer Phase 0-0에서 이슈 생성. HANDOFF 시 이슈번호 전달 보장.

### 에이전트 관리

- **Universal Preamble**: `agents/preamble.md`에 전 에이전트 공통 지침 정의. 동적 주입으로 에이전트 파일 중복 제거.
- **인프라 탐색 금지**: architect/engineer/validator에 orchestration-rules.md·harness/·hooks/ 인프라 파일 Read 금지 명시.
- **도구 경계 물리적 차단**: `agent-boundary.py`가 `{agent}_active` 플래그 활성 시 허용 경로 외 Write/Edit 차단.
- **QA 스코프**: Agent/Bash 도구 제거, 인프라 접근 금지. Grep-first 전략, Read 최대 3개/150줄, 총 도구 10회 제한.

### 코드 품질 / 인프라

- **Python 마이그레이션 완료**: 코어 로직 9개 모듈 Python 전환. Bash 래퍼가 Python을 호출하는 구조. `.sh.bak` 백업 보존.
- **마커 파싱 강건화**: `^MARKER$` 라인 전체 매칭. `flags.sh`에 플래그 이름 상수 정의.
- **PR body 자동 생성**: HARNESS_DONE 후 What/Why + 테스트 결과 + 위험도 포함.
- **Memory 반자동 기록**: FAIL 시 실패 패턴 초안 → 유저 승인 후 `harness-memory.md`에 기록. 3회 누적 시 Auto-Promoted Rules.
- **PREFIX 전략 통일**: `harness_common.py` 공유 모듈. 하드코딩 경로 전면 제거.
- **BATS 테스트**: 하네스 스크립트 자체 테스트 115건+.
- **플래그 영속화**: `/tmp` → 프로젝트별 `.claude/harness-state/` 영속 디렉토리 이전.

### 스킬

| 스킬 | 기능 |
|---|---|
| `/harness-test` | fixture impl로 플래그 흐름 dry-run — SMOKE_PASS/FAIL 판정 |
| `/harness-kill` | 실행 중인 하네스 루프 즉시 중단 |
| `/harness-review` | JSONL 로그 분석 — WASTE 패턴 + 흐름 진단 리포트 |
| `/harness-status` | 현재 하네스 훅 상태와 워크플로우 플래그 확인 |
| `/harness-monitor` | 디버그 로그 실시간 스트리밍 (tail -f) |
| `/doc-garden` | docs/**와 src/** 비교 — 문서-코드 불일치 리포트 |
| `/deliver` | B2B 납품 전 체크 — .env 노출·console.log·빌드 스캔 |
| `/ux` | 디자인 요청 → 2×2 매트릭스 선택 → designer Agent 직접 호출 |

---

## 에이전트 역할 경계 매트릭스

`agent-boundary.py`가 `{p}_{agent}_active` 플래그 활성 상태에서 허용 경로 외 Write/Edit를 물리적으로 차단.

| 에이전트 | 허용 경로 | 절대 금지 |
|---|---|---|
| engineer | `src/**` (테스트 포함) | 설계 문서 수정 |
| architect | `docs/**`, `backlog.md` | `src/**` 수정 |
| designer | `design-variants/**`, `docs/ui-spec*` | architecture 계열, src |
| test-engineer | `src/__tests__/**` | src 본체 수정 |
| product-planner | `prd.md`, `trd.md` | 코드·설계 문서 |
| validator, design-critic, pr-reviewer, qa, security-reviewer | *(없음 — ReadOnly)* | 모든 Write/Edit |

---

## 의존성 맵

```mermaid
graph TD
  User[사용자 프롬프트] --> Router[harness-router.py\nUserPromptSubmit]
  Router -->|AMBIGUOUS| Interview[Adaptive Interview\nHaiku Q&A → product-planner 힌트]
  Router -->|분류 완료| Executor[executor.py\n5모드 라우터]
  Executor -->|impl + depth 감지| Loop[impl_loop.py\n구현 루프]
  Executor -->|impl| Architect[architect\nModule Plan]
  Architect --> Validator_C[validator\nPlan Validation]
  Validator_C -->|PASS| Loop
  Loop -->|simple/std/deep| Engineer[engineer\nsrc/** 구현]
  Engineer --> Commit_early[git commit\nfeature branch 즉시]
  Commit_early -->|simple| PRReviewer_fast[pr-reviewer\n코드 품질]
  Commit_early -->|std/deep| TestEngineer[test-engineer\n테스트 작성]
  TestEngineer --> Vitest[npx vitest run\nground truth]
  Vitest --> Validator_B[validator Mode B\n스펙 검증]
  Validator_B --> PRReviewer[pr-reviewer\n코드 품질]
  PRReviewer --> Security[security-reviewer\nOWASP 감사 — deep only]
  Security --> Merge[merge_to_main\npr_reviewer_lgtm 게이트]
  PRReviewer_fast --> Merge
  PRReviewer --> Merge

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
