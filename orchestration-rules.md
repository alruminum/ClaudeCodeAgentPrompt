# 오케스트레이션 룰

모든 프로젝트에서 공통으로 적용되는 에이전트 워크플로우 규칙.
**룰 변경 시 이 파일만 수정** → 스크립트·에이전트 업데이트의 단일 기준점.

## 거버넌스 — Task-ID + WHAT/WHY 로그 + 경로 기반 drift-check

판단이 섞인 변경은 **Task-ID**(`HARNESS-CHG-YYYYMMDD-NN`)를 부여하고 두 로그에 기록한다.

| 로그 | 담는 내용 | 경로 |
|------|-----------|------|
| **WHAT** | Task-ID, 날짜, 변경 파일, Exception | [`orchestration/update-record.md`](orchestration/update-record.md) |
| **WHY** | 배경·대안·결정·follow-up (판단이 섞인 변경만) | [`orchestration/rationale-history.md`](orchestration/rationale-history.md) |
| **요약 인덱스** | 시간순 한 줄 요약 (검색용) | [`orchestration/changelog.md`](orchestration/changelog.md) |

### drift-check (경로 기반 advisory 게이트)

`hooks/harness-drift-check.py`가 `git commit` 시 staged 파일을 `PATH_RULES`로 카테고리 분류하고 각 카테고리의 필수 동반 파일을 검사한다. 미충족 시 1회 deny + 5분 bypass TTL (advisory 운영).

- **의도적 예외**는 현재 커밋의 diff **추가 라인**에 다음 형식으로 명시:
  ```
  Document-Exception: HARNESS-CHG-YYYYMMDD-NN <사유>
  ```
- 과거 누적된 Exception 엔트리는 자동 무효 — 매 커밋마다 현재 diff만 파싱.
- PATH_RULES 변경 시: `hooks/harness-drift-check.py` + `orchestration/update-record.md` Change-Type 토큰 표 동기화.

---

## 핵심 원칙

1. 메인 Claude는 src/**를 직접 수정하지 않는다 — 반드시 executor.sh 경유
2. 모든 구현은 하네스 루프를 거친다 — 예외 없음 (depth=simple로 경량화 가능)
3. 유저 게이트(READY_FOR_IMPL 등)에서 자동 진행 금지 — 승인 후 진행
4. 에스컬레이션 수신 시 자동 복구 금지 — 유저 보고 후 대기
5. 워크플로우 변경은 이 파일 먼저, 스크립트는 그 다음

> **적용 범위 — 프로젝트 화이트리스트 (옵트인)**
> 위 규칙은 `~/.claude/harness-projects.json`에 **명시 등록된 프로젝트**에서만 적용된다. 전역 훅(`~/.claude/hooks/*.py`)은 모든 Claude Code 세션에서 호출되지만 `is_harness_enabled()`가 False면 조용히 no-op. 일반 코드 작업 프로젝트는 기본 disabled이므로 훅 태클 없음.
>
> 활성화: `/harness-enable` (현재 cwd 등록) · 비활성: `/harness-disable` · 목록: `/harness-list` · `setup-harness.sh` 실행 시 자동 등록.

---

## 루프 진입 기준 (메인 Claude)

| 상황 | 호출 |
|------|------|
| 신규 프로젝트 / PRD 변경 | → **[기획-UX 루프](orchestration/plan.md)** → 유저 승인 ① → **[설계 루프](orchestration/system-design.md)** → 디자인 승인 → **[구현 루프](orchestration/impl.md)** |
| UI 변경 요청 (독립) | → **ux 스킬** → designer 에이전트 직접 호출 (Pencil 캔버스, 하네스 루프 없음). 상세: [orchestration/design.md](orchestration/design.md) |
| 화면 레이아웃 리디자인 (REFINE) | → **ux 스킬** (REFINE 감지) → ux-architect(UX_REFINE) → 유저 와이어프레임 승인 → designer SCREEN 모드. 기능/플로우 변경 없이 배치·비주얼만 개편. 화면 단위만 지원. 상세: [orchestration/design.md](orchestration/design.md) |
| 구현 요청 (READY_FOR_IMPL 또는 plan_validation_passed) | → **[구현 루프 개요](orchestration/impl.md)** — `bash ~/.claude/harness/executor.sh impl --impl <path> --issue <N> [--prefix <P>] [--depth simple\|std\|deep]`<br>depth 상세: [simple](orchestration/impl_simple.md) / [std](orchestration/impl_std.md) / [deep](orchestration/impl_deep.md) |
| 버그 보고 | → **qa 스킬** → QA 에이전트 직접 분류 + 라우팅. 상세: [orchestration/impl.md](orchestration/impl.md) (QA/DESIGN_HANDOFF 진입 흐름 섹션)<br>FUNCTIONAL_BUG → `executor.sh impl --issue <N>` (architect LIGHT_PLAN) / DESIGN_ISSUE → ux 스킬 / SCOPE_ESCALATE → 유저 보고 |
| 기술 에픽 / 리팩 / 인프라 | → **[기술 에픽 루프](orchestration/tech-epic.md)** — `bash ~/.claude/harness/executor.sh impl --impl <path> --issue <N> [--prefix <P>]` |
| **AMBIGUOUS** | → **Adaptive Interview** (Haiku Q&A → 충분하면 product-planner → 기획-UX 루프) |

---

## 마커 안전 규칙 (Marker Safety)

에이전트 호출 후 `parse_marker()`가 **UNKNOWN**을 반환하면 (= 기대 마커 미감지):
- **진행 게이트** (다음 단계로 넘어가는 판단): UNKNOWN → **에스컬레이션** (fail-safe). 예: product-planner 마커 없음 → CLARITY_INSUFFICIENT, architect 마커 없음 → SPEC_GAP_ESCALATE
- **실패 게이트** (PASS인지 판단): UNKNOWN → **FAIL 처리** (fail-safe). 예: validator UNKNOWN → FAIL, pr-reviewer UNKNOWN → CHANGES_REQUESTED
- **재시도 게이트** (SPEC_GAP 등): UNKNOWN → **재시도** 허용 (attempt 소진). 예: architect SPEC_GAP UNKNOWN → engineer 재시도

원칙: **마커 없으면 진행 금지**. 우연히 텍스트에서 추출한 경로로 다음 단계에 진입하는 것을 방지한다.

### 에이전트 간 데이터 전달 규칙
- plan 루프에서 product-planner → ux-architect 전환 시, prd.md 경로만 전달. ux-architect가 직접 Read.
- 설계 루프에서 메인 Claude가 architect(SD)를 호출할 때, ux-flow.md + prd.md 경로만 전달. architect가 직접 Read.
- 설계/구현 루프에서 에이전트에 전문을 프롬프트에 넣지 않는다. 경로만 전달하고 에이전트가 직접 Read하도록 한다.
- 이유: 수만 토큰의 전문이 프롬프트에 들어가면 에이전트가 파일을 자기가 다시 써야 한다고 착각해서 Bash heredoc 파일 쓰기 루프에 빠진다 (900초 타임아웃 사고 원인).

### PRODUCT_PLAN_CHANGE 경유 시 ux-architect 재호출 조건
- 유저 승인 ① 수정 요청 시 라우팅:
  - 화면 추가/삭제 → planner(PRODUCT_PLAN_CHANGE) + ux-architect(UX_FLOW) 재실행
  - 기존 화면 내 인터랙션/플로우 변경 → ux-architect(UX_FLOW)만 재실행
  - 비기능 변경 (BM, 기술 스택 등) → planner(PRODUCT_PLAN_CHANGE)만 재실행

### 유저 승인 ① 후 이슈 동기화
- 유저 승인 ① 확정 후, 설계 루프 진입 전에 planner ISSUE_SYNC 모드를 호출하여 stories.md ↔ GitHub 이슈 동기화.
  - 새 스토리 → 이슈 생성
  - 삭제된 스토리 → 이슈 close
  - 변경된 스토리 → 이슈 body 업데이트
- ISSUE_CREATORS에 product-planner 포함 (`harness_common.py`).
- 마커: `ISSUES_SYNCED` (이슈 번호 목록 포함).
- **사전 요건 — GitHub MCP 서버 등록 필수**: ISSUE_CREATORS 에이전트(qa, designer, architect, product-planner)가 사용하는 `mcp__github__*` 도구는 MCP 서버가 실제로 등록돼있어야 동작한다. 미등록 시 호출은 silently 실패하고 메인 Claude의 `gh issue create` fallback도 `issue-gate.py`가 차단해 데드락(jajang 사례). `claude mcp list` 로 확인하고, 없으면 `setup-harness.sh` 안내대로 user scope 등록 (`claude mcp add github -s user -e GITHUB_PERSONAL_ACCESS_TOKEN=$(gh auth token) -- npx -y @modelcontextprotocol/server-github`). 등록 후 세션 재시작 필요.

### agent-gate architect 프롬프트 검증 정책
- **Mode 명시**: 의미적 키워드(`SYSTEM_DESIGN` / `MODULE_PLAN` / `SPEC_GAP` / `TASK_DECOMPOSE` / `TECH_EPIC` / `LIGHT_PLAN` / `DOCS_SYNC`)를 **권장**한다. 알파벳 표기(Mode A-G)는 deprecate — 의미 전달이 약하고 추가될 때마다 재할당 필요하므로 사용 금지. 누락 시 훅은 `stderr` 경고만 남기고 통과 — 에이전트 본문의 "모드 미지정 시 입력 내용으로 판단" 규칙에 위임한다.
- **이슈 번호 면제**: 아래 모드는 `#NNN` 없이 호출 가능.
  - `SYSTEM_DESIGN`: 전체 구조 설계, 특정 이슈 귀속 아님.
  - `TASK_DECOMPOSE`: 이슈를 생성하는 역할.
  - `TECH_EPIC`: 기술 에픽 초안, 이슈 선행 생성 아님.
  - `LIGHT_PLAN`: qa/외부 경로에서 이슈 자동 주입 가능.
  - `DOCS_SYNC`: impl 이미 완료 상태라 이슈 번호 무의미.
- engineer 는 예외 없이 `#NNN` 필요 (impl 파일 메타 추적).

### SPEC_GAP 화면 구조 변경 에스컬레이션
- SPEC_GAP에서 화면 구조 변경이 필요하다고 판단되면 (새 화면 추가, 화면 간 플로우 변경):
  - architect가 직접 처리하지 않고 `UX_FLOW_ESCALATE` 경로로 에스컬레이션
  - 메인 Claude가 ux-architect 재호출 여부를 판단

### 에이전트 간 handoff 전달 규칙
- 에이전트 전환 시 하네스가 handoff 문서를 생성해 경로만 다음 에이전트에게 전달한다 (전문 인라인 금지).
- 적용 지점: architect→validator, validator→engineer, test-engineer→engineer(TDD), engineer→pr-reviewer, SPEC_GAP engineer→architect.

### plan 루프 재개성
- plan_loop 진입 시 기존 산출물(prd.md, ux-flow.md, architecture.md, stories.md) 존재 여부를 확인해 미완성 단계부터 재개한다.

### architect Module Plan 호출 규칙
- System Design 출력의 design_doc는 `docs/architecture*.md` 패턴 우선 매칭.
- 단일 모듈이면 MODULE_PLAN, 다중 모듈(impl 3개 이상)이면 TASK_DECOMPOSE.

---

## 에스컬레이션 마커 — 모두 "메인 Claude 보고 후 대기"

| 마커 | 발행 주체 | 처리 |
|------|-----------|------|
| `UX_FLOW_READY` | ux-architect (UX Flow Doc 완성) | 기획-UX 루프에서 validator(UX) 호출 |
| `UX_REFINE_READY` | ux-architect (UX_REFINE — 리디자인 와이어프레임 완성) | 유저 와이어프레임 승인 → designer SCREEN 모드 호출 |
| `UX_FLOW_ESCALATE` | ux-architect (PRD 범위 초과/모순) | 메인 Claude 보고 — planner 재호출 또는 유저 판단 |
| `PLAN_REVIEW_PASS` | plan-reviewer (PRD 기반 8차원 판단 게이트 통과) | ux-architect 호출 |
| `PLAN_REVIEW_CHANGES_REQUESTED` | plan-reviewer (PRD 단계 FAIL — 현실성/MVP/BM/기술 실현성 등) | 메인 Claude가 피드백 유저 전달 → 유저 결정(수정/override/취소). **UX Flow 생성 전이라 재작업 비용 최소** |
| `UX_REVIEW_PASS` | validator UX Validation (UX Flow Doc 검증 통과) | 유저 승인 ① 게이트 |
| `UX_REVIEW_FAIL` | validator UX Validation (UX Flow Doc 검증 실패) | ux-architect 재설계 (max 1회) |
| `UX_REVIEW_ESCALATE` | validator UX Validation (재검 후 재FAIL) | 메인 Claude 보고 |
| `VARIANTS_APPROVED` | design-critic THREE_WAY 모드 (1개 이상 PASS) | 유저 PICK 안내 |
| `VARIANTS_ALL_REJECTED` | design-critic THREE_WAY 모드 (전체 REJECT) | designer 재시도 (max 3회) |
| `DESIGN_REVIEW_ESCALATE` | validator Design Validation (재검 후 재FAIL) | 메인 Claude 보고 |
| `DESIGN_ISSUE` | qa 스킬 (QA 에이전트 분류 결과) | ux 스킬 자동 진입 (COMPONENT_ONE_WAY 기본) → DESIGN_HANDOFF 후 executor.sh impl --issue <N> |
| `KNOWN_ISSUE` | qa 에이전트 (1회 분석으로 원인 특정 불가) | 메인 Claude 보고 |
| `SCOPE_ESCALATE` | qa 에이전트 (관련 모듈/파일 = 0 → 신규 기능 판정) | 메인 Claude 보고 — product-planner 라우팅 |
| `LIGHT_PLAN_READY` | architect Light Plan (버그·디자인 국소 변경) | plan_validation → depth별 루프 |
| `SPEC_MISSING` | validator Code Validation (impl 없음) | architect Module Plan 호출 |
| `PRODUCT_PLANNER_ESCALATION_NEEDED` | architect SPEC_GAP | product-planner 에스컬레이션 |
| `ISSUES_SYNCED` | product-planner ISSUE_SYNC (이슈 동기화 완료) | 설계 루프 진입 (architect SD + designer 병렬) |
| `CLARITY_INSUFFICIENT` | product-planner (정보 부족) | 부족 항목 질문 → 유저 답변 수집 → plan 루프 재실행 (max 2회) |
| `IMPLEMENTATION_ESCALATE` | harness/impl_{simple,std,deep}.sh (3회 실패 or SPEC_GAP 동결 초과) | 메인 Claude 보고 — 복귀 옵션 제시 |
| `DESIGN_LOOP_ESCALATE` | designer (ONE_WAY: 3회 재시도 후에도 REJECT / THREE_WAY: 3라운드 후에도 VARIANTS_ALL_REJECTED) | 유저 직접 선택 |
| `TECH_CONSTRAINT_CONFLICT` | architect SPEC_GAP (기술 제약 충돌) | 메인 Claude 보고 |
| `PLAN_VALIDATION_ESCALATE` | validator Plan Validation (재검 후 재FAIL) | 메인 Claude 보고 |
| `MERGE_CONFLICT_ESCALATE` | harness/impl_{simple,std,deep}.sh / harness/executor.sh (merge 실패) | 메인 Claude 보고 |

---

## 구현 루프 내부 기능

### 세션 격리 (Phase 3)
`.claude/harness-state/` 는 세션 스코프. 훅·하네스·스킬이 `live.json` 단일 소스로 활성 에이전트/이슈를 판별한다. 상세 설계(디렉토리 구조, atomic write, ownership 검증, 이슈 lock, stale cleanup, session_id 전파 체인)는 **[docs/session-isolation/phase3-session-isolation.md](docs/session-isolation/phase3-session-isolation.md)** 참조.

규칙 수준의 핵심만 나열:
- 상태 디렉토리는 모두 dot-prefixed(숨김) — 에이전트 glob/rm 사고 방지.
- 활성 에이전트 판정은 `session_state.active_agent(stdin_data)` 하나로만. 별도 폴백/TTL 로직 추가 금지.
- 워크플로우 플래그는 세션 × 이슈 스코프에만 기록. 전역 신호(`harness_kill`)만 `.global.json`에 기록.
- 두 세션이 같은 이슈를 동시 진입 시 후발 세션 거부 (이슈 lock — PID alive + heartbeat TTL).

### Ralph 세션 격리 (스킬 교차오염 방지)
ralph 스킬이 `/tmp/ralph_task_*.md`, `/tmp/ralph_{slug}_progress.md`를 글로벌 경로에 쓰면 세션 A의 루프가 세션 B의 transcript/progress를 claim하는 사고가 난다. 모든 ralph 작업 파일은 세션 스코프에만 둔다.
- 경로: `.sessions/{sid}/ralph/{task.md, progress.md, state.json}` — `session_state.ralph_{dir,task_path,progress_path,state_path}` 헬퍼로만 접근.
- SID 획득 우선순위: `HARNESS_SESSION_ID` env → `.session-id` 포인터. **둘 다 없을 때 `_global` 공유 슬롯으로 폴백 금지** — 프로세스 고유 `_pid-<pid>-<ts>` 슬롯 사용(재발 경로 차단).
- 오피셜 `ralph-loop@claude-plugins-official` stop-hook은 전역 스크립트라 직접 수정하지 않는다. 선행 훅(`~/.claude/hooks/ralph-session-stop.py`)이 `.claude/ralph-loop.local.md`에 `cc_session_id` 필드를 기록해 교차 claim 시 경고만 출력. 완전 차단은 Phase 4 T1에서 처리.

### 플러그인 디렉토리 직접 수정 금지
`~/.claude/plugins/{cache,marketplaces,data}/**`는 CC 플러그인 매니저가 관리하는 영역. 유저 스킬/커맨드/에이전트 파일을 이 안에 추가하거나 오피셜 플러그인 파일을 손으로 고치면 재설치 시 증발하거나 원본과 drift가 생겨 추적 불가능한 오염을 남긴다.
- 유저 스킬/커맨드는 `~/.claude/commands/*.md`에만 둔다.
- 에이전트 프로젝트 컨텍스트는 `.claude/agent-config/*.md`에 둔다.
- 오피셜 플러그인 버그는 그 안의 파일을 손대지 말고 `~/.claude/hooks/`에 선행 훅을 추가해 우회한다.
- `plugin-write-guard.py`가 PreToolUse(Write/Edit)에서만 물리적으로 차단한다 — **플러그인 안의 스크립트 실행(Bash)은 정상이며 차단 대상 아님**. 예외 편집이 꼭 필요하면 `CLAUDE_ALLOW_PLUGIN_EDIT=1` env로 일시 허용.

### 스킬 컨텍스트 보호 (Phase 4)
`/ux`, `/qa`, `/product-plan`, `/ralph` 같은 스킬이 다중 에이전트를 부르거나 장시간 루프를 돌 때, 훅이 "지금 어떤 스킬이 활성인지" 모르면 정당한 Bash/Edit를 오인 차단하거나 Stop 훅이 조기 종료시키는 사고가 난다. Phase 3 `live.json` 위에 `skill` 필드를 얹어 해결한다. 상세: **[docs/session-isolation/phase4-skill-context-protection.md](docs/session-isolation/phase4-skill-context-protection.md)**.
- 상태 스키마: `live.json.skill = {name, level, started_at, reinforcements}`. 레벨 매핑은 `hooks/skill_protection.SKILL_LEVELS`(SSoT) — `get_skill_level(name)` 호출. 매핑 없는 스킬은 `DEFAULT_LEVEL = light`(보수적 보호).
- 보호 레벨 정책(OMC 벤치마크): **none** 0/0, **light** 300s/3회, **medium** 900s/5회, **heavy** 1800s/10회. 모두 `LEVEL_POLICIES` dict 한 곳에서 변경.
- 기록 단일 진입점: `hooks/skill-gate.py`(PreToolUse Skill).
- 청소 책임자(분산 금지 — OMC `cancel-skill-active-state-gap` 학습):
  - none/light/medium → `hooks/post-skill-flags.py`(PostToolUse Skill) 즉시 청소.
  - heavy → PostToolUse가 청소하지 **않음**. `hooks/skill-stop-protect.py`(Stop 훅)가 TTL/max_reinforcements/`harness_kill` 신호로 lifecycle 관리.
- Stop 훅 동작: 활성 스킬이 medium/heavy면 `{decision: block, reason: ...}`로 차단 + reinforcements +1. `reinforcements >= max` 또는 `age >= ttl`이면 강제 청소 + 통과. 모든 결정은 `.claude/harness-state/.logs/skill-protect.jsonl`에 박제.
- **자체 lifecycle 관리 스킬 예외** (`SELF_MANAGED_LIFECYCLE`): `ralph-loop:ralph-loop`처럼 자기 stop-hook이 prompt 재주입으로 다음 iteration을 트리거하는 스킬은 Stop 차단을 하면 그 재주입이 막혀 루프가 망가진다. heavy로 등록은 하되 `should_block_stop()`에서 항상 False — 차단하지 않고 자체 메커니즘에 위임. 우리 wrapper인 `ralph` 스킬은 차단 대상(자기 lifecycle 관리 메커니즘 없음).
- 중첩 스킬: last-write-wins(스택 비스코프). `clear_active_skill(expect_name=...)`로 race 방지.
- `/harness-kill` 등 전역 kill 신호 — `skill-stop-protect.py`가 1순위로 처리, 즉시 청소 후 통과.
- 활성 스킬 판정은 `session_state.active_skill(stdin_data)` 하나 — `active_agent`와 대칭. 별도 폴백/TTL 로직 추가 금지.
- 다른 훅의 적응:
  - `agent-boundary.py` 메인 Claude 경로 deny 메시지에 `(스킬 '<이름>' 진행 중)` 컨텍스트 부착 → 유저가 원인 즉시 파악.
  - `harness-router.py`는 활성 스킬이면 라우팅 힌트 주입 억제(스킬이 자체 라우팅 담당).
  - `orch-rules-first.py`는 활성 스킬이면 경고 톤 완화(스킬 안에서 시스템 파일 정당하게 손대는 경우 흔함).

#### Phase 4 잔여 TODO 처리 결과
- T1 오피셜 ralph-loop claim 가로채기 → **해결**. ralph-session-stop이 state.session_id에 시작자 SID 또는 placeholder를 박아 오피셜의 격리 분기를 발동시킨다 (`stop-hook.sh:31-35`). 시작자 식별은 `live.json.skill.name == "ralph-loop:ralph-loop"` 신뢰. 검증: `test_ralph_isolation.py` 8 tests.
- T2 plugin-write-guard와 ralph state 파일 → 자동 해소. T1 해결로 state 파일이 첫 Stop부터 격리되므로 별도 우회 불필요.
- T3 ralph 교차오염 진단 → `.claude/harness-state/.logs/ralph-cross-session.jsonl` 박제(`ralph-session-stop.py`). claim_self / claim_block_pending / claim_promote / cross_session_state_attempt 4종 이벤트.
- T4 `_pid-<pid>-<ts>` 폴백 슬롯 청소 → 활성 PID 보존, 죽은 PID 즉시 제거 (`session_state.cleanup_stale_sessions`).

### 이슈별 Worktree 격리 (동시 이슈 작업)
`config.isolation = "worktree"` 설정 시, 이슈별 git worktree를 생성하여 동시에 여러 이슈를 작업할 수 있다.
- worktree 경로: `{project_root}/.worktrees/{prefix}/issue-{N}/`. 각 에이전트는 해당 worktree에서 실행.
- 이슈별 PID 잠금 + `HARNESS_ISSUE_NUM` env로 훅이 이슈별 플래그 디렉토리 참조.
- merge 성공 후 자동 정리. `config.isolation` 미설정 시 기존 단일 worktree 동작 유지.
- **주의**: `claude` CLI에 `--isolation` 플래그는 존재하지 않는다. `cwd` 전달로만 격리 구현 — CLI 옵션으로 전달 시 에이전트 즉시 실패.

### 에이전트 Read 제한 (READ_DENY_MATRIX)
agent-boundary.py가 에이전트별 Read 접근을 제한한다. Write/Edit 허용 경로와 별개.
- product-planner: src/** 읽기 금지 (기획자가 코드 레벨 결정을 하는 것 방지)
- designer: src/** 읽기 금지 (디자인은 Pencil 캔버스 + 스펙 문서 기반)
- test-engineer: docs/ domain 문서 읽기 금지 (impl + src만 참조)
- plan-reviewer: src/**, docs/impl/**, trd.md 읽기 금지. `docs/sdk.md`·`docs/reference.md`·`docs/architecture.md`는 **허용** (기술 실현성 판단용 외부 기술 사실). TRD 금지 사유는 planner와 동일 — architect 내부 결정이 역방향으로 기획을 오염시키는 것 방지.
- 공통: .claude/harness* 인프라 파일 금지 (기존 HARNESS_INFRA_PATTERNS)

### ux-architect Pencil MCP 읽기 접근
UX_REFINE 모드에서 현재 디자인을 분석하기 위해 Pencil MCP 읽기 도구를 사용한다.
- 허용: get_editor_state, batch_get, get_screenshot, get_variables
- 금지: batch_design (쓰기는 designer 전용)
- UX_FLOW/UX_SYNC 모드에서도 읽기 도구 사용 가능 (기존 텍스트 와이어프레임이 주력이지만 참고용 읽기는 허용)
- frontmatter tools에 Pencil 읽기 도구 포함됨 → agent-boundary.py 별도 설정 불필요

### UX_REFINE 모드 제약 (src/ 금지 + Pencil 호출 상한)
UX_REFINE 모드에서 Stream idle timeout(~11분)을 방지하기 위해 아래를 강제한다. hook 차단 없이 에이전트 자율 규약으로 운영.
- **src/ 코드 읽기 금지**: *.ts/*.tsx/*.js/*.jsx 등 구현 코드 Read/Glob/Grep 금지. UX_REFINE은 시각 레이아웃만 개편하므로 코드 동작 분석 불필요.
- **Pencil MCP 호출 상한**: get_editor_state 1회 + batch_get 1회(screen_node_id 루트, readDepth ≤ 3) + get_screenshot 1회 + get_variables 1회. 동일 노드 재조회·readDepth 4 이상 금지.
- 정보 부족 시 추가 조회 대신 UX_FLOW_ESCALATE.
- 근거: 실측에서 첫 호출 699s(timeout), 제약 포함 retry 219s. 약 3배 차이.

### 에이전트 도구 차단 매트릭스 (_AGENT_DISALLOWED)
`harness/core.py`의 `agent_call()`이 claude CLI를 `bypassPermissions` 모드로 실행하므로 frontmatter `tools:`가 무시된다. 따라서 `_AGENT_DISALLOWED` 매트릭스에서 에이전트별로 명시 차단해야 안전하다.

| 에이전트 | 차단 도구 | 사유 |
|---|---|---|
| product-planner | Agent, Bash, NotebookEdit | 기획자가 시스템 명령 실행 금지 |
| validator | Agent, Bash, Write, Edit, NotebookEdit | ReadOnly 검증 |
| pr-reviewer | Agent, Bash, Write, Edit, NotebookEdit | ReadOnly 리뷰 |
| design-critic | Agent, Bash, Write, Edit, NotebookEdit | ReadOnly 심사 |
| security-reviewer | Agent, Bash, Write, Edit, NotebookEdit | ReadOnly 보안 |
| plan-reviewer | Agent, Bash, Write, Edit, NotebookEdit | ReadOnly 판단 (기획팀장 포지션 — PRD+UX Flow 현실성/균형 심사) |
| **qa** | Agent, Bash, Write, Edit, NotebookEdit | ReadOnly 분류 — 시스템 명령 금지 |
| **ux-architect** | Agent, Bash, NotebookEdit, Pencil 쓰기 7종 (batch_design, set_variables, open_document, find_empty_space_on_canvas, snapshot_layout, export_nodes, replace_all_matching_properties, search_all_unique_properties, get_guidelines) | 캔버스 쓰기는 designer 전용. ux-architect는 Pencil 읽기 4종(get_editor_state, batch_get, get_screenshot, get_variables)만. |
| **engineer** | Agent, NotebookEdit, Pencil 쓰기 7종 | 디자인 핸드오프 참조용 읽기만 허용. 캔버스 수정 금지. Bash는 빌드/테스트 필요해 유지. |
| **test-engineer** | Agent, Bash, NotebookEdit | 테스트 실행은 하네스가 직접 vitest 호출 — test-engineer는 작성만. agent.md "테스트 실행 금지" 명시. |
| **architect** | Agent, Bash, NotebookEdit | architect는 Read/Write/Edit + gh + Pencil 읽기로 충분. 본문에 Bash 사용 지시 없음. |
| designer | Agent (기본만) | gh 이슈 생성에 Bash 필요 — 유지 |

근거: ux-architect/engineer는 frontmatter에 Pencil 읽기 도구만 있는데 bypassPermissions에서 batch_design 등 쓰기 도구 호출 가능. designer 전용 캔버스를 다른 에이전트가 수정하는 경계 위반 방지.

### UX_SYNC_INCREMENTAL 모드 (드리프트 부분 패치)
- 기존 `ux-flow.md` 를 보존하며 변경 화면 섹션만 교체한다. 전체 재생성은 UX_SYNC 모드를 사용.
- 입력: `ux_flow_path` + `changed_files` (post-commit 훅이 감지한 UX 영향 파일 목록) + `src_dir`.
- 출력 마커: `UX_FLOW_PATCHED` (성공) / `UX_FLOW_ESCALATE` (드리프트 >50% 또는 오감지).
- 트리거: `post-commit-scan.sh` 가 UX 영향 파일 (`*Screen.tsx`, `*Page.tsx`, `routes/**`, `screens/**`, 라우터 설정) 변경 감지 시 `{state_dir}/{prefix}_ux_flow_drift` 플래그 생성 (STATE_DIR 최상위 — `.flags/` 서브디렉토리는 `migrate_legacy_flags` 가 매 세션 비우므로 부적합). SessionStart 훅이 플래그 읽어 유저에게 알림. `/ux-sync` 스킬이 플래그 소비해 INCREMENTAL 호출.
- SessionStart cleanup 예외: `session-start.py` PRESERVE_SUFFIXES 에 `_ux_flow_drift`, `_ux_sync_in_progress`, `_plan_metadata.json`, `_plan_review_override` 포함. 다른 플래그는 세션 시작 시 정리됨. plan_metadata/review_override는 세션 간 체크포인트(같은 기획 이어서 작업)가 유효해야 하므로 보존.
- Edit 툴로 섹션 단위 교체. Write 전체 덮어쓰기 금지 — 기존 PRD 맥락·결정 로그 보존 목적.
- **중복 실행 방지 (soft lock)**: `/ux-sync` 는 ux-architect 호출 직전 `{prefix}_ux_sync_in_progress` 센티널 파일을 생성하고, 성공/ESCALATE 어느 쪽이든 종료 시 삭제한다. SessionStart 훅은 드리프트 플래그 + 센티널 둘 다 있으면 "다른 세션에서 진행 중 — 중복 실행 비권장" 안내로 메시지를 변경. 강제 차단이 아니라 유저 판단용 안내 (하나의 유저가 2개 세션을 동시에 쓰는 드문 시나리오 대비).

### UX_REFINE 출력 규칙 (원문 echo + 절대경로)
UX_REFINE 완료 시 메인 Claude가 재요약 없이 유저에게 전달할 수 있도록 아래를 강제.
- ux-flow.md 해당 화면 섹션(`### SXX`부터 다음 `### ` 직전까지)을 마커 출력부에 **원문 그대로 echo**.
- 모든 문서 경로는 **절대경로** (예: `/Users/.../docs/ux-flow.md`). 상대경로 금지 — 터미널 클릭 가능성 확보.
- ux 스킬(commands/ux.md) REFINE 라우팅도 동일 — 요약·테이블 압축 금지, 원문 ASCII 와이어프레임 + 리디자인 노트 테이블 통째로 노출.

### TDD 게이트 (std/deep)
attempt 0 + `test_command` 설정 시 test-engineer가 테스트를 선작성(RED)한 뒤 engineer가 구현(GREEN). attempt 1+ 에서는 test-engineer 스킵. simple depth 적용 안 됨. 마커: `TESTS_WRITTEN`.

### 듀얼 모드 — 디자인 토큰 우선 구현 (Pencil 시안 미도착 + UX Flow 디자인 가이드 존재)

`docs/ux-flow.md`에 §0 디자인 가이드(컬러·타이포·UI 패턴)가 있고 `docs/design-handoff.md`(Pencil 시안)는 아직 없는 상태에서 UI 구현을 진행하는 경우(=듀얼 모드), **디자인 시안 도착 후 컴포넌트를 갈아엎지 않도록** 토큰 우선 가드레일을 강제한다.

판정 조건 (3개 모두 충족):
1. `docs/ux-flow.md` 에 `## 0. 디자인 가이드` 섹션 존재
2. `docs/design-handoff.md` 미존재 (Pencil 시안 아직 안 받음)
3. impl 파일이 UI 컴포넌트(*.tsx 화면·뷰)를 만드는 작업

가드레일:
- **architect TASK_DECOMPOSE**: 첫 번째 impl을 `01-theme-tokens.md`로 강제 (`src/theme/colors.ts`, `typography.ts`, `spacing.ts`, `index.ts`). ux-flow §0 디자인 가이드 토큰을 추상 키로 노출.
- **architect MODULE_PLAN** (UI 컴포넌트 impl만): `## 의존성`에 `src/theme/` 명시 + 인터페이스/수용 기준에서 직접 색·폰트·간격 리터럴 사용 금지 명시.
- **engineer**: `src/theme/` 존재 시 색은 `theme.colors.*`, 폰트는 `theme.typography.*`, 간격은 `theme.spacing.*` 경유 강제. 직접 hex/rem/font-name 박기 금지. 자가 검증 grep 0건.
- **새 토큰 키 필요**: engineer 임의 추가 금지 → architect SPEC_GAP 보고.

근거: 디자인 시안 도착 시 토큰값만 patch하면 컴포넌트 변경 0. 시안 늦어도 wall-clock 단축. 핸드오프 받으면 토큰 diff만 추출 → 1차 머지 → 화면별 미세 조정. 상세: `agents/architect/task-decompose.md`, `agents/architect/module-plan.md`, `agents/engineer.md`의 듀얼 모드 섹션.

### POLISH 모드 (LGTM 후 경량 정리)
pr-reviewer LGTM 후 merge 전에 engineer가 NICE TO HAVE 항목만 경량 정리 (기능 변경 금지). lint/test regression 실패 시 수정 파일만 선택적 revert.

### Impl Scope Guard
engineer 구현 후 impl 파일의 `## 수정 파일` 목록과 실제 diff를 대조해, 목록 밖 수정이 있으면 FAIL → 재시도. 하네스 인프라 파일은 제외.

### Autocheck 실패 피드백
engineer 재시도 시 실패 로그를 task에 포함해야 한다 (에러 없이 반복 시 서킷 브레이커 유발).

### Lint/Build/Test 게이트
automated_checks에 lint/build/test 실행. `config.lint_command` / `config.build_command` / `config.test_command` 미설정 시 각각 스킵.
- **실행 순서**: scope_guard → lint → build → test (simple depth 한정).
- **test 분기**: `run_automated_checks(run_tests=True)`는 depth=simple 경로에서만 호출 — test-engineer/TDD GREEN이 스킵되는 유일한 depth라 여기서 회귀를 잡아야 한다. std/deep는 GREEN 단계에서 test_command 별도 실행하므로 automated_checks에서는 test 생략(중복 회피).
- pre-existing 에러와 구분하기 위해 engineer 수정 파일 스코프로 축소하는 옵션 제공 (lint).

### depth 분류 — DOM/텍스트 assertion 예외
architect가 LIGHT_PLAN/Module Plan에서 depth를 고를 때, **기존 테스트(`__tests__`)가 assertion하는 DOM 구조·텍스트 리터럴·testid·role을 바꾸는 변경은 simple로 분류 금지 — std로 승격**.
- 이유: simple은 test-engineer TDD 선행이 스킵돼 기존 테스트 회귀를 잡지 못한다. DOM/텍스트 변경(이모지→SVG, 버튼 텍스트 교체, 엘리먼트 구조 변경)은 거의 항상 기존 스냅샷/쿼리 테스트를 깬다.
- 판단: impl 작성 전 `grep -rl "<변경 심볼|텍스트 리터럴>" src/**/__tests__` 로 touched 파일을 assertion하는 테스트 존재 여부 확인.
- 기록: `agents/architect.md`, `impl_router.py`(`ensure_depth_frontmatter` + LIGHT_PLAN 프롬프트) 세 곳에 명시.

---

## 상세 문서

| 문서 | 내용 |
|------|------|
| [정책 상세](orchestration/policies.md) | 정책 1~21 전문 (그룹별 정리) |
| [이슈 컨벤션](orchestration/issue-convention.md) | GitHub 이슈 제목·본문 규칙 |
| [브랜치 전략](orchestration/branch-strategy.md) | 네이밍·머지·정리 규칙 |
| [에이전트 역할 경계](orchestration/agent-boundaries.md) | 담당·금지 + Write/Edit 매트릭스 + Pencil MCP 권한 |
| [기획-UX 루프](orchestration/plan.md) | planner → ux-architect → validator(UX) → 유저 승인 ① |
| [설계 루프](orchestration/system-design.md) | architect(SD) + designer 병렬 → validator(DV) → 디자인 승인 |
| [디자인 루프](orchestration/design.md) | designer 2×2 매트릭스 (Pencil, ux 스킬 독립 경로) |
| [구현 루프 개요](orchestration/impl.md) | depth 선택 + QA/DESIGN_HANDOFF 진입 |
| [impl simple](orchestration/impl_simple.md) / [std](orchestration/impl_std.md) / [deep](orchestration/impl_deep.md) | depth별 상세 |
| [기술 에픽](orchestration/tech-epic.md) | 리팩·인프라 에픽 루프 |
| [변경 로그](orchestration/changelog.md) | 시간순 변경 이력 |

---

## 이 파일 변경 시 함께 업데이트할 대상

| 변경 내용 | 업데이트 대상 |
|-----------|---------------|
| 루프 순서 / 조건 변경 | `harness/executor.py`, `harness/{impl_router,impl_loop,helpers,plan_loop,core,config}.py`, `docs/harness-state.md` (진입점: `harness/executor.sh` → Python 래퍼) |
| 마커 추가 / 변경 | 해당 에이전트 md 파일 + 해당 루프 파일(`orchestration/*.md`) + `harness/core.py` Marker enum |
| 에이전트 역할 경계 변경 | 해당 에이전트 md 파일 + `orchestration/agent-boundaries.md` |
| 에이전트 추가 / 삭제 | `orchestration/agent-boundaries.md` + 해당 루프 다이어그램 + 마커 표 + 스크립트 + `CLAUDE.md` 수정 금지 테이블 |
| UX 흐름 / 화면 구조 변경 | `agents/ux-architect.md` + `orchestration/plan.md` + `orchestration/design.md` |
| 하네스 기능 추가 / 변경 | `docs/harness-state.md` (완료/한계 섹션) + `docs/harness-backlog.md` (항목 상태) |
| config.py 필드 추가 | `harness/config.py` (필드) + `harness/impl_loop.py`/`helpers.py` (사용처) + `harness/tests/test_parity.py` (테스트) + `orchestration/changelog.md` (변경 로그) + `setup-harness.sh` (기본 템플릿) |
| 훅 패턴/매핑 변경 | `hooks/*.py` 대상 파일 + `setup-harness.sh` 주석 |
| 세션 상태 스키마 변경 (live.json 필드 등) | `hooks/session_state.py` (API) + `hooks/tests/test_session_state.py` (테스트) + `docs/session-isolation/phase3-session-isolation.md` (설계) + orchestration-rules.md 세션 격리 섹션 |
| 스킬 보호 레벨 매핑 변경 (신규 스킬 추가/제거 등) | `hooks/skill_protection.py` (SKILL_LEVELS / LEVEL_POLICIES) + `hooks/tests/test_skill_protection.py` (테스트) + orchestration-rules.md "스킬 컨텍스트 보호" 섹션 + `docs/session-isolation/phase4-skill-context-protection.md` |
| 스킬 훅 추가/변경 (skill-gate / post-skill-flags / skill-stop-protect) | 해당 훅 파일 + `~/.claude/settings.json` Skill/Stop 매처 + `~/.claude/setup-harness.sh` 주석 + `hooks/tests/test_skill_hooks.py` |
| agent-boundary.py ALLOW_MATRIX 변경 | `hooks/agent-boundary.py` + `orchestration/agent-boundaries.md` 동기 |
| architect @MODE 추가/변경 | `CLAUDE.md` (프로젝트) architect 호출 규칙 표 |
| 디자인 도구 변경 (Pencil MCP 등) | `agents/designer.md`, `agents/design-critic.md`, `orchestration/design.md`, `commands/ux.md` |
| 정책 추가/변경 | `orchestration/policies.md` |
| 이슈 규칙 변경 | `orchestration/issue-convention.md` |
| 브랜치 전략 변경 | `orchestration/branch-strategy.md` |
