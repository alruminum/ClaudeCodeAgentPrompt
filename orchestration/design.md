# 디자인 루프 (Design) — v2 Pencil MCP 기반

진입 조건: impl 파일에 UI 키워드 감지 + design_critic_passed 없음

---

```mermaid
flowchart TD
    DES["designer
@MODE:DESIGNER:DEFAULT
/ UX_REDESIGN"]
    P0["Phase 0: 컨텍스트 수집
+ Pencil 캔버스 준비
(batch_get / get_screenshot)"]
    P1["Phase 1: 변형 3개 생성
(Pencil batch_design)
+ 애니메이션 스펙
+ get_screenshot × 3"]
    DRR{"DESIGN_READY_FOR_REVIEW
+ 스크린샷 3개"}

    CRITIC["design-critic
@MODE:CRITIC:REVIEW
(스크린샷 + 애니메이션 스펙)"]

    PICK{"PICK"}
    ITERATE{"ITERATE"}
    ESC_CRITIC{"ESCALATE"}

    DES_RETRY["designer 재시도
(max 3회, 피드백 누적)"]
    DLE["DESIGN_LOOP_ESCALATE"]:::escalation
    USER_PICK{{"유저 직접 선택 (강제)"}}

    PHASE3{{"Phase 3: 유저 선택
Pencil에서 확인 후 A/B/C 입력"}}
    HANDOFF{"DESIGN_HANDOFF"}

    P4["Phase 4: 코드 생성
(batch_get 확정 프레임 읽기
→ 디자인 토큰 + 컴포넌트 구조
+ 애니메이션 스펙 → 코드)
출력: design-variants/"]

    IMPL_CHK{{"impl 파일 영향 있음?"}}
    ARC_MP["architect
@MODE:ARCHITECT:MODULE_PLAN"]
    RFI{"READY_FOR_IMPL"}
    KEEP["기존 impl 파일 유지"]

    FLAG["/tmp/{prefix}_design_critic_passed
플래그 생성"]
    USER_APPROVE{{"유저 승인 대기"}}
    IMPL_ENTRY["→ 구현 루프 진입"]

    DES --> P0
    P0 --> P1
    P1 --> DRR
    DRR --> CRITIC
    CRITIC -->|"스크린샷 + 애니메이션 스펙"| PICK
    CRITIC -->|"스크린샷 + 애니메이션 스펙"| ITERATE
    CRITIC -->|"스크린샷 + 애니메이션 스펙"| ESC_CRITIC

    PICK --> PHASE3
    ITERATE -->|feedback| DES_RETRY
    DES_RETRY -->|"3회 초과"| DLE
    DES_RETRY -->|"3회 이내"| P1
    ESC_CRITIC --> USER_PICK
    DLE --> USER_PICK
    USER_PICK --> PHASE3

    PHASE3 --> HANDOFF
    HANDOFF --> P4
    P4 --> IMPL_CHK
    IMPL_CHK -->|YES| ARC_MP
    ARC_MP -->|"design_doc, module"| RFI
    IMPL_CHK -->|NO| KEEP
    RFI --> FLAG
    KEEP --> FLAG
    FLAG --> USER_APPROVE
    USER_APPROVE --> IMPL_ENTRY

    classDef escalation stroke:#f00,stroke-width:2px
```

---

## 마커 레퍼런스

### 인풋 마커 (이 루프에서 호출하는 @MODE)

| @MODE | 대상 에이전트 | 호출 시점 |
|---|---|---|
| `@MODE:DESIGNER:DEFAULT` | designer | Pencil MCP 기반 3 variant 생성 (기본) |
| `@MODE:DESIGNER:UX_REDESIGN` | designer | UX 전면 개편 요청 시 |
| `@MODE:CRITIC:REVIEW` | design-critic | 3 variant 스크린샷 심사 |
| `@MODE:CRITIC:UX_SHORTLIST` | design-critic | UX 개편 5→3 선별 |
| `@MODE:ARCHITECT:MODULE_PLAN` | architect | DESIGN_HANDOFF 후 impl 영향 있을 때 |

### 아웃풋 마커 (이 루프에서 발생하는 시그널)

| 마커 | 발행 주체 | 다음 행동 |
|------|-----------|-----------|
| `DESIGN_READY_FOR_REVIEW` | designer | 스크린샷 + 메타데이터 → design-critic 호출 |
| `PICK` | design-critic | Phase 3 유저 선택 안내 |
| `ITERATE` | design-critic | designer 재시도 (max 3회, 피드백 누적) |
| `ESCALATE` | design-critic | 유저 직접 선택 강제 |
| `UX_REDESIGN_SHORTLIST` | design-critic | 3개 선별 → Phase 1 variant 생성 |
| `DESIGN_LOOP_ESCALATE` | designer (3회 초과) | 유저 직접 선택 |
| `DESIGN_HANDOFF` | designer Phase 4 (유저 선택 후) | architect Module Plan (영향 시) → 구현 루프 |

---

## 의존성

- **Pencil.dev** 설치 필요 (VS Code 확장 또는 데스크톱 앱)
- **Pencil MCP 서버** 활성화 필요
- 사용 MCP 도구: `batch_design`, `batch_get`, `get_screenshot`, `get_editor_state`
- 추가 비용: $0 (Pencil.dev 얼리 액세스 무료)
