# 프로젝트 킥오프 & 구현 가이드

## 오케스트레이션 룰 (최우선 확인)

모든 구현·디자인·계획 작업 시작 전 **`~/.claude/orchestration-rules.md`를 Read한다.**
건너뛰기 금지.

---

새 프로젝트를 시작하거나 기존 프로젝트를 이어받을 때 아래 순서를 따른다.

---

## 0단계 — 요구사항 파악 (PRD/TRD)

### PRD/TRD가 이미 있는 경우
- `prd.md` / `trd.md` 를 읽고 파악 후 1단계로 진행

### PRD/TRD가 없는 경우 — product-planner 에이전트에게 위임
`product-planner` 에이전트를 호출해 PRD/TRD 작성을 진행한다.
Claude가 직접 역질문하거나 PRD/TRD를 작성하지 않는다.

product-planner 에이전트가 역질문 → `prd.md` / `trd.md` 작성 → 유저 확인 → 1단계 진행

---

## 1단계 — 설계 문서 작성

PRD/TRD 기반으로 `docs/` 아래 설계 문서 작성.

| 파일 | 내용 |
|---|---|
| `docs/architecture.md` | 시스템 구조, 상태머신, 화면 흐름, DB ERD (Mermaid 권장) |
| `docs/domain-logic.md` | 핵심 비즈니스 로직, 상수, 계산식 |
| `docs/db-schema.md` | DB 테이블 DDL + 주요 쿼리 |
| `docs/sdk.md` | 외부 SDK/API 연동 방법, 환경별 분기 |
| `docs/ui-spec.md` | 화면별 컴포넌트 스펙, 레이아웃 |

---

## 2단계 — 레퍼런스 수집

공식 샘플/문서가 있으면 MCP 또는 WebFetch로 직접 확인. **추측 금지.**
`docs/reference.md`에 정리:
- 정확한 API 이름, import 경로, 버전별 차이
- 샘플과 현재 프로젝트 버전 차이 명시 (복붙 금지 여부)
- 의존성 규칙, 패키지 구조 패턴

설계 문서가 레퍼런스와 다르면 즉시 설계 문서 업데이트.

---

## 3단계 — 백로그 & 에픽 구성

`backlog.md` (에픽 인덱스)와 `docs/milestones/vNN/epics/epic-NN-*/stories.md` (스토리/태스크)를 작성한다.

**규칙:**
- 에픽 완료 즉시 `backlog.md` 체크, 태스크 완료 즉시 `stories.md` 체크 (`[ ]` → `[x]`)
- 설계/문서 변경 시 관련 에픽·태스크도 반드시 추가
- **스토리/impl 번호는 에픽 내 독립 순번** (Story 1, Story 2 … / impl `01-*`, `02-*` …). 전역 누적 번호 사용 금지.
- 새 에픽 stories.md 작성 전 **직전 에픽 stories.md를 읽어 컨벤션 확인** 필수.

---

## 3.5단계 — 마일스톤 버전 관리 (해당 시)

PRD/스펙이 크게 바뀌어 새 마일스톤을 시작할 때는 아래 순서로 스냅샷을 보관한다.

**원칙**: 루트 파일 = 항상 현재 최신. 과거 버전 = `docs/milestones/vNN/`에 스냅샷.

**체크리스트**:
1. 루트 스펙 파일(`prd.md`, `trd.md`, `docs/ui-spec.md` 등) → `docs/milestones/vNN/`에 복사
2. 현재 에픽 폴더 → `docs/milestones/vNN/epics/`에 복사
3. 루트 파일 업데이트 (새 버전 내용으로 교체)
4. `backlog.md` + `CLAUDE.md` 경로 업데이트

> 소규모 수정(버그픽스, 단순 문구 변경)은 스냅샷 불필요. PRD 스펙 변경 수준일 때만 적용.

---

## 4단계 — impl 계획 파일 작성

`docs/milestones/vNN/epics/epic-NN-[이름]/impl/NN-모듈명.md` 형식. **구현 전에 계획 파일이 있어야 한다.**

각 파일 포함 내용:
- 생성/수정할 파일 목록
- 인터페이스 정의 (타입, props, 반환값)
- 핵심 로직 의사코드 또는 스니펫
- 결정 근거 (검토한 대안과 선택 이유)
- 주의사항 (다른 모듈과의 경계)

---

## 5단계 — CLAUDE.md 작성

프로젝트 루트 `CLAUDE.md`에 명시 (`~/.claude/templates/CLAUDE-base.md` 참고):
- 정확한 개발 명령어
- **작업 순서**: `backlog.md` → `stories.md` → `impl/` 계획 확인 → 구현 → stories 체크
- 문서 목록 (어떤 파일에 뭐가 있는지)
- 환경변수 목록

---

## 구현 중 작업 순서 (매 모듈마다 준수)

```
1. backlog.md 에서 에픽 목록 확인
2. docs/milestones/vNN/epics/epic-NN-*/stories.md 에서 미완료 태스크 확인
3. docs/milestones/vNN/epics/epic-NN-*/impl/NN-*.md 해당 계획 파일 확인 (없으면 먼저 작성)
4. 계획대로 구현
5. stories.md 해당 태스크 체크
```

## 문서/코드 직접 수정 금지 (절대 원칙)

메인 Claude는 아래 파일을 **절대 직접 생성·수정하지 않는다.** 반드시 담당 에이전트에게 위임한다.

| 파일 계열 | 담당 에이전트 |
|---|---|
| `docs/architecture*.md`, `docs/game-logic*.md`, `docs/db-schema.md`, `docs/sdk.md`, `docs/impl/**` | **architect** |
| `docs/ui-spec*.md` | **designer** |
| `src/**` (소스 코드) | **engineer** |
| `prd.md`, `trd.md` | **product-planner** |

위 파일에 변경이 필요하다고 판단되면: 직접 수정 금지 → 담당 에이전트 호출 → 위임.

---

## 구현 루프 게이트

→ `~/.claude/orchestration-rules.md` 참조

---

## 공통 규칙

- **SDK/외부 API**: `.d.ts` 직접 열거나 MCP/WebFetch로 확인 후 사용. 추측 금지.
- **샌드박스 분기**: 광고·SDK 호출은 개발환경 mock 분기 필수.
- **stories 동기화**: 설계 변경 → stories.md 태스크 업데이트 자동 처리. 요청 기다리지 않음.
- **내용 먼저**: 파일 생성 전 내용을 유저에게 먼저 보여주고 확인 후 저장.
- **settings.json 훅 동기화**: 프로젝트 `.claude/settings.json`의 `hooks` 섹션을 추가/수정할 때 `~/.claude/setup-harness.sh`에도 즉시 반영한다. `allowedTools`/`permissions`/`enabledPlugins` 변경은 해당 없음.

---

## 에이전트 관리 원칙

에이전트 파일은 **전역(`~/.claude/agents/`)에서만 관리**한다. 프로젝트에 복사하지 않는다.

| 에이전트 유형 | 전역 파일 |
|---|---|
| 기획자 에이전트 | `~/.claude/agents/product-planner.md` |
| 코드 구현 에이전트 | `~/.claude/agents/engineer.md` |
| 검증 에이전트 | `~/.claude/agents/validator.md` |
| UI 디자인 생성 에이전트 | `~/.claude/agents/designer.md` |
| 디자인 심사 에이전트 | `~/.claude/agents/design-critic.md` |
| 설계/계획 에이전트 | `~/.claude/agents/architect.md` |

### 프로젝트별 에이전트 컨텍스트

프로젝트별 에이전트 지침은 `.claude/agent-config/{에이전트명}.md`에 작성한다.
모든 에이전트는 작업 시작 시 해당 파일이 존재하면 Read로 읽어 프로젝트 컨텍스트를 파악한다.
파일이 없으면 기본 동작으로 진행한다.

```
.claude/agent-config/
├── engineer.md      # SDK 래퍼 패턴, 의존성 규칙, 스타일 규칙
├── designer.md      # 브랜드 제약, 플랫폼 제약
├── architect.md     # TRD 섹션 매핑, 프로젝트 특화 문서 이름
└── (필요한 에이전트만 작성)
```

> `/agent-downSync`, `/agent-upSync`는 폐기됨. 전역 에이전트 수정 = 모든 프로젝트에 즉시 반영.
