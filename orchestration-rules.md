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
