# 에이전트 역할 경계

에이전트별 담당·금지 영역 + PreToolUse 훅 agent-boundary.py 매트릭스. hooks/agent-boundary.py가 참조.

---

## 역할 경계

| 에이전트 | 담당 | 절대 금지 |
|----------|------|-----------|
| architect | 설계 문서 · impl 파일 작성 | src/** 수정 |
| engineer | 소스 코드 구현 | 설계 문서 수정, Agent 도구 사용 |
| validator | PASS/FAIL 판정 리포트 | 파일 수정 |
| designer | 2×2 포맷 매트릭스 기반 variant 생성 (SCREEN/COMPONENT × ONE_WAY/THREE_WAY), DESIGN_HANDOFF 패키지 출력. ux 스킬이 직접 호출 — 하네스 루프 밖 | src/** 수정, 코드 생성 |
| design-critic | PICK/ITERATE/ESCALATE 판정 | 파일 수정 |
| qa | 원인 분석 + 라우팅 추천 | 코드·문서 수정 |
| ux-architect | UX Flow Doc 작성 (화면 구조·플로우·인터랙션) | 시각 디자인, 시스템 설계, 코드 작성, Pencil MCP |
| product-planner | PRD/TRD 작성 | 코드·설계 문서 수정 |
| test-engineer | 테스트 코드 작성 (TDD: impl 기반 선작성, 실행은 하네스) | 소스 수정, 테스트 실행 |
| pr-reviewer | 코드 품질 리뷰 | 파일 수정 |
| security-reviewer | OWASP+WebView 보안 감사 | 파일 수정 |

## Write/Edit 허용 경로 매트릭스 (물리적 강제)

PreToolUse 훅 `agent-boundary.py`가 아래 매트릭스를 물리적으로 차단한다.
`{agent}_active` 플래그가 활성화된 상태에서 허용 경로 외 파일을 Write/Edit하면 deny.

| 에이전트 | 허용 경로 | 비고 |
|----------|-----------|------|
| engineer | `src/**` | 테스트 포함 |
| architect | `docs/**`, `backlog.md` | impl 파일 포함 |
| designer | `design-variants/**`, `docs/ui-spec*` | architecture 계열 금지. design-preview-*.html 제거 (Pencil MCP로 대체) |
| test-engineer | `src/__tests__/**`, `src/**/*.test.*`, `src/**/*.spec.*` | src 본체 수정 금지 |
| ux-architect | `docs/ux-flow.md` | 다른 모든 경로 금지 |
| product-planner | `prd.md`, `trd.md` | 설계 문서 금지 |
| validator, design-critic, pr-reviewer, qa, security-reviewer | *(없음 — ReadOnly)* | 모든 Write/Edit deny |

## 인프라 파일 접근 금지 (전 에이전트 공통)

아래 경로는 하네스 인프라 파일로, 모든 에이전트가 Read/Glob/Grep 대상에서 제외해야 한다.

| 경로 패턴 | 설명 |
|-----------|------|
| `.claude/harness-memory.md` | 하네스 메모리 |
| `.claude/harness-state/` | 하네스 상태 플래그·히스토리 |
| `.claude/harness-logs/` | 실행 로그 |
| `.claude/harness.config.json` | 하네스 설정 |
| `.claude/harness/` | 하네스 스크립트 |

> 반복 위반 에이전트: engineer, pr-reviewer (WASTE_INFRA_READ 패턴)

## Pencil MCP 접근 권한 (Read-Only)

디자인 파일 참조 목적으로 아래 에이전트에 Pencil MCP 읽기 도구를 부여한다.
Write 도구(`batch_design`, `batch_design` 등) 는 designer 전용.

| 에이전트 | Pencil MCP 허용 도구 |
|----------|----------------------|
| designer | 전체 (batch_design 포함) |
| engineer | get_editor_state, batch_get, get_screenshot, get_guidelines, get_variables |
| architect | get_editor_state, batch_get, get_screenshot, get_guidelines, get_variables |
| qa | get_editor_state, batch_get, get_screenshot, get_guidelines, get_variables |
