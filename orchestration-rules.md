# 오케스트레이션 룰

모든 프로젝트에서 공통으로 적용되는 에이전트 워크플로우 규칙.
**룰 변경 시 이 파일만 수정** → 스크립트·에이전트 업데이트의 단일 기준점.

---

## 핵심 원칙

1. 메인 Claude는 src/**를 직접 수정하지 않는다 — 반드시 executor.sh 경유
2. 모든 구현은 하네스 루프를 거친다 — 예외 없음 (depth=simple로 경량화 가능)
3. 유저 게이트(READY_FOR_IMPL 등)에서 자동 진행 금지 — 승인 후 진행
4. 에스컬레이션 수신 시 자동 복구 금지 — 유저 보고 후 대기
5. 워크플로우 변경은 이 파일 먼저, 스크립트는 그 다음

---

## 루프 진입 기준 (메인 Claude)

| 상황 | 호출 |
|------|------|
| 신규 프로젝트 / PRD 변경 | → **[기획 루프](orchestration/plan.md)** |
| UI 변경 요청 | → **ux 스킬** → designer 에이전트 직접 호출 (Pencil 캔버스, 하네스 루프 없음). 상세: [orchestration/design.md](orchestration/design.md) |
| 구현 요청 (READY_FOR_IMPL 또는 plan_validation_passed) | → **[구현 루프 개요](orchestration/impl.md)** — `bash ~/.claude/harness/executor.sh impl --impl <path> --issue <N> [--prefix <P>] [--depth simple\|std\|deep]`<br>depth 상세: [simple](orchestration/impl_simple.md) / [std](orchestration/impl_std.md) / [deep](orchestration/impl_deep.md) |
| 버그 보고 | → **qa 스킬** → QA 에이전트 직접 분류 + 라우팅. 상세: [orchestration/impl.md](orchestration/impl.md) (QA/DESIGN_HANDOFF 진입 흐름 섹션)<br>FUNCTIONAL_BUG → `executor.sh impl --issue <N>` (architect LIGHT_PLAN) / DESIGN_ISSUE → ux 스��� / SCOPE_ESCALATE → 유저 보고 |
| 기술 에픽 / 리팩 / 인프라 | → **[기술 에픽 루프](orchestration/tech-epic.md)** — `bash ~/.claude/harness/executor.sh impl --impl <path> --issue <N> [--prefix <P>]` |
| **AMBIGUOUS** | → **Adaptive Interview** (Haiku Q&A → 충분하면 product-planner → 기획 루프) |

---

## 마커 안전 규칙 (Marker Safety)

에이전트 호출 후 `parse_marker()`가 **UNKNOWN**을 반환하면 (= 기대 마커 미감지):
- **진행 게이트** (다음 단계로 넘어가는 판단): UNKNOWN → **에스컬레이션** (fail-safe). 예: product-planner 마커 없음 → CLARITY_INSUFFICIENT, architect 마커 없음 → SPEC_GAP_ESCALATE
- **실패 게이트** (PASS인지 판단): UNKNOWN → **FAIL 처리** (fail-safe). 예: validator UNKNOWN → FAIL, pr-reviewer UNKNOWN → CHANGES_REQUESTED
- **재시도 게이트** (SPEC_GAP 등): UNKNOWN → **재시도** 허용 (attempt 소진). 예: architect SPEC_GAP UNKNOWN → engineer 재시도

원칙: **마커 없으면 진행 금지**. 우연히 텍스트에서 추출한 경로로 다음 단계에 진입하는 것을 방지한다.

### 에이전트 간 데이터 전달 규칙
- plan 루프에서 product-planner → architect 전환 시, **pp_out 전문을 프롬프트에 넣지 않는다**. prd.md 경로만 전달하고 architect가 직접 Read하도록 한다.
- 이유: 수만 토큰의 PRD 전문이 architect 프롬프트에 들어가면 architect가 prd.md를 자기가 다시 써야 한다고 착각해서 Bash heredoc 파일 쓰기 루프에 빠진다 (900초 타임아웃 사고 원인).

### plan 루프 타임아웃 정책
- plan 루프 Bash 호출 시 **timeout 3600000ms (60분)** 명시. 기본 20분으로는 plan loop 완주 불가.
- 에이전트별 타임아웃: product-planner 600s, architect-sd 600s, architect-mp 600s, validator 300s.
- `agent_call`에서 에이전트 frontmatter `tools:` 목록 외 도구를 `--disallowedTools`에 추가하여 불필요한 도구 사용 방지 (예: product-planner의 Bash 차단).
- `agent_call` 내부에서 30초마다 stdout heartbeat 출력 (`[HARNESS] agent 경과 Ns, tool calls: N`). 에이전트 실행 중 부모 Bash가 "조용"해지는 문제 방지.

---

## 에스컬레이션 마커 — 모두 "메인 Claude 보고 후 대기"

| 마커 | 발행 주체 | 처리 |
|------|-----------|------|
| `VARIANTS_APPROVED` | design-critic THREE_WAY 모드 (1개 이상 PASS) | 유저 PICK 안내 |
| `VARIANTS_ALL_REJECTED` | design-critic THREE_WAY 모드 (전체 REJECT) | designer 재시도 (max 3회) |
| `DESIGN_REVIEW_ESCALATE` | validator Design Validation (재검 후 재FAIL) | 메인 Claude 보고 |
| `DESIGN_ISSUE` | qa 스킬 (QA 에이전트 분류 결과) | ux ���킬 자동 진입 (COMPONENT_ONE_WAY 기본) → DESIGN_HANDOFF 후 executor.sh impl --issue <N> |
| `KNOWN_ISSUE` | qa 에이전트 (1회 분석으로 원인 특정 불가) | 메인 Claude 보고 |
| `SCOPE_ESCALATE` | qa 에이전트 (관련 모듈/파일 = 0 → 신규 기능 판정) | 메인 Claude 보고 — product-planner 라우팅 |
| `LIGHT_PLAN_READY` | architect Light Plan (버그·디자인 국소 변경) | plan_validation → depth별 루프 |
| `SPEC_MISSING` | validator Code Validation (impl 없음) | architect Module Plan 호출 |
| `PRODUCT_PLANNER_ESCALATION_NEEDED` | architect SPEC_GAP | product-planner 에스컬레이션 |
| `CLARITY_INSUFFICIENT` | product-planner (정보 부족) | 부족 항목 질문 → 유저 답변 수집 → plan 루프 재실행 (max 2회) |
| `IMPLEMENTATION_ESCALATE` | harness/impl_{simple,std,deep}.sh (3회 실패 or SPEC_GAP 동결 초과) | 메인 Claude 보고 — 복귀 옵션 제시 |
| `DESIGN_LOOP_ESCALATE` | designer (ONE_WAY: 3회 재시도 후에도 REJECT / THREE_WAY: 3라운드 후에도 VARIANTS_ALL_REJECTED) | 유저 직접 선택 |
| `TECH_CONSTRAINT_CONFLICT` | architect SPEC_GAP (기술 제약 충돌) | 메인 Claude 보고 |
| `PLAN_VALIDATION_ESCALATE` | validator Plan Validation (재검 후 재FAIL) | 메인 Claude 보고 |
| `MERGE_CONFLICT_ESCALATE` | harness/impl_{simple,std,deep}.sh / harness/executor.sh (merge 실패) | 메인 Claude 보고 |

---

## 구현 루프 내부 기능

### Handoff 문서 (에이전트 간 인수인계)
에이전트 전환 시 하네스가 자동으로 구조화된 인수인계 문서를 생성한다 (에이전트 프롬프트 변경 없음).
- 저장: `.claude/harness-state/{prefix}_handoffs/attempt-{N}/{from}-to-{to}.md`
- 적용 지점: architect→validator, validator→engineer, engineer→pr-reviewer, engineer→test-engineer, SPEC_GAP engineer→architect
- JSONL에 `{"event": "handoff", "from": ..., "to": ...}` 이벤트 로깅
- `explore_instruction()`에 `handoff_path` 파라미터 추가 — handoff 우선, 상세 로그는 필요 시만
- `harness-review.py`: handoff 이벤트 존재 시 WASTE_DUPLICATE_READ 심각도 LOW로 하향

### HUD Statusline (진행 상태 시각화)
impl/plan 전체 라이프사이클의 진행 상태를 stdout에 시각적으로 표시.
- `run_impl()` 진입 시 HUD 생성 (depth="auto", preamble: architect + plan-validation)
- `run_plan()` 진입 시 HUD 생성 (depth="plan", agents: product-planner → architect-sd → design-validation → architect-mp → plan-validation)
- depth 확정 후 `set_depth()`로 depth별 에이전트 목록 확장
- run_simple/run_std/run_deep에 `hud` 파라미터 전달 — 외부 HUD가 있으면 재사용, 없으면 자체 생성
- 재진입 경로(plan_validation_passed 플래그): preamble 없이 depth 루프가 자체 HUD 생성
- 실시간 JSON: `.claude/harness-state/{prefix}_hud.json`
- `/harness-monitor` 스킬: 별도 세션에서 HUD를 실시간 모니터링 (전용 세션, 무한 대기)
- 하네스 완료 시 HUD 파일 유지 (`"status": "done"` 필드 추가), 다음 루프 시작 시 덮어쓰기
- `_write_json` 디버그: `_hud_debug.log`에 파일 기반 진단 로그 (stdout 버퍼링 우회, 매 호출 카운트 + 파일 존재 여부 기록)

### POLISH 모드 (LGTM 후 경량 코드 다듬기)
pr-reviewer LGTM 후, merge 전에 NICE TO HAVE 항목을 경량 정리한다.
- engineer `@MODE:ENGINEER:POLISH` (180초, 기능 변경 금지)
- regression check: 하네스가 `config.lint_command` + `config.test_command` 직접 실행 (에이전트 호출 없음)
- regression 실패 → `git reset --hard`로 revert, 원본 코드로 merge (slop 있는 채로)
- NICE TO HAVE 없으면 스킵

### Circuit Breaker (시간 윈도우 반복 실패 감지)
동일 fail_type이 120초 내 2회 반복되면 attempt를 소진하지 않고 즉시 IMPLEMENTATION_ESCALATE.
- JSONL에 `circuit_breaker` 이벤트 기록
- 기존 max 3 attempts와 독립 동작 (시간 기반 조기 탈출)

### Second Reviewer v3 (외부 AI 파일별 병렬 리뷰)
pr-reviewer(Claude) 실행과 동시에 외부 AI(Gemini/GPT)를 파일별로 리뷰. threading으로 병렬 실행, 추가 대기 시간 0.
- 설정: `harness.config.json`의 `second_reviewer` (예: `"gemini"`, `"gpt"`, `""` = 비활성)
- 구현: `harness/providers.py` — BaseProvider + GeminiProvider (adapter 패턴)
- 실행: `threading.Thread`로 pr-reviewer와 병렬. `git diff HEAD~1 -- {file}`로 파일별 patch 추출 → stdin pipe로 gemini 호출 (파일당 60초)
- 2단계 프롬프트: 1차 diff만, "NEED_FULL_FILE" 시 2차 전체 파일 전달
- 결과: LGTM 시 findings → POLISH 항목 합산. CHANGES_REQUESTED 시 무시
- 결과 합산: LGTM 시 findings → POLISH 항목에 append (기존 POLISH 파이프라인 재활용)
- CHANGES_REQUESTED 시 gemini 결과 무시 (기능 수정 우선)
- 폴백: CLI 미설치/타임아웃/에러 → 조용히 스킵, 기존 파이프라인 영향 0

### Impl Scope Guard (수정 범위 물리적 차단)
engineer 구현 후 automated_checks에서 impl 파일의 `## 수정 파일` 목록과 실제 `git diff --name-only`를 대조.
- impl에 없는 파일이 변경됐으면 FAIL → engineer 재시도
- `.claude/` 등 인프라 파일은 제외 (harness가 자동 수정하는 파일)
- engineer가 impl 범위 밖을 자의적으로 수정하는 "과잉 수정" 패턴 방지

---

## 상세 문서

| 문서 | 내용 |
|------|------|
| [정책 상세](orchestration/policies.md) | 정책 1~21 전문 (그룹별 정리) |
| [이슈 컨벤션](orchestration/issue-convention.md) | GitHub 이슈 제목·본문 규칙 |
| [브랜치 전략](orchestration/branch-strategy.md) | 네이밍·머지·정리 규칙 |
| [에이전트 역할 경계](orchestration/agent-boundaries.md) | 담당·금지 + Write/Edit 매트릭스 + Pencil MCP 권한 |
| [기획 루프](orchestration/plan.md) | product-planner → architect → validator 흐름 |
| [디자인 루프](orchestration/design.md) | designer → design-critic 흐름 |
| [구현 루프 개요](orchestration/impl.md) | depth 선택 + QA/DESIGN_HANDOFF 진입 |
| [impl simple](orchestration/impl_simple.md) / [std](orchestration/impl_std.md) / [deep](orchestration/impl_deep.md) | depth별 상세 |
| [기술 에픽](orchestration/tech-epic.md) | 리팩·인프라 에픽 루프 |
| [변경 로그](orchestration/changelog.md) | 시간순 변경 이력 |

---

## 이 파일 변경 시 함께 업데이트할 대상

| 변경 내용 | 업데이트 대상 |
|-----------|---------------|
| 루프 순서 / 조건 변경 | `harness/executor.py`, `harness/{impl_router,impl_loop,helpers,plan_loop,core,config}.py`, `docs/harness-state.md` (진입점: `harness/executor.sh` → Python 래퍼) |
| 마커 추가 / 변경 | 해당 에이전트 md 파일 + 해당 루프 파일(`orchestration/*.md`) |
| 에이전트 역할 경계 변경 | 해당 에이전트 md 파일 + `orchestration/agent-boundaries.md` |
| 에이전트 추가 / 삭제 | `orchestration/agent-boundaries.md` + 해당 루프 다이어그램 + 마커 표 + 스크립트 |
| 하네스 기능 추가 / 변경 | `docs/harness-state.md` (완료/한계 섹션) + `docs/harness-backlog.md` (항목 상태) |
| config.py 필드 추가 | `harness/config.py` (필드) + `harness/impl_loop.py`/`helpers.py` (사용처) + `harness/tests/test_parity.py` (테스트) |
| 훅 패턴/매핑 변경 | `hooks/*.py` 대상 파일 + `setup-harness.sh` 주석 |
| architect @MODE 추가/변경 | `CLAUDE.md` (프로젝트) architect 호출 규칙 표 |
| 디자인 도구 변경 (Pencil MCP 등) | `agents/designer.md`, `agents/design-critic.md`, `orchestration/design.md`, `commands/ux.md` |
| 정책 추가/변경 | `orchestration/policies.md` |
| 이슈 규칙 변경 | `orchestration/issue-convention.md` |
| 브랜치 전략 변경 | `orchestration/branch-strategy.md` |
