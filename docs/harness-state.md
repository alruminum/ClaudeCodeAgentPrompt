# 하네스 엔지니어링 현행 상태

> 최종 업데이트: 2026-04-09 (S77 — harness-review INFRA 오탐 수정: agent-config/ 경로를 INFRA_EXCLUSIONS로 제외)
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
| `harness/utils.sh` | 공용 유틸: `_agent_call()`, `kill_check()`, `parse_marker()`, `run_plan_validation()`, `run_design_validation()`, `create_feature_branch()`, `merge_to_main()`, `generate_commit_msg()`, `rotate_harness_logs()`, `write_run_end()`, `build_loop_context()` (Phase C), `explore_instruction()`, `prune_history()` | 모든 harness 스크립트에서 source |
| `harness/review-agent.sh` | Phase D Step A: 하네스 완료 후 Haiku 로그 분석 → `/tmp/{prefix}_review-result.json` 생성 (JSON 검증 포함) | `write_run_end()` 백그라운드 트리거 |
| `harness/executor.sh` | 순수 라우터 + 공유 인프라 (lock, heartbeat, detect_depth) | harness-{impl,design,bugfix,plan}.sh |
| `harness/impl.sh` | impl 모드: 재진입 감지 → architect → `run_plan_validation()` → engineer 루프 | harness/impl-process.sh |
| `harness/impl-process.sh` | impl engineer 루프 엔진 (fast/std/deep depth 분기, 3회 재시도, SPEC_GAP 동결) + memory candidate | /tmp/{p}_* 플래그들 |
| `harness/design.sh` | design 모드 v2: designer (Pencil MCP Phase 0~1) → design-critic (스크린샷) → Phase 3 유저 선택 안내 → DESIGN_DONE. HTML 프리뷰 제거. | 에이전트들 |
| `harness/bugfix.sh` | bugfix 모드: qa → 5-way 분기 (engineer_direct/architect_full/design/backlog/KNOWN_ISSUE) + `run_plan_validation()` 활용 | 에이전트들 |
| `harness/plan.sh` | plan 모드: product-planner → architect SD → `run_design_validation()` → architect MP → `run_plan_validation()` → PLAN_VALIDATION_PASS | 에이전트들 |
| `setup-harness.sh` | 프로젝트별 훅 설치 → `.claude/settings.json` + `harness.config.json` | - |
| `setup-agents.sh` | 프로젝트별 에이전트 파일 초기화 (9개) + GitHub milestone/label 생성 | - |
| `harness-memory.md` | 크로스 프로젝트 실패/성공 패턴 저장 (S5 반자동: FAIL 시 초안 생성 → 유저 승인) | harness/impl-process.sh (CONSTRAINTS 로드) |
| `orchestration-rules.md` | **마스터 규칙 단일 소스** — 루프 A~E, 마커, 정책 | 모든 스크립트/에이전트 |
| `scripts/harness-review.py` | JSONL 로그 파서 — 타임라인·도구사용·WASTE 패턴 8종 진단 | `/harness-review` 스킬 |

### 글로벌 훅 (`~/.claude/hooks/`)

| 파일 | 트리거 | 역할 |
|---|---|---|
| `harness_common.py` | (모듈) | `get_prefix()`, `deny()`, `flag_path()` 공유 유틸 (S54) |
| `harness-router.py` | UserPromptSubmit (global) | fast_classify(regex) → extract_intent(Haiku LLM) → 워크플로우 상태/Adaptive Interview 주입 |
| ~~`harness-stop-gate.sh`~~ | ~~Stop (global)~~ | ~~S33~~ **폐기** — 정책 11(포어그라운드 강제)으로 Stop 트리거 자체 미발생. 파일 삭제됨 |
| `harness-session-start.py` | SessionStart (global) | `/tmp/{prefix}_*` 플래그 전체 초기화 (timeout=5 추가: S56) |
| `orch-rules-first.py` | PreToolUse(Edit/Write) (global) | `orchestration-rules.md` 선행 수정 물리적 강제 |
| `agent-boundary.py` | PreToolUse(Edit/Write/Read) (global) | 에이전트별 경로 제한 + 메인 Claude file-ownership 차단 통합 (S55) |
| `agent-gate.py` | PreToolUse(Agent) (global) | 에이전트 실행 순서·조건 검증 (S55) |
| `commit-gate.py` | PreToolUse(Bash) (global) | git commit 전 pr-reviewer LGTM 확인 (S55) |
| `post-agent-flags.py` | PostToolUse(Agent) (global) | 에이전트 완료 후 플래그 생성/삭제 + 문서 신선도 경고 (S55) |
| `post-commit-cleanup.py` | PostToolUse(Bash) (global) | git commit 성공 후 1회성 플래그 삭제 (S55) |
| `harness-settings-watcher.py` | PostToolUse(Edit) (global) | `settings.json` hooks 변경 감지 → 동기화 리마인드 |
| `harness-review-inject.py` | UserPromptSubmit (global) | Phase D Step A: `/tmp/*_review-result.json` 감지 → 리뷰 결과 프롬프트 주입 (HARNESS_INTERNAL=1 시 스킵) |

### 프로젝트별 (`.claude/`, `setup-harness.sh`가 생성)

| 파일 | 역할 |
|---|---|
| `settings.json` | `env` + `allowedTools`만 — 훅 없음 (전역 전용) |
| `harness.config.json` | `{"prefix": "xx"}` — 프로젝트별 플래그 prefix (최대 6자) |
| `agents/*.md` | setup-agents.sh가 초기화한 9개 에이전트 파일 |

---

## 3. 플래그 체계 (`/tmp/{prefix}_*`)

| 플래그 | 생성 주체 | 소비 주체 | 의미 |
|---|---|---|---|
| `{p}_harness_active` | harness/executor.sh | harness/impl-process.sh | 하네스 실행 중 |
| `{p}_plan_validation_passed` | validator (Plan Validation PASS) | harness/impl-process.sh (engineer 루프 진입 체크) | impl 파일 검증 완료 |
| `{p}_impl_path` | harness/executor.sh | harness/impl-process.sh | 현재 impl 파일 경로 |
| `{p}_current_issue` | harness/executor.sh | harness/impl-process.sh, PostToolUse 훅 | 현재 처리 중 이슈 번호 |
| `{p}_test_engineer_passed` | test-engineer (TESTS_PASS) | harness/impl-process.sh | 테스트 통과 |
| `{p}_validator_b_passed` | validator Mode B (PASS) | harness/impl-process.sh | 코드 검증 통과 |
| `{p}_pr_reviewer_lgtm` | pr-reviewer (LGTM) | harness/impl-process.sh | PR 리뷰 승인 |
| `{p}_security_review_passed` | security-reviewer (SECURE) | harness/impl-process.sh | 보안 감사 통과 |
| `{p}_designer_ran` | harness/executor.sh (design mode) | harness/executor.sh | designer 실행 완료 |
| `{p}_design_critic_passed` | design-critic (PICK) | harness/executor.sh | 디자인 승인 |
| `{p}_{agent}_active` | `harness/utils.sh` `_agent_call()` (호출 전 touch / 종료 후 rm) | agent-boundary.py | 에이전트 경계 검사용 |
| `{p}_pr_body.txt` | harness/impl-process.sh (HARNESS_DONE) | 메인 Claude (PR 생성 시 활용) | PR 본문 자동 생성 |
| `{p}_memory_candidate.md` | harness/impl-process.sh (FAIL 시) | 메인 Claude (유저 승인 후 harness-memory.md에 기록) | 실패 패턴 초안 (S5) |
| `{p}-agent-calls.log` | harness/impl-process.sh | - | 에이전트 호출 로그 |
| `{p}_harness_kill` | 사용자 (`/harness-kill`) | harness/impl-process.sh `kill_check()` | 킬 스위치 — 다음 에이전트 호출 전 루프 중단 (S31) |
| `{p}_{agent}_cost.txt` | `harness/utils.sh` `_agent_call()` | `harness/impl-process.sh` `budget_check()` | 에이전트별 비용 (USD). result 이벤트 `total_cost_usd` 추출 (S32) |

**생명주기**: SessionStart → `harness-session-start.py`가 `/tmp/{p}_*` 전체 삭제 → 루프 진행 중 생성 → HARNESS_DONE 후 정리

---

## 4. 완료된 기능 ✅

### 베이스라인

| 기능 | 구현체 | 완료일 |
|---|---|---|
| 결정론적 게이트 (5모드 라우팅) | `harness/executor.sh` | 초기 |
| 플래그 기반 상태머신 | `/tmp/{p}_*` 14개 | 초기 |
| Ground truth 테스트 (LLM 독립) | `npx vitest run` in `harness/impl-process.sh` | 초기 |
| 에이전트 도구 경계 물리적 차단 | `agent-boundary.py` | 초기 |
| 보안 감사 게이트 | `security-reviewer` (OWASP+WebView) | 초기 |
| Smart Context (50KB 캡) | `build_smart_context()` in `harness/impl-process.sh` | 초기 |
| 실패 유형별 수정 전략 | `fail_type` 4종 분기 (test/validator/pr/security) | 초기 |
| 실패 패턴 자동 프로모션 | 3회 누적 → Auto-Promoted Rules | 초기 |
| 단일 소스 원칙 물리적 강제 | `orch-rules-first.py` | 초기 |
| 의도 분류 라우터 | regex + LLM 하이브리드 in `harness-router.py` | 초기 |
| 루프 A~E 5종 | `orchestration-rules.md` + `harness/executor.sh` | 초기 |

### 고도화 항목 (S코드)

| 코드 | 항목 | 구현체 | 완료일 |
|---|---|---|---|
| S1 | 수용 기준 메타데이터 | `(TEST)/(BROWSER:DOM)/(MANUAL)` 태그 + validator Plan Validation 게이트 | 2026-04-05 |
| S2 | PR body 자동 생성 | `harness/impl-process.sh` HARNESS_DONE 후 `/tmp/{p}_pr_body.txt` | 2026-04-05 |
| S3 | doc-garden 스킬 | `/doc-garden` 커맨드 — 문서-코드 불일치 리포트 (수동 트리거, 자동 수정 없음) | 2026-04-05 |
| S4 | Depth Selector | `--depth=fast/std/deep` — fast: eng→commit→pr-reviewer / std: eng→commit→test→validator→pr-reviewer / deep: std+security-reviewer. 자동 감지 포함 | 2026-04-05 |
| S5 | Memory 반자동 기록 | FAIL 시 `/tmp/{p}_memory_candidate.md` 초안 작성, HARNESS_DONE 후 유저에게 기록 여부 제안 | 2026-04-05 |
| S6 | AMBIGUOUS 자동 트리거 | `harness-router.py` AMBIGUOUS + no_active → product-planner 힌트 주입 (루프 진입 금지) | 2026-04-05 |
| S7 | 세션 컨텍스트 브리지 | `harness-session-start.py` — 프로젝트명·최근커밋·진행중 항목 자동 주입. HARNESS_DONE 시 `last_issue` 저장 | 2026-04-05 |
| S8 | 하네스 smoke test | `commands/harness-test.md` — 파일존재·문법·플래그 dry-run, SMOKE_PASS/FAIL 판정 | 2026-04-05 |
| S10 | 납품 게이트 | `commands/deliver.md` — .env노출·console.log·하드코딩URL·빌드 스캔, DELIVERY_READY/BLOCKED/WARN | 2026-04-05 |
| S16 | ~~Router spawn~~ → Rate Limiter 유지 | `harness-router.py` _check_invoke_rate() (5회/60초). Popen/Atomic Lock/TTL/heartbeat 제거 (RF1) | 2026-04-07 |
| S17 | ~~JSON Lease~~ → pre-evaluator 유지 | `harness/impl-process.sh` run_automated_checks() (has_changes/no_new_deps/file_unchanged). JSON Lease 제거 (RF1) | 2026-04-07 |
| S18 | Adaptive Interview (additionalContext) | `harness-router.py` _run_interview_turn() + Haiku Q&A(max 4턴) → additionalContext로 질문/힌트 주입. Popen spawn 제거 (RF1) | 2026-04-07 |
| S19 | macOS timeout 호환 + impl_path 누락 가드 | `timeout` shim (perl fallback) + impl_path 미설정 시 즉시 오류 출력 | 2026-04-06 |
| S20 | Agent Observability | `harness/utils.sh` `_agent_call()` — stream-json tee → JSONL 아카이브 + python3 result 추출. FIFO 10-run 보존 (`rotate_harness_logs()`). 로그 위치: `~/.claude/harness-logs/{prefix}/run_*.jsonl` | 2026-04-06 |
| S21 | 타임스탬프 로깅 (hlog) | `harness/impl-process.sh` `hlog()` 함수 — `[HH:MM:SS] [attempt=N]` 형식. 루프 시작/종료·에이전트 전후·vitest 전후 기록. `/tmp/${PREFIX}-harness-debug.log` | 2026-04-06 |
| S22 | 에이전트 timeout + exit 124 감지 | `harness/utils.sh` `_call_exit` 전파 + `return $_call_exit`. `harness/impl-process.sh` 모든 `_agent_call`에 `\|\| AGENT_EXIT=$?` + exit 124 hlog | 2026-04-06 |
| S23 | std 모드 게이트 축소 (5→3단계) → S72로 재편 | fast=2단계(eng→pr-reviewer), std=4단계(eng→test→validator→pr-reviewer), deep=5단계(+security-reviewer). 머지 조건=pr_reviewer_lgtm 전 depth 통일 | 2026-04-06 |
| S24 | grep 파싱 라인 전체 매칭 | `grep -oE` → `grep -qE "^MARKER$"` 교체. UNKNOWN 케이스 `!= PASS` 통일. validator/pr-reviewer/security-reviewer 3곳 | 2026-04-06 |
| S26 | git diff 타이밍 픽스 | deep 모드 pr-reviewer 호출 직전 `git add -A` 추가 → staged 변경이 diff에 포함 보장 | 2026-04-06 |
| S30 | 에이전트별 예산 상한 | `harness/utils.sh` `_agent_call()`에 `--max-budget-usd 2.00` 추가. 개별 에이전트 폭주 방지 | 2026-04-06 |
| S31 | 킬 스위치 | `harness/impl-process.sh` `kill_check()` — `/tmp/{p}_harness_kill` 감지 시 즉시 `HARNESS_KILLED` 출력 후 종료. while 루프 상단 + 에이전트 호출 직전 전수 삽입. `/harness-kill` 커맨드 추가. `harness/executor.sh` EXIT trap에서 kill 파일 정리 | 2026-04-06 |
| S32 | 전체 루프 비용 상한 $10 | `harness/impl-process.sh` `budget_check()` — stream-json result 이벤트에서 `total_cost_usd` 추출 → `TOTAL_COST` 누적 → $10 초과 시 `HARNESS_BUDGET_EXCEEDED` 출력 후 종료. hlog에 에이전트별·누적 비용 기록 | 2026-04-06 |
| S27 | fast_classify() regex 즉시 분류 | `harness-router.py` fast_classify() — GREETING/QUESTION/BUG/IMPLEMENTATION 4카테고리 regex 즉시 판정, 미분류 시 LLM 폴백 | 2026-04-07 |
| S28 | _call_haiku() API 직접 호출 | `harness-router.py` _call_haiku() — urllib API 직접(5s) + claude --agent socrates CLI 폴백(10s) | 2026-04-07 |
| S33 | Stop hook 종료 차단 | `hooks/harness-stop-gate.sh` — harness_active 존재 시 exit 2. kill switch 시 즉시 허용. `settings.json` Stop hook 등록 | 2026-04-07 |
| RF1 | 5f19c2a 복원 리팩토링 | Popen 전면 제거. 라우터=분류+힌트, Claude=판단+실행 원칙 복원. S27/S28/S18/Rate Limiter/Kill Switch 선별 병합 | 2026-04-07 |
| S34 | Bash timeout 환경변수 | `settings.json` env: `BASH_DEFAULT_TIMEOUT_MS=600000`(10분), `BASH_MAX_TIMEOUT_MS=1800000`(30분) | 2026-04-07 |
| S35 | executor 경로 폴백 | `harness-router.py` — 프로젝트 `.claude/harness/executor.sh` 먼저, 없으면 `~/.claude/` 폴백 | 2026-04-07 |
| S39 | agent out_file 가드 | `harness/impl-process.sh` `check_agent_output()` — 5곳 전수 적용. `harness/utils.sh` out_file 사전 touch | 2026-04-07 |
| S40 | rollback_attempt | `harness/impl-process.sh` `rollback_attempt()` — 실패 시 `git stash push --include-untracked`. 5곳 실패 분기 적용 | 2026-04-07 |
| S45 | JSONL 로그 보강 | `harness/utils.sh` agent_stats(tools/files_read) + `harness/impl-process.sh` decision/phase/context/config/rollback/commit 이벤트. prompt_chars 추적 | 2026-04-07 |
| S46 | /harness-review 스킬 | `scripts/harness-review.py` JSONL 파서 + 8개 WASTE 패턴 진단. `commands/harness-review.md` 스킬. old/new 로그 포맷 호환 | 2026-04-07 |
| S47 | HARNESS_DONE 후 자동 리뷰 | `orchestration-rules.md` 정책 10 — HARNESS_DONE/ESCALATE/KNOWN_ISSUE 수신 후 /harness-review 자동 실행 | 2026-04-07 |
| S48 | QA 에이전트 스코프 강화 | `harness/utils.sh` `_agent_call()`에 `{prefix}_{agent}_active` 플래그 세팅/해제 → `agent-boundary.py` 물리적 차단 활성화. `qa.md` Agent/Bash 도구 제거 + 인프라 접근 금지 명시 | 2026-04-07 |
| S49 | 루프 D 라우팅 단순화 | 6타입→3타입(FUNCTIONAL_BUG/SPEC_ISSUE/DESIGN_ISSUE), 심각도 제거, QA 이슈 등록 전 경로 의무화, backlog 분기 제거 | 2026-04-07 |
| S50 | harness-review 흐름 진단 | ABNORMAL_END/EARLY_EXIT/MISSING_PHASE/ROUTING_MISMATCH 4패턴 + 모드별 예상 순서 + QA 타입 추출 + 중단 원인 힌트 | 2026-04-07 |
| S12 | 루프 C/D 재진입 상태 감지 | run_bugfix: impl→engineer직접, issue QA리포트→architect. run_impl: plan_validation_passed→engineer 루프 직접 진입. _run_bugfix_direct: impl 있으면 architect 스킵 | 2026-04-07 |
| S51 | harness-review 토큰 낭비 진단 | WASTE_CONTEXT_EXCESS(역할별 프롬프트 상한), WASTE_SPARSE_PROMPT(컨텍스트 부족→재조회), WASTE_DUPLICATE_READ(3+에이전트 동일파일) | 2026-04-07 |
| S52 | run_end result 마커 기록 | HARNESS_RESULT 환경변수 → write_run_end() result 필드. 6개 종료 경로 전수 설정. harness-review EARLY_EXIT 오탐 수정 | 2026-04-07 |
| S53 | 로그 분석 기반 5건 수정 | validator/pr/security 마커 파싱 완화(`grep -qi`), test-engineer timeout 300→600s, engineer Agent 금지, build_smart_context 소스파일 3KB캡+전체 30KB캡 | 2026-04-07 |
| S62 | 스크립트↔룰 동기화 | e32ce43 이후 6개 스크립트 오케스트레이션 룰 반영. fast pr-reviewer 제거, SPEC_GAP 핸들링, bugfix KNOWN_ISSUE/backlog, plan DV+PV 추가, design ITERATE feedback 등 | 2026-04-09 |
| S63 | utils.sh 공용 함수 추출 | `parse_marker()`, `run_plan_validation()`, `run_design_validation()` 추출. `kill_check()` `[` → `[[` 정비. impl.sh/bugfix.sh 중복 Plan Validation 코드 제거 | 2026-04-09 |
| S64 | impl-process.sh fast 모드 정정 | validator_b_passed 조건부 설정. S72로 fast 경로 재설계됨 | 2026-04-09 |
| S72 | 커밋 전략 개편 | engineer 직후 즉시 커밋(feature branch). pr-reviewer를 fast/std/deep 전체 적용. 머지 조건=pr_reviewer_lgtm 전 depth 통일. security-reviewer는 deep only 유지. pr-reviewer model opus→sonnet | 2026-04-09 |
| S65 | impl-process.sh SPEC_GAP 핸들링 | `SPEC_GAP_FOUND` → architect SPEC_GAP → 3-way 분기 (RESOLVED/PP_ESCALATION/TECH_CONSTRAINT). `spec_gap_count` 동결 카운터 (max 2, 정책 15) | 2026-04-09 |
| S66 | bugfix.sh 라우팅 정비 | `backlog` → 이슈 생성 후 대기. `KNOWN_ISSUE` → 즉시 에스컬레이션. `DESIGN_ISSUE` → 디자인 루프 전환. qa 마일스톤 규칙 정정 (Bugs only). `grep -q '...\|...'` → `grep -qE`/`-qF` | 2026-04-09 |
| S67 | plan.sh 흐름 완성 | 2단계(pp→architect) → 6단계(pp→architect SD→validator DV→architect MP→validator PV→PLAN_VALIDATION_PASS). `run_design_validation()` 공용 함수 활용 | 2026-04-09 |
| S68 | design.sh 흐름 완성 | ITERATE feedback 전달. ESCALATE 분기 추가. DESIGN_LOOP_ESCALATE 마커. `parse_marker()` 활용 | 2026-04-09 |
| S69 | 스마트 컨텍스트 공용화 + validator diff 패싱 | `build_smart_context()`, `build_validator_context()` harness/utils.sh로 이동. validator에 git diff 사전 전달 | 2026-04-09 |
| S70 | 훅 전수 감사 | `orch-rules-first.py` HARNESS_INFRA_PATTERNS 구 파일명→실제 경로 수정 + hooks/*.py 전체 포함. `harness-drift-check.py` DRIFT_MAP 5개 에이전트 매핑 추가 (designer/design-critic/product-planner/pr-reviewer/security-reviewer). `file-ownership-gate.py` 삭제 (S55에서 agent-boundary.py에 통합 완료). BATS 테스트 16건 추가 (총 115건). harness-stop-gate.sh 참조 폐기 표기 | 2026-04-09 |
| S76 | 에이전트 인프라 탐색 금지 강화 | `agents/architect.md`, `agents/engineer.md`, `agents/validator.md` Universal Preamble에 orchestration-rules.md·harness/·hooks/ 인프라 파일 Read 금지 명시. validator에 Bash 사용 절대 금지 추가. harness-review WASTE_INFRA_READ HIGH 3건 해소 | 2026-04-09 |
| S77 | harness-review INFRA 오탐 수정 | `scripts/harness-review.py` INFRA_EXCLUSIONS 상수 추가(`agent-config/`). INFRA 체크 3곳에 exclusion 적용 — 의도된 프로젝트 컨텍스트 읽기를 WASTE_INFRA_READ로 오분류하던 문제 해소 | 2026-04-09 |
| S72 | git checkout stdout 오염 + QA 타임아웃 수정 | `utils.sh` `create_feature_branch()`: 브랜치 존재 시 `git checkout`이 수정 파일 목록을 stdout 출력 → `>/dev/null 2>&1` 추가. `bugfix.sh` QA timeout 300→600s + QA exit code 체크 (타임아웃/실패 시 HARNESS_CRASH 조기 종료). `utils.sh` `_agent_call()` 완료 메시지 exit 코드 분기. `agents/qa.md` (global+project): Grep-first 전략 + Read 최대 3개/150줄 제한 + 총 도구 10회 제한. `hooks/harness-router.py` fast_classify: 발생해/아무것도 안나온/왜~거야 패턴 추가 (14/14 PASS) | 2026-04-09 |

---

## 5. 에이전트 역할 경계 매트릭스

`agent-boundary.py`가 `{p}_{agent}_active` 플래그 활성 상태에서 허용 경로 외 Write/Edit를 물리적으로 차단.

| 에이전트 | 허용 경로 | 절대 금지 |
|---|---|---|
| engineer | `src/**` (테스트 포함) | 설계 문서 수정 |
| architect | `docs/**`, `backlog.md` | `src/**` 수정 |
| designer | `design-variants/**`, `docs/ui-spec*` | architecture 계열, src, design-preview-*.html (Pencil MCP로 대체됨) |
| test-engineer | `src/__tests__/**` | src 본체 수정 |
| product-planner | `prd.md`, `trd.md` | 코드·설계 문서 |
| validator, design-critic, pr-reviewer, qa, security-reviewer | *(없음 — ReadOnly)* | 모든 Write/Edit |

## 6. 의존성 맵

```mermaid
graph TD
  User[사용자 프롬프트] --> Router[harness-router.py\nUserPromptSubmit]
  Router -->|AMBIGUOUS| Interview[Adaptive Interview\nHaiku Q&A → product-planner 힌트]
  Router -->|분류 완료| Executor[harness/executor.sh\n5모드 라우터]
  Executor -->|impl + depth 감지| Loop[harness/impl-process.sh\n구현 루프]
  Executor -->|impl| Architect[architect\nModule Plan]
  Architect --> Validator_C[validator\nPlan Validation]
  Validator_C -->|PASS| Loop
  Loop -->|fast/std/deep| Engineer[engineer\nsrc/** 구현]
  Engineer --> Commit_early[git commit\nfeature branch 즉시]
  Commit_early -->|fast| PRReviewer_fast[pr-reviewer\n코드 품질]
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
