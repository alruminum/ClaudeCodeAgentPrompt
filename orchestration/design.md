# 디자인 루프 (Design) — v4 2×2 포맷 매트릭스

진입 조건: 유저 UX 변경 요청 → ux 스킬 → designer 에이전트 직접 호출
**harness/executor.sh design 경유 없음. designer는 하네스 루프 밖.**

> **오케스트레이션 주체**: `ux` 스킬(commands/ux.md)이 담당한다.
> `harness/design.sh`는 deprecated — 레거시 참조용으로만 보존. 신규 작업에서 사용 금지.
> ONE_WAY: 스킬이 designer 직접 호출 후 유저 확인.
> THREE_WAY: 스킬이 designer → design-critic 루프(max 3회)를 순차 오케스트레이션.

> **참고**: [설계 루프](system-design.md)에서도 designer를 호출하지만, 그 경로는 plan loop 경유(기획-UX 루프 후)이며 이 문서의 ux 스킬 독립 경로와 별개다. 설계 루프에서의 designer 파라미터(`skip_issue_creation`, `save_handoff_to`)는 [system-design.md](system-design.md) 참조.

---

## 2×2 포맷 매트릭스

| | ONE_WAY (1개) | THREE_WAY (3개) |
|---|---|---|
| **SCREEN** (전체 화면) | `SCREEN_ONE_WAY` | `SCREEN_THREE_WAY` |
| **COMPONENT** (개별 컴포넌트) | `COMPONENT_ONE_WAY` | `COMPONENT_THREE_WAY` |

| 모드 | 진입 @MODE | 크리틱 |
|---|---|---|
| **SCREEN_ONE_WAY** | `@MODE:DESIGNER:SCREEN_ONE_WAY` | 없음 — 유저 직접 확인 |
| **SCREEN_THREE_WAY** | `@MODE:DESIGNER:SCREEN_THREE_WAY` | design-critic PASS/REJECT → 유저 PICK |
| **COMPONENT_ONE_WAY** | `@MODE:DESIGNER:COMPONENT_ONE_WAY` | 없음 — 유저 직접 확인 |
| **COMPONENT_THREE_WAY** | `@MODE:DESIGNER:COMPONENT_THREE_WAY` | design-critic PASS/REJECT → 유저 PICK |

---

## ONE_WAY 모드 흐름 (SCREEN_ONE_WAY / COMPONENT_ONE_WAY)

```mermaid
flowchart TD
    UX_SKILL["ux 스킬
(TYPE=SCREEN|COMPONENT, variant=ONE_WAY)"]
    DES["designer 에이전트
@MODE:DESIGNER:[SCREEN|COMPONENT]_ONE_WAY
직접 호출 (Agent 도구)"]
    P0["Phase 0: 컨텍스트 수집
+ Pencil 캔버스 준비"]
    P1["Phase 1: variant-A 1개 생성
(Pencil batch_design)
+ 애니메이션 스펙 + get_screenshot"]
    DRR{"DESIGN_READY_FOR_REVIEW"}

    USER_CHK{{"유저 직접 확인
Pencil 앱에서 시각적 확인
APPROVE / REJECT 입력"}}

    DES_RETRY["designer 재시도
(max 3회)"]
    DLE["DESIGN_LOOP_ESCALATE"]:::escalation

    HANDOFF{"DESIGN_HANDOFF
(Pencil frame node_id 포함)"}
    P4["Phase 4: DESIGN_HANDOFF 패키지 출력
(디자인 토큰 + 컴포넌트 구조 + 애니메이션 스펙)"]

    USER_IMPL{{"유저: 구현 요청
'이 프레임으로 구현해줘'"}}
    IMPL_ENTRY["→ 구현 루프 진입
executor.sh impl
--context 'Pencil frame ID: {node_id}'"]

    UX_SKILL --> DES
    DES --> P0
    P0 --> P1
    P1 --> DRR
    DRR --> USER_CHK
    USER_CHK -->|"APPROVE"| HANDOFF
    USER_CHK -->|"REJECT"| DES_RETRY
    DES_RETRY -->|"3회 초과"| DLE
    DES_RETRY -->|"3회 이내"| P1
    HANDOFF --> P4
    P4 --> USER_IMPL
    USER_IMPL --> IMPL_ENTRY

    classDef escalation stroke:#f00,stroke-width:2px
```

---

## THREE_WAY 모드 흐름 (SCREEN_THREE_WAY / COMPONENT_THREE_WAY)

```mermaid
flowchart TD
    UX_SKILL["ux 스킬
(TYPE=SCREEN|COMPONENT, variant=THREE_WAY)"]
    DES["designer 에이전트
@MODE:DESIGNER:[SCREEN|COMPONENT]_THREE_WAY
직접 호출 (Agent 도구)"]
    P0["Phase 0: 컨텍스트 수집
+ Pencil 캔버스 준비"]
    P1["Phase 1: variant A/B/C 3개 생성
(Pencil batch_design)
+ 애니메이션 스펙 + get_screenshot × 3"]
    DRR{"DESIGN_READY_FOR_REVIEW
+ 스크린샷 3개"}

    CRITIC["design-critic
@MODE:CRITIC:REVIEW
(variant별 PASS/REJECT)"]

    APPROVED{"VARIANTS_APPROVED
(1개 이상 PASS)"}
    ALL_REJ{"VARIANTS_ALL_REJECTED"}
    DES_RETRY["designer 재시도
(max 3회, 피드백 누적)"]
    DLE["DESIGN_LOOP_ESCALATE"]:::escalation

    PHASE3{{"Phase 3: 유저 PICK
Pencil 앱에서 PASS된 variant 시각적 확인
A/B/C 입력"}}
    HANDOFF{"DESIGN_HANDOFF
(Pencil frame node_id 포함)"}
    P4["Phase 4: DESIGN_HANDOFF 패키지 출력
(디자인 토큰 + 컴포넌트 구조 + 애니메이션 스펙)"]

    USER_IMPL{{"유저: 구현 요청
'이 프레임으로 구현해줘'"}}
    IMPL_ENTRY["→ 구현 루프 진입
executor.sh impl
--context 'Pencil frame ID: {node_id}'"]

    UX_SKILL --> DES
    DES --> P0
    P0 --> P1
    P1 --> DRR
    DRR --> CRITIC
    CRITIC -->|"variant별 채점"| APPROVED
    CRITIC -->|"전체 기준 미달"| ALL_REJ

    APPROVED --> PHASE3
    ALL_REJ -->|feedback| DES_RETRY
    DES_RETRY -->|"3회 초과"| DLE
    DES_RETRY -->|"3회 이내"| P1

    PHASE3 --> HANDOFF
    HANDOFF --> P4
    P4 --> USER_IMPL
    USER_IMPL --> IMPL_ENTRY

    classDef escalation stroke:#f00,stroke-width:2px
```

---

## 마커 레퍼런스

### 인풋 마커 (designer에게 전달하는 @MODE)

| @MODE | 대상 에이전트 | 호출 시점 |
|---|---|---|
| `@MODE:DESIGNER:SCREEN_ONE_WAY` | designer | SCREEN 전체 화면 + 1 variant |
| `@MODE:DESIGNER:SCREEN_THREE_WAY` | designer | SCREEN 전체 화면 + 3 variants |
| `@MODE:DESIGNER:COMPONENT_ONE_WAY` | designer | COMPONENT 단독 + 1 variant |
| `@MODE:DESIGNER:COMPONENT_THREE_WAY` | designer | COMPONENT 단독 + 3 variants |
| `@MODE:CRITIC:REVIEW` | design-critic | THREE_WAY 모드 — 3 variant PASS/REJECT 심사 |
| `@MODE:CRITIC:UX_SHORTLIST` | design-critic | SCREEN_THREE_WAY 심층 모드 — 스케치 5→3 선별 |

### 아웃풋 마커 (이 루프에서 발생하는 시그널)

| 마커 | 발행 주체 | 다음 행동 |
|------|-----------|-----------|
| `DESIGN_READY_FOR_REVIEW` | designer | ONE_WAY: 유저 직접 확인 / THREE_WAY: design-critic 호출 |
| `VARIANTS_APPROVED` | design-critic (THREE_WAY) | 1개 이상 PASS — Phase 3 유저 PICK 안내 |
| `VARIANTS_ALL_REJECTED` | design-critic (THREE_WAY) | 전체 REJECT — designer 재시도 (max 3회, 피드백 누적) |
| `UX_REDESIGN_SHORTLIST` | design-critic | SCREEN_THREE_WAY 심층 모드 — 3개 선별 → Phase 1 variant 생성 |
| `DESIGN_LOOP_ESCALATE` | designer (3회 초과) | 유저 직접 선택 |
| `DESIGN_HANDOFF` | designer Phase 4 (유저 선택 후) | Pencil frame node_id 전달 → 유저 구현 요청 시 executor.sh impl |

---

## 핵심 아키텍처 원칙

- **designer는 하네스 루프 밖**: 결과물이 Pencil 캔버스(파일 변경 없음, git 없음)
- **유저 확인은 Pencil 앱**: 터미널 APPROVE/REJECT 대신 시각적 확인
- **ux 스킬이 designer 직접 호출**: harness/executor.sh design 경유 없음
- **구현 연결**: 확정된 Pencil 프레임 node_id → engineer에게 전달 → batch_get으로 읽어 src/ 구현

---

## 의존성

- **Pencil.dev** 설치 필요 (VS Code 확장 또는 데스크톱 앱)
- **Pencil MCP 서버** 활성화 필요
- 사용 MCP 도구: `batch_design`, `batch_get`, `get_screenshot`, `get_editor_state`
